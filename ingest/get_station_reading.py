"""
Current station reading ingestion script.

Purpose: Fetch current air quality readings for all stations and save to MongoDB.
Uses checkpoint mechanism to avoid duplicate data insertion.

Strategy:
- Check previous checkpoint to avoid time duplication
- Fetch current data for all stations from database
- Save checkpoint for current time
- Save fetched data to database according to station_reading format

Usage:
    python ingest/get_station_reading.py [--dry-run] [--log-level DEBUG]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from ingest.aqicn_client import create_client_from_env, AqicnClientError, AqicnClient
from ingest.mongo_utils import upsert_readings


def load_env_file():
    """Load environment variables manually from .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value


def setup_logging(level: str = 'INFO') -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def normalize_hour(dt: datetime) -> datetime:
    """Normalize datetime to hour precision (remove minutes, seconds, microseconds)."""
    return dt.replace(minute=0, second=0, microsecond=0)


def parse_waqi_time_to_utc(time_data: Dict[str, Any]) -> Optional[datetime]:
    """
    Parse WAQI time data to UTC datetime.
    
    Args:
        time_data: Time data from WAQI API containing 's' (time string) and 'tz' (timezone)
        
    Returns:
        UTC datetime or None if parsing fails
    """
    if not isinstance(time_data, dict):
        return None
    
    time_s = time_data.get('s')
    time_tz = time_data.get('tz')
    
    if not time_s:
        return None
    
    try:
        # Parse the time string
        dt = datetime.strptime(time_s, '%Y-%m-%d %H:%M:%S')
        
        # Apply timezone offset if available
        if time_tz:
            # Parse timezone offset like "+07:00" or "-05:00"
            if time_tz.startswith(('+', '-')):
                sign = 1 if time_tz.startswith('+') else -1
                hours, minutes = map(int, time_tz[1:].split(':'))
                offset = timedelta(hours=sign * hours, minutes=sign * minutes)
                # Convert to UTC
                dt = dt - offset
        
        return dt.replace(tzinfo=timezone.utc)
        
    except (ValueError, TypeError) as e:
        logging.getLogger(__name__).warning(f"Failed to parse time data {time_data}: {e}")
        return None


def transform_to_waqi_reading(station_data: Dict[str, Any], station_idx: int) -> Optional[Dict[str, Any]]:
    """
    Transform WAQI API response to waqi_station_readings format.
    
    Args:
        station_data: Station data from WAQI API
        station_idx: Station index
        
    Returns:
        Transformed reading document or None if invalid data
    """
    if not isinstance(station_data, dict):
        return None
    
    # Extract AQI value
    aqi = station_data.get('aqi')
    if aqi is None:
        return None
    
    # Extract time data
    time_data = station_data.get('time', {})
    
    # Parse timestamp to UTC
    ts = parse_waqi_time_to_utc(time_data)
    if ts is None:
        # Fallback to current time if time parsing fails
        ts = datetime.now(timezone.utc)
    
    # Normalize to hour precision
    ts = normalize_hour(ts)
    
    # Build the reading document
    reading = {
        'ts': ts,
        'meta': {
            'station_idx': station_idx
        },
        'aqi': aqi,
        'time': time_data
    }
    
    # Add individual pollutant data if available
    iaqi = station_data.get('iaqi', {})
    if iaqi:
        reading['iaqi'] = iaqi
    
    return reading


class CurrentReadingManager:
    """
    Manager for fetching current station readings and handling checkpoints.
    
    Features:
    - Checkpoint mechanism to avoid duplicate data
    - Batch processing for all stations
    - Comprehensive error handling and logging
    - Dry run mode for testing
    """
    
    def __init__(
        self,
        mongo_uri: str,
        mongo_db: str,
        aqicn_client: AqicnClient,
        dry_run: bool = False
    ):
        """
        Initialize the current reading manager.
        
        Args:
            mongo_uri: MongoDB connection string
            mongo_db: Database name
            aqicn_client: AQICN API client instance
            dry_run: If True, don't actually insert data to database
        """
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.aqicn_client = aqicn_client
        self.dry_run = dry_run
        
        # MongoDB connections
        self.client: Optional[MongoClient] = None
        self.db = None
        self.stations_collection: Optional[Collection] = None
        self.readings_collection: Optional[Collection] = None
        self.checkpoints_collection: Optional[Collection] = None
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Collection names
        self.CHECKPOINT_COLLECTION = 'current_reading_checkpoints'
        self.STATIONS_COLLECTION = 'waqi_stations'
        self.READINGS_COLLECTION = 'waqi_station_readings'
    
    def connect_database(self) -> bool:
        """Connect to MongoDB database and initialize collections."""
        try:
            self.logger.info(f"Connecting to MongoDB: {self.mongo_db}")
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.mongo_db]
            
            # Initialize collections
            self.stations_collection = self.db[self.STATIONS_COLLECTION]
            self.readings_collection = self.db[self.READINGS_COLLECTION]
            self.checkpoints_collection = self.db[self.CHECKPOINT_COLLECTION]
            
            self.logger.info(f"Connected to database: {self.mongo_db}")
            return True
            
        except ConnectionFailure as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected database connection error: {e}")
            return False
    
    def disconnect_database(self) -> None:
        """Close database connection."""
        if self.client:
            self.client.close()
            self.logger.info("Database connection closed")
    
    def get_last_checkpoint(self) -> Optional[datetime]:
        """
        Get the timestamp of the last checkpoint.
        
        Returns:
            UTC datetime of last checkpoint or None if no checkpoint exists
        """
        try:
            checkpoint = self.checkpoints_collection.find_one(
                {},
                sort=[('timestamp', -1)]
            )
            if checkpoint:
                ts = checkpoint.get('timestamp')
                if isinstance(ts, datetime):
                    return ts.astimezone(timezone.utc)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get last checkpoint: {e}")
            return None

    def save_checkpoint(self, timestamp: datetime, stats: Dict[str, Any]) -> bool:
        """
        Save a checkpoint with the current timestamp and statistics.
        
        Args:
            timestamp: UTC timestamp of the checkpoint
            stats: Statistics about the ingestion run
            
        Returns:
            True if checkpoint was saved successfully
        """
        try:
            checkpoint_doc = {
                'timestamp': timestamp,
                'created_at': datetime.now(timezone.utc),
                'stats': stats
            }
            
            if not self.dry_run:
                self.checkpoints_collection.insert_one(checkpoint_doc)
                self.logger.info(f"Checkpoint saved: {timestamp}")
            else:
                self.logger.info(f"(dry-run) Would save checkpoint: {timestamp}")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")
            return False
    
    def should_skip_ingestion(self, current_time: datetime) -> bool:
        """
        Check if ingestion should be skipped based on last checkpoint.
        
        Args:
            current_time: Current normalized time
            
        Returns:
            True if ingestion should be skipped
        """
        last_checkpoint = self.get_last_checkpoint()
        
        if last_checkpoint is None:
            self.logger.info("No previous checkpoint found, proceeding with ingestion")
            return False
        
        # Compare normalized hours
        last_hour = normalize_hour(last_checkpoint)
        current_hour = normalize_hour(current_time)
        
        if last_hour >= current_hour:
            self.logger.info(
                f"Skipping ingestion: last checkpoint {last_hour} >= current time {current_hour}"
            )
            return True
        
        self.logger.info(
            f"Proceeding with ingestion: last checkpoint {last_hour} < current time {current_hour}"
        )
        return False
    
    def get_all_stations(self) -> List[Dict[str, Any]]:
        """
        Get all stations from the database.
        
        Returns:
            List of station documents
        """
        try:
            stations = list(self.stations_collection.find(
                {},
                {'_id': 1, 'city.name': 1}
            ))
            self.logger.info(f"Found {len(stations)} stations in database")
            return stations
        except Exception as e:
            self.logger.error(f"Failed to get stations: {e}")
            return []
    
    def fetch_station_current_data(self, station_idx: int) -> Optional[Dict[str, Any]]:
        """
        Fetch current data for a single station.
        
        Args:
            station_idx: Station index
            
        Returns:
            Station data from API or None if failed
        """
        try:
            # Use the AQICN client to get current station info
            station_info = self.aqicn_client.get_station_info(station_idx)
            
            # Transform to the format expected by fetch_hourly
            if station_info:
                # Get the full station data using fetch_hourly which includes current reading
                full_data = self.aqicn_client.fetch_hourly(station_idx)
                if full_data and 'current_aqi' in full_data:
                    return {
                        'aqi': full_data['current_aqi'],
                        'time': {
                            's': full_data.get('current_time', ''),
                            'tz': full_data.get('timezone', '')
                        },
                        'iaqi': full_data.get('current_iaqi', {})
                    }
            
            return None
            
        except AqicnClientError as e:
            self.logger.warning(f"Failed to fetch data for station {station_idx}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching station {station_idx}: {e}")
            return None
    
    def process_all_stations(self, normalized_time: datetime) -> Dict[str, Any]:
        """
        Process all stations to fetch current readings.
        
        Args:
            normalized_time: The normalized current time for checking duplicates
        
        Returns:
            Statistics about the processing
        """
        stations = self.get_all_stations()
        if not stations:
            return {
                'total_stations': 0,
                'successful_stations': 0,
                'failed_stations': 0,
                'total_readings': 0
            }
        
        stats = {
            'total_stations': len(stations),
            'successful_stations': 0,
            'failed_stations': 0,
            'total_readings': 0,
            'failed_station_ids': []
        }
        
        self.logger.info(f"Processing {len(stations)} stations")
        
        for station in stations:
            station_idx = station.get('_id')
            station_name = station.get('city', {}).get('name', 'Unknown')
            
            if station_idx is None:
                self.logger.warning(f"Station missing _id: {station}")
                stats['failed_stations'] += 1
                continue
            
            self.logger.debug(f"Processing station {station_idx}: {station_name}")
            
            # Check if data already exists for this station using time-based duplicate detection
            station_data = self.fetch_station_current_data(station_idx)
            
            if station_data is None:
                self.logger.warning(f"No data received for station {station_idx}")
                stats['failed_stations'] += 1
                stats['failed_station_ids'].append(station_idx)
                continue
            
            # Transform to reading format
            reading = transform_to_waqi_reading(station_data, station_idx)
            
            if reading is None:
                self.logger.warning(f"Failed to transform data for station {station_idx}")
                stats['failed_stations'] += 1
                stats['failed_station_ids'].append(station_idx)
                continue
            
            # Use safe insert with enhanced duplicate prevention
            if self.safe_insert_reading(station_idx, reading):
                stats['successful_stations'] += 1
                stats['total_readings'] += 1
                self.logger.debug(f"Successfully processed station {station_idx}")
            else:
                stats['failed_stations'] += 1
                stats['failed_station_ids'].append(station_idx)
                
        return stats
            
    def update_station_latest_time(self, station_idx: int, time_data: Dict[str, str]) -> None:
        """
        Update latest_update_time field in waqi_stations collection.
        
        Args:
            station_idx: Station ID
            time_data: Time data from reading (e.g., {'s': '2025-09-11 12:00:00', 'tz': '+07:00'})
        """
        try:
            self.stations_collection.update_one(
                {'_id': station_idx},
                {'$set': {'latest_update_time': time_data}},
                upsert=False
            )
            self.logger.debug(f"Updated latest_update_time for station {station_idx}: {time_data}")
        except Exception as e:
            self.logger.warning(f"Failed to update latest_update_time for station {station_idx}: {e}")

    def check_station_time_duplicate(self, station_idx: int, time_data: Dict[str, str]) -> bool:
        """
        Check if station already has data for this time by comparing with latest_update_time.
        
        Args:
            station_idx: Station ID
            time_data: Time data from reading (e.g., {'s': '2025-09-11 12:00:00', 'tz': '+07:00'})
            
        Returns:
            True if duplicate (should skip), False if new data (should insert)
        """
        try:
            station = self.stations_collection.find_one({'_id': station_idx})
            if not station:
                self.logger.warning(f"Station {station_idx} not found in stations collection")
                return False
            
            latest_time = station.get('latest_update_time')
            if not latest_time:
                # No previous data, this is first time - should insert
                self.logger.debug(f"Station {station_idx} has no latest_update_time, allowing insert")
                return False
            
            # Compare time data
            if (latest_time.get('s') == time_data.get('s') and 
                latest_time.get('tz') == time_data.get('tz')):
                self.logger.debug(f"Station {station_idx} already has data for time {time_data}, skipping")
                return True
            else:
                self.logger.debug(f"Station {station_idx} has new time data {time_data} vs latest {latest_time}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error checking station time duplicate for {station_idx}: {e}")
            return False

    def safe_insert_reading(self, station_idx: int, reading: Dict[str, Any]) -> bool:
        """
        Safely insert a reading with station-level time duplicate prevention.
        
        Returns:
            True if successfully inserted, False if duplicate or failed
        """
        try:
            # Check if station already has this time data
            time_data = reading.get('time', {})
            if self.check_station_time_duplicate(station_idx, time_data):
                self.logger.debug(f"Station {station_idx} time duplicate detected, skipping insert")
                return False
            
            if not self.dry_run:
                # Use insert_one with error handling for duplicates
                try:
                    result = self.readings_collection.insert_one(reading)
                    if result.inserted_id:
                        # Update station's latest_update_time after successful insert
                        self.update_station_latest_time(station_idx, time_data)
                        self.logger.debug(f"Successfully inserted reading for station {station_idx}")
                        return True
                    else:
                        self.logger.warning(f"Insert failed for station {station_idx}")
                        return False
                        
                except DuplicateKeyError:
                    self.logger.info(f"Duplicate key prevented insertion for station {station_idx}")
                    return False
                except Exception as e:
                    self.logger.error(f"Insert error for station {station_idx}: {e}")
                    return False
            else:
                # For dry-run, also update the latest time to simulate real behavior
                self.update_station_latest_time(station_idx, time_data)
                self.logger.info(f"(dry-run) Would insert reading for station {station_idx}")
                return True
                
        except Exception as e:
            self.logger.error(f"Safe insert failed for station {station_idx}: {e}")
            return False

    def reset_all_stations_update_time(self) -> bool:
        """
        Reset latest_update_time field for all stations to allow full data reload.
        
        Returns:
            True if reset was successful
        """
        try:
            if not self.dry_run:
                result = self.stations_collection.update_many(
                    {},  # Update all stations
                    {'$unset': {'latest_update_time': ''}}  # Remove the field
                )
                self.logger.info(f"Reset latest_update_time for {result.modified_count} stations")
                return True
            else:
                count = self.stations_collection.count_documents({})
                self.logger.info(f"(dry-run) Would reset latest_update_time for {count} stations")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to reset stations update time: {e}")
            return False
    
    def run(self, reset_stations: bool = False) -> bool:
        """
        Main execution method.
        
        Args:
            reset_stations: If True, reset all stations latest_update_time before processing
        
        Returns:
            True if execution was successful
        """
        try:
            # Connect to database
            if not self.connect_database():
                return False
            
            # Reset stations if requested
            if reset_stations:
                self.logger.info("Resetting all stations latest_update_time...")
                if not self.reset_all_stations_update_time():
                    self.logger.error("Failed to reset stations, aborting")
                    return False
                self.logger.info("Successfully reset all stations latest_update_time")
            
            # Get current time and normalize to hour
            current_time = datetime.now(timezone.utc)
            normalized_time = normalize_hour(current_time)
            
            self.logger.info(f"Starting current reading ingestion at {normalized_time}")
            
            # Check if we should skip this run (unless resetting stations)
            if not reset_stations and self.should_skip_ingestion(normalized_time):
                return True
            
            # Process all stations
            stats = self.process_all_stations(normalized_time)
            
            # Save checkpoint
            self.save_checkpoint(normalized_time, stats)
            
            # Log summary
            self.logger.info(
                f"Ingestion completed: {stats['successful_stations']}/{stats['total_stations']} "
                f"stations successful, {stats['total_readings']} readings processed"
            )
            
            if stats['failed_stations'] > 0:
                self.logger.warning(
                    f"Failed stations: {stats['failed_station_ids'][:10]}"
                    + ("..." if len(stats['failed_station_ids']) > 10 else "")
                )
            
            return stats['failed_stations'] == 0
            
        except Exception as e:
            self.logger.error(f"Unexpected error during execution: {e}")
            return False
        finally:
            self.disconnect_database()


def main():
    """Main function to run current reading ingestion."""
    parser = argparse.ArgumentParser(description='Fetch current station readings and save to MongoDB')
    parser.add_argument('--dry-run', action='store_true', help='Run without inserting data')
    parser.add_argument('--reset-stations', action='store_true', 
                       help='Reset all stations latest_update_time to allow full data reload')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Load environment variables
    load_env_file()
    
    # Validate required environment variables
    mongo_uri = os.environ.get('MONGO_URI')
    mongo_db = os.environ.get('MONGO_DB', 'air_quality_db')
    
    if not mongo_uri:
        logger.error("MONGO_URI environment variable is required")
        sys.exit(1)
    
    try:
        # Create AQICN client
        aqicn_client = create_client_from_env()
        
        # Create and run current reading manager
        manager = CurrentReadingManager(
            mongo_uri=mongo_uri,
            mongo_db=mongo_db,
            aqicn_client=aqicn_client,
            dry_run=args.dry_run
        )
        
        success = manager.run(reset_stations=args.reset_stations)
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Failed to run current reading ingestion: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()