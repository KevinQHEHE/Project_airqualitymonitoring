"""Air quality API: latest measurements per station.

Provides an endpoint to return the most recent measurement per station
with common pollutant fields and AQI. Supports filtering by `station_id`
and `limit` query parameter.

Design notes:
- Uses a MongoDB aggregation pipeline to pick the latest reading per station
- Projects a stable set of pollutant fields (additive; missing fields may be null)
- Returns JSON with list of station measurements
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify
import logging
from typing import List, Dict, Any, Optional

from backend.app.db import get_db

logger = logging.getLogger(__name__)

air_quality_bp = Blueprint('air_quality', __name__)


def build_latest_per_station_pipeline(station_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Build aggregation pipeline to return latest measurement per station.

    Args:
        station_id: optional station_id to filter results
        limit: maximum number of stations to return

    Returns:
        Aggregation pipeline list
    """
    match_stage = None
    # Support matching either the stored `station_id` (legacy) or `meta.station_idx` (numeric)
    if station_id:
        # If station_id looks numeric, match numeric meta.station_idx as well
        if station_id.isdigit():
            match_stage = {'$or': [
                {'station_id': station_id},
                {'meta.station_idx': int(station_id)}
            ]}
        else:
            match_stage = {'station_id': station_id}

    # Pollutant fields we want to include. Keep this list additive.
    pollutant_fields = [
        'pm25', 'pm10', 'o3', 'no2', 'so2', 'co', 'bc', 'nh3'
    ]

    # Build extraction expressions for pollutants. Many documents store pollutant
    # values under `iaqi.<pollutant>.v` (from WAQI). Fall back to top-level fields
    # if present.
    pollutant_projection = {}
    for f in pollutant_fields:
        pollutant_projection[f] = {'$first': {'$ifNull': [f'$iaqi.{f}.v', f'${f}', None]}}

    pipeline: List[Dict[str, Any]] = []
    if match_stage:
        pipeline.append({'$match': match_stage})

    # Sort by timestamp descending so $first in grouping is the latest. Documents
    # may store time in `ts` (datetime) or `time.iso` (string). Prefer `ts`.
    pipeline.append({'$sort': {'ts': -1, 'time.iso': -1, 'timestamp': -1}})

    # Group by station_id and take the first (latest) document per station
    # Build group projection: pick fields from either meta.* or top-level fields.
    project_fields = {
        'station_id': {'$first': {'$ifNull': ['$meta.station_idx', '$station_id', None]}},
        'timestamp': {'$first': {'$ifNull': ['$ts', '$time.iso', '$timestamp', None]}},
        'aqi': {'$first': {'$ifNull': ['$aqi', None]}},
        'location': {'$first': {'$ifNull': ['$location', '$meta.location', None]}},
        'station_name': {'$first': {'$ifNull': ['$station_name', '$meta.name', None]}},
    }
    # include pollutants (already prepared as $first expressions)
    for k, expr in pollutant_projection.items():
        project_fields[k] = expr

    pipeline.append({
        '$group': {
            # Group by meta.station_idx when available, otherwise station_id.
            '_id': {'$ifNull': ['$meta.station_idx', '$station_id']},
            **project_fields
        }
    })

    # Optional lookup to enrich station_name and location from `waqi_stations` collection
    # `meta.station_idx` references `waqi_stations._id` per db schema.
    pipeline.append({
        '$lookup': {
            'from': 'waqi_stations',
            'localField': '_id',
            'foreignField': '_id',
            'as': 'station_doc'
        }
    })

    # Unwind station_doc if present (preserveEmpty to keep readings without station metadata)
    pipeline.append({'$unwind': {'path': '$station_doc', 'preserveNullAndEmptyArrays': True}})

    # Project final shape and remove _id
    final_projection = {
        '_id': 0,
        'station_id': 1,
        # station_name: fallback order: grouped station_name, waqi_stations.city.name
        'station_name': { '$ifNull': ['$station_name', '$station_doc.city.name'] },
        'timestamp': 1,
        'aqi': 1,
        # location: fallback order: grouped location, waqi_stations.city.geo
        'location': { '$ifNull': ['$location', '$station_doc.city.geo'] },
    }
    for f in pollutant_fields:
        final_projection[f] = 1

    pipeline.append({'$project': final_projection})

    # Sort by aqi desc then timestamp desc to give deterministic ordering
    pipeline.append({'$sort': {'aqi': -1, 'timestamp': -1}})

    if limit and limit > 0:
        pipeline.append({'$limit': limit})

    return pipeline


@air_quality_bp.route('/latest', methods=['GET'])
def get_latest_measurements():
    """Return the latest measurement per station.

    Query parameters:
      - station_id: optional, filter to a single station
      - limit: optional, number of stations to return (default 100, max 500)

    Returns:
        JSON list of latest measurements per station
    """
    try:
        station_id = request.args.get('station_id')
        try:
            limit = int(request.args.get('limit', 100))
        except ValueError:
            return jsonify({'error': 'limit must be an integer'}), 400

        if limit <= 0:
            return jsonify({'error': 'limit must be greater than 0'}), 400
        if limit > 500:
            return jsonify({'error': 'limit cannot exceed 500'}), 400

        db = get_db()
        pipeline = build_latest_per_station_pipeline(station_id, limit)
        logger.debug(f"Aggregation pipeline: {pipeline}")

        cursor = db.waqi_station_readings.aggregate(pipeline, allowDiskUse=False)
        results = list(cursor)

        # Ensure timestamps and other non-JSON types are serialized
        for doc in results:
            if 'timestamp' in doc:
                # If it's a datetime, convert to ISO format
                try:
                    doc['timestamp'] = doc['timestamp'].isoformat()
                except Exception:
                    pass

        return jsonify({'measurements': results}), 200

    except Exception as e:
        logger.error(f"get_latest_measurements error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
