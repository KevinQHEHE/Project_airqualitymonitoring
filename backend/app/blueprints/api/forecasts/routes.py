"""Forecasts blueprint for weekly aggregated statistics.

Provides an endpoint to return N-day statistics (min, max, avg) for
PM2.5, PM10 and UVI computed directly from the `waqi_station_readings`
collection using a MongoDB aggregation pipeline.

Endpoint: GET /api/forecast/weekly?station_id=<id>

Notes:
- Uses `$dateTrunc` to group by day (UTC) and computes min/max/avg.
- Accepts either numeric or string `station_id` similar to other APIs.
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.db import get_db

logger = logging.getLogger(__name__)

forecasts_bp = Blueprint('forecasts', __name__)


def _parse_station_match(station_id: Optional[str]) -> Dict[str, Any]:
	"""Return a match expression for either numeric or string station_id."""
	if not station_id:
		return {}
	if station_id.isdigit():
		return {'$or': [{'station_id': station_id}, {'meta.station_idx': int(station_id)}]}
	return {'station_id': station_id}


@forecasts_bp.route('/weekly', methods=['GET'])
def get_weekly_forecast():
	"""Return next-N-day min/max/avg for pm25, pm10 and uvi for a station.

	Query params:
	  - station_id (required)
	  - days (optional, int, default 7, min 1, max 14)

	Response:
	  {
		"station_id": <id>,
		"forecast": [
		  {"date": "YYYY-MM-DD", "pm25_min": x, "pm25_max": x, "pm25_avg": x, ...},
		  ... (N items)
		],
		"generated_at": "ISO timestamp UTC"
	  }
	"""
	try:
		station_id = request.args.get('station_id')
		if not station_id:
			return jsonify({'error': 'station_id is required'}), 400

		# parse days
		try:
			days = int(request.args.get('days', 7))
		except ValueError:
			return jsonify({'error': 'days must be an integer'}), 400
		if days < 1:
			return jsonify({'error': 'days must be >= 1'}), 400
		if days > 14:
			return jsonify({'error': 'days cannot exceed 14'}), 400

		# compute future window: from tomorrow 00:00:00 UTC to next N days (future window)
		now = datetime.utcnow().replace(tzinfo=timezone.utc)
		start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
		end = start + timedelta(days=days)

		match_expr = _parse_station_match(station_id)

		# Match documents for the station and timestamp >= start
		# Documents may store time in `ts` (datetime) or `time.iso`/`timestamp` (string). We'll match using `ts` when possible
		pipeline: List[Dict[str, Any]] = []
		pipeline.append({'$match': match_expr})
		pipeline.append({'$match': {
			'$or': [
				{'ts': {'$gte': start, '$lt': end}},
				{'time.iso': {'$gte': start.isoformat(), '$lt': end.isoformat()}},
				{'timestamp': {'$gte': start.isoformat(), '$lt': end.isoformat()}},
			]
		}})

		# Normalize timestamp into a field `ts_dt` that is a Date type when possible
		pipeline.append({'$addFields': {
			'ts_dt': {
				'$ifNull': ['$ts', {
					'$convert': {
						'input': {'$ifNull': ['$time.iso', '$timestamp']},
						'to': 'date',
						'onError': None,
						'onNull': None
					}
				}]
			}
		}})

		# Truncate to day (UTC) and group
		pipeline.append({'$addFields': {
			'day': {'$dateTrunc': {'date': '$ts_dt', 'unit': 'day', 'binSize': 1, 'timezone': 'UTC'}}
		}})

		# Group by day and compute stats
		pipeline.append({'$group': {
			'_id': '$day',
			'pm25_min': {'$min': {'$ifNull': ['$iaqi.pm25.v', '$pm25', None]}},
			'pm25_max': {'$max': {'$ifNull': ['$iaqi.pm25.v', '$pm25', None]}},
			'pm25_avg': {'$avg': {'$ifNull': ['$iaqi.pm25.v', '$pm25', None]}},
			'pm10_min': {'$min': {'$ifNull': ['$iaqi.pm10.v', '$pm10', None]}},
			'pm10_max': {'$max': {'$ifNull': ['$iaqi.pm10.v', '$pm10', None]}},
			'pm10_avg': {'$avg': {'$ifNull': ['$iaqi.pm10.v', '$pm10', None]}},
			# Support UVI stored under either iaqi.uvi.v or top-level uvi
			'uvi_min': {'$min': {'$ifNull': ['$iaqi.uvi.v', '$uvi', None]}},
			'uvi_max': {'$max': {'$ifNull': ['$iaqi.uvi.v', '$uvi', None]}},
			'uvi_avg': {'$avg': {'$ifNull': ['$iaqi.uvi.v', '$uvi', None]}},
		}})

		# Project and sort ascending by day
		pipeline.append({'$project': {
			'_id': 0,
			'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$_id', 'timezone': 'UTC'}},
			'pm25_min': 1, 'pm25_max': 1, 'pm25_avg': 1,
			'pm10_min': 1, 'pm10_max': 1, 'pm10_avg': 1,
			'uvi_min': 1, 'uvi_max': 1, 'uvi_avg': 1,
		}})

		pipeline.append({'$sort': {'date': 1}})

		# Execute aggregation and return only days present in DB (no padding)
		db = get_db()
		logger.debug(f"Weekly forecast pipeline: {pipeline}")
		cursor = db.waqi_station_readings.aggregate(pipeline, allowDiskUse=False)
		rows = list(cursor)

		# Round averages to 2 decimal places when present
		for stats in rows:
			for k in list(stats.keys()):
				if k.endswith('_avg') and stats[k] is not None:
					try:
						stats[k] = round(float(stats[k]), 2)
					except Exception:
						pass

		# --- Merge waqi_daily_forecasts as a fallback/source of truth for forecast-only data ---
		try:
			# Build date strings for future window (today .. today+N-1)
			date_strs = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]

			db_coll = db.waqi_daily_forecasts

			# Build forecast match: try to resolve incoming station_id to the
			# internal `station_idx` (waqi_stations._id) when possible. Some
			# clients pass the WAQI `station_id` string while forecast docs use
			# `station_idx` as the station _id. Attempt a lookup and fall back
			# to sensible OR conditions if resolution fails.
			forecast_match = None
			if station_id.isdigit():
				# try lookup by station_id field in waqi_stations to get its _id
				try:
					st_doc = db.waqi_stations.find_one({'station_id': str(station_id)})
				except Exception:
					st_doc = None

				if st_doc and '_id' in st_doc:
					forecast_match = {'station_idx': st_doc['_id'], 'day': {'$in': date_strs}}
				else:
					# fallback: accept either a numeric station_idx or a station_id string
					forecast_match = {'$or': [{'station_idx': int(station_id)}, {'station_id': station_id}], 'day': {'$in': date_strs}}
			else:
				# fallback to stored station_id if forecasts use it
				forecast_match = {'station_id': station_id, 'day': {'$in': date_strs}}

			fc_cursor = db_coll.find(forecast_match)
			forecast_docs = list(fc_cursor)

			# map existing rows by date for easy merge
			rows_map = {r['date']: r for r in rows}

			for doc in forecast_docs:
				day = doc.get('day')
				# extract pollutant objects (robust to nested structure)
				pollutants = doc.get('pollutants') or {}
				# support alternative structure where pm10/pm25/uvi are top-level
				pm10_obj = pollutants.get('pm10') if pollutants else (doc.get('pm10') or {})
				pm25_obj = pollutants.get('pm25') if pollutants else (doc.get('pm25') or {})
				uvi_obj = pollutants.get('uvi') if pollutants else (doc.get('uvi') or {})

				fed = {
					'pm25_min': pm25_obj.get('min') if pm25_obj else None,
					'pm25_max': pm25_obj.get('max') if pm25_obj else None,
					'pm25_avg': pm25_obj.get('avg') if pm25_obj else None,
					'pm10_min': pm10_obj.get('min') if pm10_obj else None,
					'pm10_max': pm10_obj.get('max') if pm10_obj else None,
					'pm10_avg': pm10_obj.get('avg') if pm10_obj else None,
					'uvi_min': uvi_obj.get('min') if uvi_obj else None,
					'uvi_max': uvi_obj.get('max') if uvi_obj else None,
					'uvi_avg': uvi_obj.get('avg') if uvi_obj else None,
				}

				# If we already have readings-based stats for the day, fill only missing fields
				if day in rows_map:
					target = rows_map[day]
					for k, v in fed.items():
						if (target.get(k) is None or target.get(k) == '') and v is not None:
							# round avg
							if k.endswith('_avg') and v is not None:
								try:
									target[k] = round(float(v), 2)
								except Exception:
									target[k] = v
							else:
								target[k] = v
				else:
					# Add forecast-only day into rows list
					new_entry = {'date': day}
					for k, v in fed.items():
						if k.endswith('_avg') and v is not None:
							try:
								new_entry[k] = round(float(v), 2)
							except Exception:
								new_entry[k] = v
						else:
							new_entry[k] = v
					rows.append(new_entry)

		except Exception:
			# Non-fatal: if forecasts collection missing or query fails, continue with rows
			logger.debug('waqi_daily_forecasts merge failed or no forecasts available')

		# Ensure we return exactly N consecutive days in the window
		# Build a date -> stats map and pad missing days with nulls
		rows_map = {r.get('date'): r for r in rows if r.get('date')}
		ordered: List[Dict[str, Any]] = []
		for i in range(days):
			day_str = (start + timedelta(days=i)).date().isoformat()
			if day_str in rows_map:
				ordered.append(rows_map[day_str])
			else:
				ordered.append({
					'date': day_str,
					'pm25_min': None, 'pm25_max': None, 'pm25_avg': None,
					'pm10_min': None, 'pm10_max': None, 'pm10_avg': None,
					'uvi_min': None, 'uvi_max': None, 'uvi_avg': None,
				})

		# Sort rows by date ascending (ordered is already in range order)
		rows = ordered

		# Remove days where all pollutant fields are null (user requested dropping empty days)
		def _is_all_null(item: Dict[str, Any]) -> bool:
			keys = [
				'pm25_min', 'pm25_max', 'pm25_avg',
				'pm10_min', 'pm10_max', 'pm10_avg',
				'uvi_min', 'uvi_max', 'uvi_avg'
			]
			for k in keys:
				if item.get(k) is not None:
					return False
			return True

		rows = [r for r in rows if not _is_all_null(r)]

		response = {
			'station_id': station_id,
			'forecast': rows,
			'generated_at': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
		}

		return jsonify(response), 200

	except Exception as e:
		logger.error(f"get_weekly_forecast error: {e}")
		return jsonify({'error': 'Internal server error'}), 500
