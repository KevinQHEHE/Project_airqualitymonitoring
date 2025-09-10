"""MongoDB upsert utilities for Air Quality data persistence.

This module provides idempotent MongoDB operations for upserting stations,
readings, and forecasts according to the waqi schema. All operations are
designed to be safe for repeated execution without creating duplicates.

Key decisions:
- Station upserts use _id=idx for direct mapping
- Readings upsert by (station_idx, ts) compound key
- Forecasts upsert by (station_idx, day) compound key
- Bulk operations supported for efficiency
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError, PyMongoError, DuplicateKeyError

logger = logging.getLogger(__name__)


class MongoUpsertError(Exception):
    """Custom exception for MongoDB upsert operations."""
    pass


def upsert_station(
    collection: Collection,
    station_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Upsert a single station record using _id=idx.
    
    Args:
        collection: MongoDB collection for stations
        station_data: Station data containing _id, city, geo, tz fields
        
    Returns:
        Dict with upsert result metadata
        
    Raises:
        MongoUpsertError: If upsert operation fails
        ValueError: If required fields are missing
    """
    # Validate required fields
    if '_id' not in station_data:
        raise ValueError("Station data must contain '_id' field")
    if 'city' not in station_data:
        raise ValueError("Station data must contain 'city' field")
    
    station_id = station_data['_id']
    
    try:
        result = collection.replace_one(
            {'_id': station_id},
            station_data,
            upsert=True
        )
        
        logger.debug(f"Station {station_id} upserted successfully")
        
        return {
            'station_id': station_id,
            'matched_count': result.matched_count,
            'modified_count': result.modified_count,
            'upserted_id': result.upserted_id,
            'acknowledged': result.acknowledged
        }
        
    except PyMongoError as e:
        logger.error(f"Failed to upsert station {station_id}: {e}")
        raise MongoUpsertError(f"Station upsert failed: {e}")


def upsert_readings(
    collection: Collection,
    station_idx: int,
    readings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Upsert multiple readings for a station using (station_idx, ts) compound key.
    
    Args:
        collection: MongoDB collection for readings
        station_idx: WAQI station index
        readings: List of reading documents with ts, aqi, time fields
        
    Returns:
        Dict with bulk upsert result metadata
        
    Raises:
        MongoUpsertError: If bulk upsert operation fails
        ValueError: If readings data is invalid
    """
    if not readings:
        logger.warning(f"No readings provided for station {station_idx}")
        return {'station_idx': station_idx, 'processed_count': 0}
    
    # Prepare bulk operations
    operations = []
    
    for reading in readings:
        # Validate required fields
        if 'ts' not in reading:
            raise ValueError("Reading must contain 'ts' field")
        if 'aqi' not in reading:
            raise ValueError("Reading must contain 'aqi' field")
        if 'time' not in reading:
            raise ValueError("Reading must contain 'time' field")
        
        # Ensure meta.station_idx is set
        if 'meta' not in reading:
            reading['meta'] = {}
        reading['meta']['station_idx'] = station_idx
        
        # Create upsert operation with compound key
        filter_query = {
            'meta.station_idx': station_idx,
            'ts': reading['ts']
        }
        
        operation = UpdateOne(
            filter_query,
            {'$set': reading},
            upsert=True
        )
        operations.append(operation)
    
    try:
        result = collection.bulk_write(operations, ordered=False)

        logger.info(
            f"Bulk upserted {len(readings)} readings for station {station_idx}: "
            f"{result.upserted_count} inserted, {result.modified_count} updated"
        )

        return {
            'station_idx': station_idx,
            'processed_count': len(readings),
            'matched_count': result.matched_count,
            'modified_count': result.modified_count,
            'upserted_count': result.upserted_count,
            'acknowledged': result.acknowledged
        }

    except BulkWriteError as e:
        # Time-series collections do not support update/upsert operations.
        # Detect that case and fall back to an insert-only approach that
        # inserts only timestamps that do not already exist for the station.
        details = getattr(e, 'details', {}) or {}
        msg = str(e)
        logger.error(f"Bulk write error for station {station_idx} readings: {details}")

        # Heuristic: the server error message for this case contains
        # 'Cannot perform a non-multi update on a time-series collection'
        if 'Cannot perform a non-multi update on a time-series collection' in msg or \
           any(w.get('code') == 72 for w in details.get('writeErrors', [])):
            logger.info(
                "Detected time-series collection; switching to insert-only path for readings"
            )
            try:
                return _insert_missing_readings(collection, station_idx, readings)
            except MongoUpsertError:
                # Re-raise original bulk error context for visibility
                raise
        # Otherwise surface the original error
        raise MongoUpsertError(f"Readings bulk upsert failed: {e}")
    except PyMongoError as e:
        logger.error(f"Failed to upsert readings for station {station_idx}: {e}")
        raise MongoUpsertError(f"Readings upsert failed: {e}")


def _insert_missing_readings(
    collection: Collection,
    station_idx: int,
    readings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Insert-only fallback for time-series collections.

    This function queries existing timestamps for the station and inserts
    only the missing readings. The operation is idempotent and avoids
    update/upsert operations which time-series collections prohibit.
    """
    # Helper: coerce various ts representations into datetime (UTC)
    def _coerce_ts_to_datetime(ts_val) -> Optional[datetime]:
        if ts_val is None:
            return None
        if isinstance(ts_val, datetime):
            return ts_val.astimezone(timezone.utc)
        if isinstance(ts_val, (int, float)):
            # treat as POSIX timestamp (seconds)
            try:
                return datetime.fromtimestamp(float(ts_val), tz=timezone.utc)
            except Exception:
                return None
        if isinstance(ts_val, str):
            s = ts_val.strip()
            # ISO-like with Z
            try:
                if s.endswith('Z'):
                    return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(timezone.utc)
                # Try full datetime with space
                try:
                    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                except Exception:
                    pass
                # Try date-only
                try:
                    return datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                except Exception:
                    pass
                # Fallback to fromisoformat
                return datetime.fromisoformat(s).astimezone(timezone.utc)
            except Exception:
                return None
        return None

    # Gather candidate timestamps and coerce them
    coerced_map = {}
    for r in readings:
        ts_val = r.get('ts')
        dt = _coerce_ts_to_datetime(ts_val)
        if dt is None:
            logger.warning(f"Skipping reading with unparseable ts for station {station_idx}: {ts_val}")
            continue
        coerced_map.setdefault(dt, []).append(r)

    if not coerced_map:
        logger.info(f"No valid readings to insert for station {station_idx}")
        return {'station_idx': station_idx, 'processed_count': 0, 'inserted_count': 0}

    ts_list = list(coerced_map.keys())

    try:
        existing_cursor = collection.find(
            {'meta.station_idx': station_idx, 'ts': {'$in': ts_list}},
            {'ts': 1}
        )
    except PyMongoError as e:
        logger.error(f"Failed to query existing readings for station {station_idx}: {e}")
        raise MongoUpsertError(f"Failed to query existing readings: {e}")

    existing_ts = {doc.get('ts').astimezone(timezone.utc) for doc in existing_cursor if isinstance(doc.get('ts'), datetime)}

    to_insert = []
    for dt, rows in coerced_map.items():
        if dt in existing_ts:
            continue
        for r in rows:
            # Clone and set normalized ts and meta
            new_doc = dict(r)
            new_doc['ts'] = dt
            if 'meta' not in new_doc:
                new_doc['meta'] = {}
            new_doc['meta']['station_idx'] = station_idx
            to_insert.append(new_doc)

    if not to_insert:
        logger.info(f"No new readings to insert for station {station_idx}")
        return {'station_idx': station_idx, 'processed_count': 0, 'inserted_count': 0}

    try:
        result = collection.insert_many(to_insert, ordered=False)
        inserted = len(result.inserted_ids)
        logger.info(f"Inserted {inserted} new readings for station {station_idx}")
        return {
            'station_idx': station_idx,
            'processed_count': len(readings),
            'inserted_count': inserted,
            'acknowledged': True
        }
    except BulkWriteError as e:
        details = getattr(e, 'details', {}) or {}
        inserted = details.get('nInserted', 0)
        logger.error(
            f"Bulk insert partially failed for station {station_idx}: {details} (inserted={inserted})"
        )
        # Treat partial insert as error for now
        raise MongoUpsertError(f"Readings bulk insert failed: {e}")
    except DuplicateKeyError as e:
        # Concurrent insert may have created some documents; re-query to compute
        logger.warning(f"Duplicate key during insert for station {station_idx}: {e}")
        try:
            post_cursor = collection.find(
                {'meta.station_idx': station_idx, 'ts': {'$in': ts_list}},
                {'ts': 1}
            )
            post_ts = set()
            for d in post_cursor:
                t = d.get('ts')
                if isinstance(t, datetime):
                    post_ts.add(t.astimezone(timezone.utc))
            inserted_count = len(post_ts - existing_ts)
        except PyMongoError:
            inserted_count = 0
        return {
            'station_idx': station_idx,
            'processed_count': len(readings),
            'inserted_count': inserted_count,
            'acknowledged': False
        }
    except PyMongoError as e:
        logger.error(f"Failed to insert readings for station {station_idx}: {e}")
        raise MongoUpsertError(f"Readings insert failed: {e}")


def upsert_forecasts(
    collection: Collection,
    station_idx: int,
    forecasts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Upsert multiple forecasts for a station using (station_idx, day) compound key.
    
    Args:
        collection: MongoDB collection for forecasts
        station_idx: WAQI station index
        forecasts: List of forecast documents with day, pollutants fields
        
    Returns:
        Dict with bulk upsert result metadata
        
    Raises:
        MongoUpsertError: If bulk upsert operation fails
        ValueError: If forecasts data is invalid
    """
    if not forecasts:
        logger.warning(f"No forecasts provided for station {station_idx}")
        return {'station_idx': station_idx, 'processed_count': 0}
    
    # Prepare bulk operations
    operations = []
    
    for forecast in forecasts:
        # Validate required fields
        if 'day' not in forecast:
            raise ValueError("Forecast must contain 'day' field")
        if 'pollutants' not in forecast:
            raise ValueError("Forecast must contain 'pollutants' field")
        
        # Ensure station_idx is set
        forecast['station_idx'] = station_idx
        
        # Create upsert operation with compound key
        filter_query = {
            'station_idx': station_idx,
            'day': forecast['day']
        }
        
        operation = UpdateOne(
            filter_query,
            {'$set': forecast},
            upsert=True
        )
        operations.append(operation)
    
    try:
        result = collection.bulk_write(operations, ordered=False)
        
        logger.info(
            f"Bulk upserted {len(forecasts)} forecasts for station {station_idx}: "
            f"{result.upserted_count} inserted, {result.modified_count} updated"
        )
        
        return {
            'station_idx': station_idx,
            'processed_count': len(forecasts),
            'matched_count': result.matched_count,
            'modified_count': result.modified_count,
            'upserted_count': result.upserted_count,
            'acknowledged': result.acknowledged
        }
        
    except BulkWriteError as e:
        logger.error(f"Bulk write error for station {station_idx} forecasts: {e.details}")
        raise MongoUpsertError(f"Forecasts bulk upsert failed: {e}")
    except PyMongoError as e:
        logger.error(f"Failed to upsert forecasts for station {station_idx}: {e}")
        raise MongoUpsertError(f"Forecasts upsert failed: {e}")


def bulk_upsert_stations(
    collection: Collection,
    stations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Bulk upsert multiple stations efficiently.
    
    Args:
        collection: MongoDB collection for stations
        stations: List of station documents with _id, city, geo fields
        
    Returns:
        Dict with bulk upsert result metadata
        
    Raises:
        MongoUpsertError: If bulk upsert operation fails
        ValueError: If stations data is invalid
    """
    if not stations:
        logger.warning("No stations provided for bulk upsert")
        return {'processed_count': 0}
    
    # Prepare bulk operations
    operations = []
    
    for station in stations:
        # Validate required fields
        if '_id' not in station:
            raise ValueError("Station must contain '_id' field")
        if 'city' not in station:
            raise ValueError("Station must contain 'city' field")
        
        operation = UpdateOne(
            {'_id': station['_id']},
            {'$set': station},
            upsert=True
        )
        operations.append(operation)
    
    try:
        result = collection.bulk_write(operations, ordered=False)
        
        logger.info(
            f"Bulk upserted {len(stations)} stations: "
            f"{result.upserted_count} inserted, {result.modified_count} updated"
        )
        
        return {
            'processed_count': len(stations),
            'matched_count': result.matched_count,
            'modified_count': result.modified_count,
            'upserted_count': result.upserted_count,
            'acknowledged': result.acknowledged
        }
        
    except BulkWriteError as e:
        logger.error(f"Bulk write error for stations: {e.details}")
        raise MongoUpsertError(f"Stations bulk upsert failed: {e}")
    except PyMongoError as e:
        logger.error(f"Failed to bulk upsert stations: {e}")
        raise MongoUpsertError(f"Stations bulk upsert failed: {e}")
