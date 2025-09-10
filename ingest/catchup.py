"""
Catch-up utilities for ingesting missing hourly data on server startup.

Functions:
 - catchup_station(station_idx): backfill missing hours from last seen ts -> now (UTC)
 - catchup_all_stations(): iterate stations and run catchup_station

This module is defensive: it accepts multiple response shapes from the AQICN client
and uses the existing mongo upsert utilities to ensure idempotence.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from ingest.aqicn_client import create_client_from_env, AqicnClientError, AqicnRateLimitError
from ingest.mongo_utils import upsert_readings
# Import backend DB lazily inside functions to avoid circular imports with Flask app

logger = logging.getLogger(__name__)


def _parse_ts_to_utc(ts_str: str) -> datetime:
    """Parse ISO-ish timestamp strings to UTC-aware datetime.

    Accepts values like '2025-09-09T10:00:00Z' or WAQI local time string '2025-09-09 17:00:00'
    together with timezone info when available.
    """
    if not ts_str:
        raise ValueError("Empty timestamp")

    # Already in ISO Z format?
    try:
        if ts_str.endswith('Z'):
            return datetime.fromisoformat(ts_str.replace('Z', '+00:00')).astimezone(timezone.utc)
        # Try common WAQI format 'YYYY-MM-DD HH:MM:SS' (local) - assume UTC if no tz
        if ' ' in ts_str and 'T' not in ts_str:
            # treat as naive local time — interpret as UTC to be conservative
            return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(ts_str).astimezone(timezone.utc)
    except Exception:
        # Fallback: parse date part only
        try:
            return datetime.strptime(ts_str.split(' ')[0], '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except Exception:
            raise


def _normalize_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _get_last_ts_for_station(station_idx: int) -> Optional[datetime]:
    """Return last seen ts (UTC datetime) for a station or None if no readings."""
    from backend.app import db as backend_db
    db = backend_db.get_db()
    coll = db.waqi_station_readings
    doc = coll.find_one({'meta.station_idx': station_idx}, sort=[('ts', -1)])
    if not doc:
        return None
    ts = doc.get('ts')
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc)
    if isinstance(ts, str):
        return _parse_ts_to_utc(ts)
    return None


def _extract_readings_from_response(resp: Dict[str, Any], station_idx: int) -> List[Dict[str, Any]]:
    """Try multiple shapes to extract per-hour readings as list of documents with 'ts' and 'aqi'."""
    results: List[Dict[str, Any]] = []

    # Common: resp may contain 'time_series' or 'readings' or 'data' with nested points
    candidates = []
    if isinstance(resp, dict):
        # Handle AQICN client.fetch_hourly() processed shape which returns
        # keys like 'current_time' and 'current_aqi' (not wrapped under 'data').
        # Create a single reading from current snapshot so stations without
        # a time_series still get ingested.
        cur_time = resp.get('current_time') or resp.get('current_time_iso')
        cur_aqi = resp.get('current_aqi') or resp.get('current_aqi_value') or resp.get('current_aqi')
        if cur_time and cur_aqi is not None:
            results.append({'ts': cur_time, 'aqi': cur_aqi, 'time': {'s': cur_time}, 'meta': {'station_idx': station_idx}})

        if 'time_series' in resp and isinstance(resp['time_series'], list):
            candidates = resp['time_series']
        elif 'readings' in resp and isinstance(resp['readings'], list):
            candidates = resp['readings']
        elif 'data' in resp and isinstance(resp['data'], dict):
            # Some clients wrap points under data->history or similar
            data = resp['data']
            if isinstance(data.get('history'), list):
                candidates = data['history']
            elif isinstance(data.get('time_series'), list):
                candidates = data['time_series']
            # else maybe a single current reading
            elif 'time' in data:
                # create single reading
                time_s = data.get('time', {}).get('s') or data.get('time', {}).get('iso')
                aqi = data.get('aqi')
                if time_s:
                    results.append({'ts': time_s, 'aqi': aqi, 'time': data.get('time', {})})

    # If we got a candidates list, normalize entries
    for item in candidates:
        if not isinstance(item, dict):
            continue

        # Common shapes: {'ts': ..., 'aqi': ...} or {'date': 'YYYY-MM-DD', 'avg': ...}
        ts = item.get('ts') or item.get('time') or item.get('date') or item.get('s')
        aqi = item.get('aqi') or item.get('value') or item.get('avg')
        time_meta = item.get('time') or item.get('meta') or {}
        if ts is None:
            # try nested
            if 'time' in item and isinstance(item['time'], dict):
                ts = item['time'].get('s')
        if ts is None:
            continue
        results.append({'ts': ts, 'aqi': aqi, 'time': time_meta})

    # Attach meta for station when inserting
    for r in results:
        if 'meta' not in r:
            r['meta'] = {}
        r['meta']['station_idx'] = station_idx

    return results


def catchup_station(station_idx: int, client=None, dry_run: bool = False) -> Dict[str, Any]:
    """Backfill missing hourly readings for a single station from last_ts -> now.

    Returns a dict with counts and status.
    """
    if client is None:
        client = create_client_from_env()

    try:
        now_utc = datetime.now(timezone.utc)
        now_hour = _normalize_hour(now_utc)

        last_ts = _get_last_ts_for_station(station_idx)
        logger.info(f"Station {station_idx}: last_ts={last_ts} now_hour={now_hour}")
        if last_ts is None:
            # No readings at all — fetch only current snapshot
            from_ts = now_hour
        else:
            from_ts = _normalize_hour(last_ts + timedelta(hours=1))

        # Handle cases where stored last_ts is in the future (data corruption or timezone issues).
        # In that case, clamp from_ts to now_hour and proceed with a warning rather than
        # marking the station up-to-date.
        if from_ts > now_hour:
            if last_ts and last_ts > now_hour:
                logger.warning(
                    f"Station {station_idx}: last_ts {last_ts} is in the future relative to now {now_hour}; "
                    "clamping from_ts to now and proceeding"
                )
                from_ts = now_hour
            else:
                logger.info(f"Station {station_idx}: up-to-date (last {last_ts}) from_ts={from_ts} now_hour={now_hour}")
                return {'station_idx': station_idx, 'status': 'up-to-date', 'processed': 0}

        # Fetch in one call using client.fetch_hourly(start_date, end_date) where supported
        try:
            resp = client.fetch_hourly(station_idx, start_date=from_ts, end_date=now_hour)
        except AqicnRateLimitError as e:
            logger.warning(f"Rate limited when fetching station {station_idx}: {e}")
            # Wait and retry once
            time.sleep(60)
            resp = client.fetch_hourly(station_idx, start_date=from_ts, end_date=now_hour)

        readings = _extract_readings_from_response(resp, station_idx)

        if not readings:
            # As a fallback, try to insert the single current reading
            if isinstance(resp, dict) and 'data' in resp:
                data = resp['data']
                time_s = data.get('time', {}).get('s') or data.get('time', {}).get('iso')
                aqi = data.get('aqi')
                if time_s:
                    readings = [{'ts': time_s, 'aqi': aqi, 'time': data.get('time', {}), 'meta': {'station_idx': station_idx}}]

        # Convert ts strings to ISO-Z where possible (upsert_readings will accept string ts)
        if not readings:
            logger.info(f"Station {station_idx}: no new readings available from API")
            return {'station_idx': station_idx, 'status': 'no-data', 'processed': 0}

        # Upsert into DB (or dry-run)
        processed_count = len(readings)
        if dry_run:
            logger.info(f"(dry-run) Station {station_idx}: would process {processed_count} readings")
            return {'station_idx': station_idx, 'status': 'dry-run', 'processed': processed_count}

        from backend.app import db as backend_db
        db_conn = backend_db.get_db()
        collection = db_conn.waqi_station_readings
        result = upsert_readings(collection, station_idx, readings)

        logger.info(f"Station {station_idx}: catchup processed {result.get('processed_count', 0)} readings")
        return {'station_idx': station_idx, 'status': 'ok', 'processed': result.get('processed_count', 0)}

    except Exception as e:
        logger.exception(f"Error during catchup for station {station_idx}: {e}")
        return {'station_idx': station_idx, 'status': 'error', 'error': str(e)}


def catchup_all_stations(country: str = 'VN', dry_run: bool = False, station: Optional[int] = None) -> Dict[str, Any]:
    """Iterate all stations in DB and perform catchup.

    Returns summary dict.
    """
    client = None
    try:
        client = create_client_from_env()
    except Exception as e:
        logger.error(f"Cannot create AQICN client for catchup: {e}")
        return {'status': 'error', 'error': str(e)}

    from backend.app import db as backend_db
    db_conn = backend_db.get_db()
    stations_coll = db_conn.waqi_stations

    summary = {'processed': 0, 'errors': 0, 'stations': []}

    # If caller requested a single station, run it directly without depending
    # on the contents of `waqi_stations` (useful for testing or one-off runs).
    if station is not None:
        try:
            res = catchup_station(int(station), client=client, dry_run=dry_run)
            summary['stations'].append(res)
            if res.get('status') == 'ok':
                summary['processed'] += res.get('processed', 0) or 0
            if res.get('status') == 'error':
                summary['errors'] += 1
            logger.info(f"Catchup finished: processed={summary['processed']} errors={summary['errors']}")
            return summary
        except Exception as e:
            logger.exception(f"Unhandled error running single-station catchup {station}: {e}")
            return {'status': 'error', 'error': str(e)}

    query_cursor = stations_coll.find({})
    def _extract_station_id(station_doc):
        """Return a normalized station id (prefer numeric) or None if not available."""
        # prefer explicit numeric field
        val = station_doc.get('station_idx') or station_doc.get('id') or station_doc.get('_id')
        if val is None:
            return None
        # Handle pymongo ObjectId
        try:
            from bson import ObjectId
            if isinstance(val, ObjectId):
                return str(val)
        except Exception:
            # bson not available or val not ObjectId
            pass
        # Handle exported JSON shape {'$oid': '...'} or other dict wrappers
        if isinstance(val, dict):
            if '$oid' in val:
                return val.get('$oid')
            # fallback to string representation
            return str(val)
        return val

    for station_doc in query_cursor:
        raw_id = _extract_station_id(station_doc)
        if raw_id is None:
            continue
        # Try to interpret as integer station index where possible
        station_idx_int = None
        try:
            station_idx_int = int(raw_id)
        except Exception:
            # not an integer-like id; we'll skip unless user requested a matching string
            station_idx_int = None
        # If a single station is requested, skip others
        try:
            if station is not None:
                # compare numerically if possible, else compare string forms
                if station_idx_int is not None:
                    if station_idx_int != int(station):
                        continue
                else:
                    if str(raw_id) != str(station):
                        continue
            # If we couldn't coerce to int, skip this station (catchup_station expects int id)
            if station_idx_int is None:
                logger.warning(f"Skipping station with non-integer id: {raw_id}")
                continue
            res = catchup_station(int(station_idx_int), client=client, dry_run=dry_run)
            summary['stations'].append(res)
            if res.get('status') == 'ok':
                summary['processed'] += res.get('processed', 0) or 0
            if res.get('status') == 'error':
                summary['errors'] += 1
        except Exception as e:
            logger.exception(f"Unhandled error catchup station {raw_id}: {e}")
            summary['errors'] += 1

    logger.info(f"Catchup finished: processed={summary['processed']} errors={summary['errors']}")
    return summary


def start_background_catchup(app):
    """Start a background thread that runs catchup_all_stations once on startup."""

    def _run():
        with app.app_context():
            try:
                logger.info("Starting startup catchup: scanning stations and filling missing hours")
                catchup_all_stations()
            except Exception:
                logger.exception("Startup catchup failed")

    t = threading.Thread(target=_run, name='catchup-startup', daemon=True)
    t.start()
