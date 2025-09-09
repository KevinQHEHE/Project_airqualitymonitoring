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
from datetime import datetime

from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError, PyMongoError

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
        logger.error(f"Bulk write error for station {station_idx} readings: {e.details}")
        raise MongoUpsertError(f"Readings bulk upsert failed: {e}")
    except PyMongoError as e:
        logger.error(f"Failed to upsert readings for station {station_idx}: {e}")
        raise MongoUpsertError(f"Readings upsert failed: {e}")


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
