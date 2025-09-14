"""Forecast data ingestion service with intelligent upsert strategy.

Purpose: Fetch daily forecasts from AQICN API for all stations and merge into MongoDB
with conditional updates based on data changes and last run timestamps.

Key decisions:
- Merge all forecast.daily arrays (pm25/pm10/o3/uvi) by day key
- Normalize days to YYYY-MM-DD UTC format
- Use bulkWrite with conditional upserts for efficiency
- Track last_forecast_run_at to avoid unnecessary updates
- Compare pollutant values to detect actual changes

Extension points:
- Add forecast confidence scores when available
- Support additional pollutants as API expands
- Add forecast accuracy tracking over time
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError, PyMongoError

from aqicn_client import AqicnClient, AqicnClientError

logger = logging.getLogger(__name__)


class ForecastIngestError(Exception):
    """Exception for forecast ingestion errors."""
    pass


class ForecastIngestionService:
    """
    Service for ingesting daily air quality forecasts.
    
    Features:
    - Bulk forecast processing for all stations
    - Intelligent conditional updates based on data changes
    - Timestamp tracking to avoid redundant updates
    - Comprehensive error handling with per-station isolation
    """
    
    def __init__(self, client: Optional[AqicnClient] = None, database_name: Optional[str] = None):
        """Initialize forecast ingestion service.
        
        Args:
            client: AQICN API client (creates default if None)
            database_name: MongoDB database name (uses env if None)
        """
        self.client = client or self._create_default_client()
        self.database_name = database_name or os.environ.get('MONGO_DB', 'air_quality_db')
        
        # Create MongoDB connection
        mongo_uri = os.environ.get('MONGO_URI')
        if not mongo_uri:
            raise ForecastIngestError("MONGO_URI environment variable is required")
        
        self.mongo_client = MongoClient(mongo_uri)
        self.database = self.mongo_client[self.database_name]
        
        # Collections
        self.stations_collection = self.database['waqi_stations']
        self.forecasts_collection = self.database['waqi_daily_forecasts']
        
        logger.info(f"ForecastIngestionService initialized for database: {self.database_name}")
    
    @staticmethod
    def _create_default_client() -> AqicnClient:
        """Create default AQICN client from environment variables."""
        return AqicnClient(
            api_key=os.environ.get('AQICN_API_KEY'),
            base_url=os.environ.get('AQICN_API_URL', 'https://api.waqi.info'),
            rate_limit=int(os.environ.get('AQICN_RATE_LIMIT', '1000')),
            timeout=int(os.environ.get('AQICN_TIMEOUT', '30'))
        )
    
    def get_all_station_ids(self) -> List[int]:
        """Retrieve all station IDs from database.
        
        Returns:
            List of station IDs (idx values)
        """
        try:
            cursor = self.stations_collection.find({}, {'_id': 1})
            station_ids = [doc['_id'] for doc in cursor]
            logger.info(f"Retrieved {len(station_ids)} station IDs from database")
            return station_ids
        except PyMongoError as e:
            logger.error(f"Failed to retrieve station IDs: {e}")
            raise ForecastIngestError(f"Database query failed: {e}")
    
    def fetch_station_forecast_data(self, station_idx: int, 
                                   run_at: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Fetch and process forecast data for a single station.
        
        Args:
            station_idx: Station ID
            run_at: Timestamp for this ingestion run (default: now)
            
        Returns:
            Processed forecast data or None if failed/no data
        """
        if run_at is None:
            run_at = datetime.now(timezone.utc)
            
        try:
            # Log station processing start
            logger.info(f"Fetching forecast data for station {station_idx}")
            
            # Fetch raw data from API
            raw_data = self.client._make_request(f"feed/@{station_idx}/")
            
            if 'data' not in raw_data:
                logger.warning(f"No data returned for station {station_idx}")
                return None
            
            station_data = raw_data['data']
            forecast_section = station_data.get('forecast', {})
            daily_section = forecast_section.get('daily', {})
            
            if not daily_section:
                logger.info(f"No daily forecasts available for station {station_idx}")
                return None
            
            # Extract run timestamp from debug.sync or use current time
            debug_sync = raw_data.get('data', {}).get('debug', {}).get('sync')
            if debug_sync:
                try:
                    # Parse various possible timestamp formats
                    if debug_sync.endswith('+09:00'):  # Japan timezone example
                        # Convert to UTC
                        import dateutil.parser
                        parsed_dt = dateutil.parser.parse(debug_sync)
                        run_at = parsed_dt.astimezone(timezone.utc)
                except Exception as e:
                    logger.warning(f"Could not parse debug.sync timestamp '{debug_sync}': {e}")
            
            # Merge all pollutant arrays by day
            merged_forecasts = self._merge_daily_forecasts(daily_section)
            
            if not merged_forecasts:
                logger.info(f"No valid forecast days found for station {station_idx}")
                return None
            
            return {
                'station_idx': station_idx,
                'forecasts': merged_forecasts,
                'run_at': run_at,
                'fetched_at': datetime.now(timezone.utc)
            }
            
        except AqicnClientError as e:
            logger.error(f"API error fetching forecast for station {station_idx}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching forecast for station {station_idx}: {e}")
            return None
    
    def _merge_daily_forecasts(self, daily_section: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Merge forecast arrays by day key.
        
        Args:
            daily_section: Raw daily forecast data from API
            
        Returns:
            List of merged forecast documents by day
        """
        # Collect all unique days across all pollutants
        all_days: Set[str] = set()
        for pollutant_data in daily_section.values():
            if isinstance(pollutant_data, list):
                for entry in pollutant_data:
                    if isinstance(entry, dict) and 'day' in entry:
                        # Normalize day format to YYYY-MM-DD
                        day = self._normalize_day_format(entry['day'])
                        if day:
                            all_days.add(day)
        
        merged_forecasts = []
        
        for day in sorted(all_days):
            day_data = {
                'day': day,
                'pollutants': {}
            }
            
            # Collect pollutant data for this day
            for pollutant_name, pollutant_data in daily_section.items():
                if not isinstance(pollutant_data, list):
                    continue
                    
                # Find entry for this day
                for entry in pollutant_data:
                    if not isinstance(entry, dict):
                        continue
                        
                    entry_day = self._normalize_day_format(entry.get('day', ''))
                    if entry_day == day:
                        # Extract avg/min/max values
                        pollutant_values = {}
                        for key in ['avg', 'min', 'max']:
                            value = entry.get(key)
                            if value is not None:
                                pollutant_values[key] = value
                        
                        if pollutant_values:
                            day_data['pollutants'][pollutant_name] = pollutant_values
                        break
            
            # Only include days with at least one pollutant
            if day_data['pollutants']:
                merged_forecasts.append(day_data)
        
        return merged_forecasts
    
    @staticmethod
    def _normalize_day_format(day_str: str) -> Optional[str]:
        """Normalize day string to YYYY-MM-DD UTC format.
        
        Args:
            day_str: Input day string (e.g., "2025-09-13")
            
        Returns:
            Normalized day string or None if invalid
        """
        if not isinstance(day_str, str):
            return None
            
        try:
            # Parse date and convert to YYYY-MM-DD
            from datetime import datetime
            parsed_date = datetime.fromisoformat(day_str.split('T')[0])  # Handle ISO format
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            logger.warning(f"Could not parse day format: {day_str}")
            return None
    
    def get_existing_forecasts(self, station_idx: int, days: List[str]) -> Dict[str, Dict[str, Any]]:
        """Retrieve existing forecast documents for given station and days.
        
        Args:
            station_idx: Station ID
            days: List of day strings (YYYY-MM-DD format)
            
        Returns:
            Dictionary mapping day -> existing document
        """
        try:
            query = {
                'station_idx': station_idx,
                'day': {'$in': days}
            }
            
            cursor = self.forecasts_collection.find(query)
            existing = {}
            
            for doc in cursor:
                day = doc.get('day')
                if day:
                    existing[day] = doc
            
            logger.debug(f"Found {len(existing)} existing forecasts for station {station_idx}")
            return existing
            
        except PyMongoError as e:
            logger.error(f"Failed to query existing forecasts: {e}")
            return {}
    
    def should_update_forecast(self, existing_doc: Dict[str, Any], 
                             new_pollutants: Dict[str, Any],
                             run_at: datetime) -> bool:
        """Determine if forecast document should be updated.
        
        Args:
            existing_doc: Current document in database
            new_pollutants: New pollutant data
            run_at: Current ingestion run timestamp
            
        Returns:
            True if document should be updated
        """
        existing_pollutants = existing_doc.get('pollutants', {})
        last_run_at = existing_doc.get('last_forecast_run_at')
        
        # Check if pollutant data has changed
        pollutants_changed = self._pollutants_different(existing_pollutants, new_pollutants)
        
        if last_run_at:
            # Only update if run_at > last_forecast_run_at OR pollutants changed
            if isinstance(last_run_at, datetime):
                # Ensure both timestamps are timezone-aware for comparison
                if last_run_at.tzinfo is None:
                    last_run_at = last_run_at.replace(tzinfo=timezone.utc)
                if run_at.tzinfo is None:
                    run_at = run_at.replace(tzinfo=timezone.utc)
                return run_at > last_run_at or pollutants_changed
            else:
                # Handle case where last_run_at is not datetime
                return pollutants_changed
        else:
            # No last_forecast_run_at: only update if pollutants changed
            return pollutants_changed
    
    def _pollutants_different(self, existing: Dict[str, Any], new: Dict[str, Any]) -> bool:
        """Compare pollutant data to detect changes.
        
        Args:
            existing: Current pollutant data
            new: New pollutant data
            
        Returns:
            True if pollutants are different
        """
        # Get all unique pollutant keys
        all_keys = set(existing.keys()) | set(new.keys())
        
        for pollutant in all_keys:
            existing_vals = existing.get(pollutant, {})
            new_vals = new.get(pollutant, {})
            
            # Compare avg/min/max values
            for metric in ['avg', 'min', 'max']:
                existing_val = existing_vals.get(metric)
                new_val = new_vals.get(metric)
                
                # Consider different if one is None and other isn't, or values differ
                if (existing_val is None) != (new_val is None):
                    return True
                if existing_val is not None and new_val is not None:
                    if abs(existing_val - new_val) > 1e-6:  # Small float tolerance
                        return True
        
        return False
    
    def build_forecast_upsert_operations(self, forecast_data: Dict[str, Any]) -> List[UpdateOne]:
        """Build bulk write operations for forecast upserts.
        
        Args:
            forecast_data: Processed forecast data from fetch_station_forecast_data
            
        Returns:
            List of UpdateOne operations for bulk write
        """
        station_idx = forecast_data['station_idx']
        forecasts = forecast_data['forecasts']
        run_at = forecast_data['run_at']
        fetched_at = forecast_data['fetched_at']
        
        # Get all days for this station
        days = [f['day'] for f in forecasts]
        existing_forecasts = self.get_existing_forecasts(station_idx, days)
        
        operations = []
        
        for forecast in forecasts:
            day = forecast['day']
            new_pollutants = forecast['pollutants']
            
            # Check if update is needed
            existing_doc = existing_forecasts.get(day)
            if existing_doc and not self.should_update_forecast(existing_doc, new_pollutants, run_at):
                logger.debug(f"Skipping update for station {station_idx}, day {day} - no changes")
                continue
            
            # Prepare document for upsert
            update_doc = {
                'station_idx': station_idx,
                'day': day,
                'pollutants': new_pollutants,
                'fetched_at': fetched_at,
                'last_forecast_run_at': run_at
            }
            
            filter_query = {
                'station_idx': station_idx,
                'day': day
            }
            
            operation = UpdateOne(
                filter_query,
                {'$set': update_doc},
                upsert=True
            )
            operations.append(operation)
        
        logger.debug(f"Built {len(operations)} upsert operations for station {station_idx}")
        return operations
    
    def bulk_upsert_forecasts(self, operations: List[UpdateOne]) -> Dict[str, int]:
        """Execute bulk write operations for forecast upserts.
        
        Args:
            operations: List of UpdateOne operations
            
        Returns:
            Dictionary with operation counts
        """
        if not operations:
            return {'matched': 0, 'modified': 0, 'upserted': 0}
        
        try:
            result = self.forecasts_collection.bulk_write(operations, ordered=False)
            
            counts = {
                'matched': result.matched_count,
                'modified': result.modified_count,
                'upserted': result.upserted_count
            }
            
            logger.info(f"Bulk forecast upsert completed: {counts}")
            return counts
            
        except BulkWriteError as e:
            logger.error(f"Bulk write error: {e.details}")
            raise ForecastIngestError(f"Bulk upsert failed: {e}")
        except PyMongoError as e:
            logger.error(f"Database error during bulk upsert: {e}")
            raise ForecastIngestError(f"Database operation failed: {e}")
    
    def ingest_forecasts_for_station(self, station_idx: int, 
                                   run_at: Optional[datetime] = None) -> Dict[str, Any]:
        """Ingest forecasts for a single station.
        
        Args:
            station_idx: Station ID
            run_at: Ingestion run timestamp
            
        Returns:
            Dictionary with ingestion results
        """
        logger.info(f"Ingesting forecasts for station {station_idx}")
        
        try:
            # Fetch forecast data
            forecast_data = self.fetch_station_forecast_data(station_idx, run_at)
            
            if not forecast_data:
                return {
                    'station_idx': station_idx,
                    'success': False,
                    'reason': 'No forecast data available',
                    'forecasts_processed': 0
                }
            
            # Build upsert operations
            operations = self.build_forecast_upsert_operations(forecast_data)
            
            if not operations:
                return {
                    'station_idx': station_idx,
                    'success': True,
                    'reason': 'No updates needed - all forecasts current',
                    'forecasts_processed': 0
                }
            
            # Execute bulk upsert
            counts = self.bulk_upsert_forecasts(operations)
            
            return {
                'station_idx': station_idx,
                'success': True,
                'forecasts_processed': len(operations),
                'matched': counts['matched'],
                'modified': counts['modified'],
                'upserted': counts['upserted']
            }
            
        except Exception as e:
            logger.error(f"Failed to ingest forecasts for station {station_idx}: {e}")
            return {
                'station_idx': station_idx,
                'success': False,
                'reason': str(e),
                'forecasts_processed': 0
            }
    
    def ingest_all_station_forecasts(self, run_at: Optional[datetime] = None) -> Dict[str, Any]:
        """Ingest forecasts for all stations in database.
        
        Args:
            run_at: Ingestion run timestamp (default: current time)
            
        Returns:
            Dictionary with overall ingestion results
        """
        if run_at is None:
            run_at = datetime.now(timezone.utc)
        
        logger.info(f"Starting forecast ingestion for all stations at {run_at}")
        
        try:
            # Get all station IDs
            station_ids = self.get_all_station_ids()
            
            if not station_ids:
                logger.warning("No stations found in database")
                return {
                    'success': True,
                    'total_stations': 0,
                    'successful_stations': 0,
                    'failed_stations': 0,
                    'total_forecasts_processed': 0,
                    'stations_results': []
                }
            
            # Log total station count like station reading does
            logger.info(f"Processing forecast data for {len(station_ids)} stations")
            
            results = {
                'success': True,
                'run_at': run_at,
                'total_stations': len(station_ids),
                'successful_stations': 0,
                'failed_stations': 0,
                'total_forecasts_processed': 0,
                'stations_results': []
            }
            
            # Process each station
            for station_idx in station_ids:
                station_result = self.ingest_forecasts_for_station(station_idx, run_at)
                results['stations_results'].append(station_result)
                
                if station_result['success']:
                    results['successful_stations'] += 1
                    results['total_forecasts_processed'] += station_result['forecasts_processed']
                else:
                    results['failed_stations'] += 1
            
            logger.info(
                f"Forecast ingestion completed: {results['successful_stations']}/{results['total_stations']} "
                f"stations successful, {results['total_forecasts_processed']} forecasts processed"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Critical error during forecast ingestion: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_stations': 0,
                'successful_stations': 0,
                'failed_stations': 0,
                'total_forecasts_processed': 0,
                'stations_results': []
            }