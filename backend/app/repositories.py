"""Repository pattern for database operations.

This module provides repository classes for each main collection,
abstracting database operations and providing a clean interface for the API layers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError
from bson import ObjectId
from bson.errors import InvalidId

from . import db

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository class with common database operations."""

    def __init__(self, collection_name: str):
        """Initialize repository with collection name.

        Args:
            collection_name: Name of the MongoDB collection
        """
        self.collection_name = collection_name

    @property
    def collection(self) -> Collection:
        database = db.get_db()
        return database[self.collection_name]

    def find_one(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return self.collection.find_one(filter_dict)
        except PyMongoError as e:
            logger.error(f"Error finding document in {self.collection_name}: {e}")
            raise

    def find_many(self, filter_dict: Dict[str, Any], limit: Optional[int] = None, sort: Optional[List[tuple]] = None) -> List[Dict[str, Any]]:
        try:
            cursor = self.collection.find(filter_dict)
            if sort:
                cursor = cursor.sort(sort)
            if limit:
                cursor = cursor.limit(limit)
            return list(cursor)
        except PyMongoError as e:
            logger.error(f"Error finding documents in {self.collection_name}: {e}")
            raise

    def insert_one(self, document: Dict[str, Any]) -> ObjectId:
        try:
            result = self.collection.insert_one(document)
            return result.inserted_id
        except PyMongoError as e:
            logger.error(f"Error inserting document in {self.collection_name}: {e}")
            raise

    def update_one(self, filter_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> bool:
        try:
            result = self.collection.update_one(filter_dict, update_dict)
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating document in {self.collection_name}: {e}")
            raise

    def delete_one(self, filter_dict: Dict[str, Any]) -> bool:
        try:
            result = self.collection.delete_one(filter_dict)
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Error deleting document in {self.collection_name}: {e}")
            raise

    def count_documents(self, filter_dict: Dict[str, Any]) -> int:
        try:
            return self.collection.count_documents(filter_dict)
        except PyMongoError as e:
            logger.error(f"Error counting documents in {self.collection_name}: {e}")
            raise


class StationsRepository(BaseRepository):
    def __init__(self):
        super().__init__('waqi_stations')

    def find_by_station_id(self, station_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'station_id': station_id})

    def find_by_city(self, city: str) -> List[Dict[str, Any]]:
        return self.find_many({'city': city})

    def find_active_stations(self) -> List[Dict[str, Any]]:
        return self.find_many({'status': 'active'})

    def find_with_pagination(self, filter_dict: Optional[Dict[str, Any]] = None, limit: int = 20, offset: int = 0) -> tuple[List[Dict[str, Any]], int]:
        if filter_dict is None:
            filter_dict = {}
        try:
            total_count = self.collection.count_documents(filter_dict)
            cursor = self.collection.find(filter_dict)
            cursor = cursor.skip(offset).limit(limit)
            stations = list(cursor)
            return stations, total_count
        except PyMongoError as e:
            logger.error(f"Error finding stations with pagination: {e}")
            raise

    def find_by_station_ids(self, station_ids: List[Any]) -> List[Dict[str, Any]]:
        if not station_ids:
            return []
        # Normalize inputs: collect numeric and string candidates
        numeric_ids: List[int] = []
        string_ids: List[str] = []
        for value in station_ids:
            # preserve ints
            if isinstance(value, int):
                numeric_ids.append(value)
                string_ids.append(str(value))
                continue
            # try to parse numeric-like strings
            try:
                n = int(value)
                numeric_ids.append(n)
                string_ids.append(str(n))
            except (TypeError, ValueError):
                # non-numeric string
                string_ids.append(str(value))

        # Build a flexible query that looks at station_id (string or numeric) and _id when possible
        queries: List[Dict[str, Any]] = []
        if string_ids:
            # match station_id against string forms
            queries.append({'station_id': {'$in': string_ids}})
        if numeric_ids:
            # also match station_id against numeric forms (if stored as numbers)
            queries.append({'station_id': {'$in': numeric_ids}})

        # attempt to match _id for candidates that look like ObjectId strings
        object_id_candidates = []
        from bson.errors import InvalidId
        for s in list(dict.fromkeys(string_ids)):
            try:
                # try to interpret as ObjectId
                oid = ObjectId(s)
                object_id_candidates.append(oid)
            except Exception:
                # ignore invalid ObjectId formats
                continue

        if object_id_candidates:
            queries.append({'_id': {'$in': object_id_candidates}})

        # Some historical imports/store station documents with integer _id values
        # (e.g. _id: 8688). If the caller provided numeric station ids, include
        # them as candidates for matching the document _id as well.
        if numeric_ids:
            queries.append({'_id': {'$in': numeric_ids}})

        if not queries:
            return []

        query: Dict[str, Any]
        if len(queries) == 1:
            query = queries[0]
        else:
            query = {'$or': queries}

        try:
            return list(self.collection.find(query))
        except PyMongoError as e:
            logger.error(f"Error finding stations by ids: {e}")
            raise


class ReadingsRepository(BaseRepository):
    def __init__(self):
        super().__init__('waqi_station_readings')

    def find_latest_by_station(self, station_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Find latest readings for a station.
        
        The waqi_station_readings collection uses meta.station_idx field instead of station_id.
        Try both field names to handle different data formats.
        """
        # Convert station_id to int if possible for meta.station_idx matching
        try:
            station_id_int = int(station_id)
        except (ValueError, TypeError):
            station_id_int = None
        
        # Try meta.station_idx first (current schema), then fall back to station_id
        queries = []
        if station_id_int is not None:
            queries.append({'meta.station_idx': station_id_int})
        queries.extend([
            {'meta.station_idx': str(station_id)},
            {'station_id': station_id},
            {'station_id': station_id_int} if station_id_int is not None else None
        ])
        
        # Remove None queries
        queries = [q for q in queries if q is not None]
        
        for query in queries:
            results = self.find_many(query, limit=limit, sort=[('ts', -1)])
            if results:
                return results
        
        return []

    def find_by_time_range(self, station_id: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        return self.find_many({'station_id': station_id, 'ts': {'$gte': start_time, '$lte': end_time}}, sort=[('ts', 1)])

    def find_by_aqi_range(self, min_aqi: int, max_aqi: int) -> List[Dict[str, Any]]:
        return self.find_many({'aqi': {'$gte': min_aqi, '$lte': max_aqi}})


class ForecastsRepository(BaseRepository):
    def __init__(self):
        super().__init__('waqi_daily_forecasts')

    def find_latest_forecast(self, station_id: str) -> Optional[Dict[str, Any]]:
        results = self.find_many({'station_id': station_id}, limit=1, sort=[('forecast_date', -1)])
        return results[0] if results else None

    def find_forecasts_by_date(self, forecast_date: datetime) -> List[Dict[str, Any]]:
        start_of_day = forecast_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = forecast_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        return self.find_many({'forecast_date': {'$gte': start_of_day, '$lte': end_of_day}})


class UsersRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__('users')

    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'email': email.lower()})

    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'username': username.lower()})

    def create_user(self, user_data: Dict[str, Any]) -> ObjectId:
        user_data['email'] = user_data['email'].lower()
        user_data['username'] = user_data['username'].lower()
        now = datetime.now(timezone.utc)
        user_data.setdefault('createdAt', now)
        user_data.setdefault('updatedAt', now)
        user_data.setdefault('status', 'active')
        try:
            return self.insert_one(user_data)
        except DuplicateKeyError as e:
            logger.warning(f"Duplicate user creation attempt: {e}")
            raise

    def find_by_id(self, user_id: Any) -> Optional[Dict[str, Any]]:
        try:
            oid = user_id if isinstance(user_id, ObjectId) else ObjectId(user_id)
        except (InvalidId, TypeError, ValueError):
            return None
        return self.find_one({'_id': oid})

    def list_with_filters(self, filter_dict: Optional[Dict[str, Any]], page: int, page_size: int, sort: Optional[List[Tuple[str, int]]]) -> Tuple[List[Dict[str, Any]], int]:
        if filter_dict is None:
            filter_dict = {}
        safe_page = max(page, 1)
        safe_page_size = max(page_size, 0)
        skip = (safe_page - 1) * safe_page_size if safe_page_size else 0
        try:
            total = self.collection.count_documents(filter_dict)
            cursor = self.collection.find(filter_dict)
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if safe_page_size:
                cursor = cursor.limit(safe_page_size)
            return list(cursor), total
        except PyMongoError as e:
            logger.error(f"Error listing users: {e}")
            raise

    def update_user_by_id(self, user_id: Any, update_operations: Dict[str, Any]) -> bool:
        try:
            oid = user_id if isinstance(user_id, ObjectId) else ObjectId(user_id)
        except (InvalidId, TypeError, ValueError):
            return False
        try:
            result = self.collection.update_one({'_id': oid}, update_operations)
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating user {user_id}: {e}")
            raise

    def update_user_status(self, user_id: Any, is_active: bool) -> bool:
        try:
            oid = user_id if isinstance(user_id, ObjectId) else ObjectId(user_id)
        except (InvalidId, TypeError, ValueError):
            return False
        try:
            result = self.collection.update_one({'_id': oid}, {'$set': {'isActive': is_active}})
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating user status: {e}")
            return False

    def update_user_role(self, user_id: Any, role: str) -> bool:
        try:
            oid = user_id if isinstance(user_id, ObjectId) else ObjectId(user_id)
        except (InvalidId, TypeError, ValueError):
            return False
        try:
            result = self.collection.update_one({'_id': oid}, {'$set': {'role': role}})
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating user role: {e}")
            return False

    def bulk_update_status(self, user_ids: List[Any], is_active: bool) -> int:
        oids: List[ObjectId] = []
        for uid in user_ids:
            try:
                oids.append(uid if isinstance(uid, ObjectId) else ObjectId(uid))
            except (InvalidId, TypeError, ValueError):
                logger.debug("Skipping invalid user id in bulk update: %s", uid)
                continue
        if not oids:
            return 0
        try:
            result = self.collection.update_many({'_id': {'$in': oids}}, {'$set': {'isActive': is_active}})
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"Error bulk updating user status: {e}")
            return 0


# Repository instances for easy import
stations_repo = StationsRepository()
readings_repo = ReadingsRepository()
forecasts_repo = ForecastsRepository()
users_repo = UsersRepository()
