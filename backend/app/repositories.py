"""Repository pattern for database operations.

This module provides repository classes for each main collection,
abstracting database operations and providing a clean interface for the API layers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError
from bson import ObjectId

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
        """Get the MongoDB collection instance."""
        database = db.get_db()
        return database[self.collection_name]
    
    def find_one(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document matching the filter.
        
        Args:
            filter_dict: MongoDB filter criteria
            
        Returns:
            Document if found, None otherwise
        """
        try:
            return self.collection.find_one(filter_dict)
        except PyMongoError as e:
            logger.error(f"Error finding document in {self.collection_name}: {e}")
            raise
    
    def find_many(self, filter_dict: Dict[str, Any], 
                  limit: Optional[int] = None, 
                  sort: Optional[List[tuple]] = None) -> List[Dict[str, Any]]:
        """Find multiple documents matching the filter.
        
        Args:
            filter_dict: MongoDB filter criteria
            limit: Maximum number of documents to return
            sort: Sort specification as list of (field, direction) tuples
            
        Returns:
            List of matching documents
        """
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
        """Insert a single document.
        
        Args:
            document: Document to insert
            
        Returns:
            Inserted document ID
        """
        try:
            result = self.collection.insert_one(document)
            return result.inserted_id
        except PyMongoError as e:
            logger.error(f"Error inserting document in {self.collection_name}: {e}")
            raise
    
    def update_one(self, filter_dict: Dict[str, Any], 
                   update_dict: Dict[str, Any]) -> bool:
        """Update a single document.
        
        Args:
            filter_dict: MongoDB filter criteria
            update_dict: Update operations
            
        Returns:
            True if document was modified, False otherwise
        """
        try:
            result = self.collection.update_one(filter_dict, update_dict)
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating document in {self.collection_name}: {e}")
            raise
    
    def delete_one(self, filter_dict: Dict[str, Any]) -> bool:
        """Delete a single document.
        
        Args:
            filter_dict: MongoDB filter criteria
            
        Returns:
            True if document was deleted, False otherwise
        """
        try:
            result = self.collection.delete_one(filter_dict)
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Error deleting document in {self.collection_name}: {e}")
            raise
    
    def count_documents(self, filter_dict: Dict[str, Any]) -> int:
        """Count documents matching the filter.
        
        Args:
            filter_dict: MongoDB filter criteria
            
        Returns:
            Number of matching documents
        """
        try:
            return self.collection.count_documents(filter_dict)
        except PyMongoError as e:
            logger.error(f"Error counting documents in {self.collection_name}: {e}")
            raise


class StationsRepository(BaseRepository):
    """Repository for air quality monitoring stations."""
    
    def __init__(self):
        super().__init__('waqi_stations')
    
    def find_by_station_id(self, station_id: str) -> Optional[Dict[str, Any]]:
        """Find station by station ID.
        
        Args:
            station_id: Unique station identifier
            
        Returns:
            Station document if found
        """
        return self.find_one({'station_id': station_id})
    
    def find_by_city(self, city: str) -> List[Dict[str, Any]]:
        """Find stations by city.
        
        Args:
            city: City name
            
        Returns:
            List of stations in the city
        """
        return self.find_many({'city': city})
    
    def find_active_stations(self) -> List[Dict[str, Any]]:
        """Find all active stations.
        
        Returns:
            List of active stations
        """
        return self.find_many({'status': 'active'})
    
    def find_with_pagination(self, filter_dict: Optional[Dict[str, Any]] = None,
                           limit: int = 20, offset: int = 0) -> tuple[List[Dict[str, Any]], int]:
        """Find stations with pagination support.
        
        Args:
            filter_dict: MongoDB filter criteria (default: all stations)
            limit: Maximum number of stations to return
            offset: Number of stations to skip
            
        Returns:
            Tuple of (stations_list, total_count)
        """
        if filter_dict is None:
            filter_dict = {}
            
        try:
            # Get total count for pagination metadata
            total_count = self.collection.count_documents(filter_dict)
            
            # Get paginated results
            cursor = self.collection.find(filter_dict)
            cursor = cursor.skip(offset).limit(limit)
            stations = list(cursor)
            
            return stations, total_count
        except PyMongoError as e:
            logger.error(f"Error finding stations with pagination: {e}")
            raise


class ReadingsRepository(BaseRepository):
    """Repository for air quality readings."""
    
    def __init__(self):
        super().__init__('waqi_station_readings')
    
    def find_latest_by_station(self, station_id: str, 
                              limit: int = 10) -> List[Dict[str, Any]]:
        """Find latest readings for a station.
        
        Args:
            station_id: Station identifier
            limit: Maximum number of readings to return
            
        Returns:
            List of recent readings, newest first
        """
        return self.find_many(
            {'station_id': station_id},
            limit=limit,
            sort=[('timestamp', -1)]
        )
    
    def find_by_time_range(self, station_id: str, 
                          start_time: datetime, 
                          end_time: datetime) -> List[Dict[str, Any]]:
        """Find readings within a time range.
        
        Args:
            station_id: Station identifier
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            List of readings in time range
        """
        return self.find_many({
            'station_id': station_id,
            'timestamp': {
                '$gte': start_time,
                '$lte': end_time
            }
        }, sort=[('timestamp', 1)])
    
    def find_by_aqi_range(self, min_aqi: int, max_aqi: int) -> List[Dict[str, Any]]:
        """Find readings within AQI range.
        
        Args:
            min_aqi: Minimum AQI value
            max_aqi: Maximum AQI value
            
        Returns:
            List of readings in AQI range
        """
        return self.find_many({
            'aqi': {
                '$gte': min_aqi,
                '$lte': max_aqi
            }
        })


class ForecastsRepository(BaseRepository):
    """Repository for air quality forecasts."""
    
    def __init__(self):
        super().__init__('waqi_daily_forecasts')
    
    def find_latest_forecast(self, station_id: str) -> Optional[Dict[str, Any]]:
        """Find latest forecast for a station.
        
        Args:
            station_id: Station identifier
            
        Returns:
            Latest forecast if found
        """
        results = self.find_many(
            {'station_id': station_id},
            limit=1,
            sort=[('forecast_date', -1)]
        )
        return results[0] if results else None
    
    def find_forecasts_by_date(self, forecast_date: datetime) -> List[Dict[str, Any]]:
        """Find all forecasts for a specific date.
        
        Args:
            forecast_date: Date to find forecasts for
            
        Returns:
            List of forecasts for the date
        """
        # Match date only, ignoring time
        start_of_day = forecast_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = forecast_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return self.find_many({
            'forecast_date': {
                '$gte': start_of_day,
                '$lte': end_of_day
            }
        })


class UsersRepository(BaseRepository):
    """Repository for user accounts."""
    
    def __init__(self):
        super().__init__('users')
    
    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find user by email address.
        
        Args:
            email: User email address
            
        Returns:
            User document if found
        """
        return self.find_one({'email': email.lower()})
    
    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Find user by username.
        
        Args:
            username: Username
            
        Returns:
            User document if found
        """
        return self.find_one({'username': username.lower()})
    
    def create_user(self, user_data: Dict[str, Any]) -> ObjectId:
        """Create a new user account.
        
        Args:
            user_data: User account data
            
        Returns:
            Created user ID
            
        Raises:
            DuplicateKeyError: If email or username already exists
        """
        # Normalize email and username
        user_data['email'] = user_data['email'].lower()
        user_data['username'] = user_data['username'].lower()
        user_data['created_at'] = datetime.now(timezone.utc)
        
        try:
            return self.insert_one(user_data)
        except DuplicateKeyError as e:
            logger.warning(f"Duplicate user creation attempt: {e}")
            raise


# Repository instances for easy import
stations_repo = StationsRepository()
readings_repo = ReadingsRepository()
forecasts_repo = ForecastsRepository()
users_repo = UsersRepository()
