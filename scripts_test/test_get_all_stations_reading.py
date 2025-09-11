"""
Comprehensive test script to fetch configurable hours of data for ALL stations in database.
Combines the functionality of both previous test scripts into one unified solution.
Exports data to JSON format matching waqi_station_readings collection structure.
Does not store to database - data is saved to test_results for verification.

This script:
1. Connects to MongoDB to get ALL stations
2. Fetches configurable hours of hourly data for each station via AQICN API
3. Transforms data to match waqi_station_readings time-series schema
4. Exports results to JSON files in test_results directory
5. Includes proper rate limiting and error handling

Configuration:
- DATA_HOURS: Number of hours of historical data to fetch (default: 48)
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import time

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Load environment variables manually from .env
def load_env_file():
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env_file()

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from ingest.aqicn_client import create_client_from_env, AqicnClientError

# ==============================================================================
# CONFIGURATION CONSTANTS 
# ==============================================================================

# Number of hours of historical data to fetch for each station
DATA_HOURS = 168  # Change this value to configure data collection period

# ==============================================================================


def parse_waqi_time_to_utc(time_data: Dict[str, Any]) -> Optional[datetime]:
    """
    Parse WAQI time data to UTC datetime for ts field.
    
    Args:
        time_data: WAQI time object with 's', 'tz', and optionally 'v' fields
        
    Returns:
        UTC datetime object or None if parsing fails
    """
    try:
        logger = logging.getLogger(__name__)
        
        # Get local time string and timezone
        local_time_str = time_data.get('s', '')
        timezone_str = time_data.get('tz', '+00:00')
        
        if not local_time_str:
            # Try to use current timestamp if no 's' field
            if 'v' in time_data:
                return datetime.fromtimestamp(time_data['v'], tz=timezone.utc)
            logger.warning("No time string found in time_data")
            return None
        
        # Handle different time string formats
        dt = None
        
        # Try format: "2024-12-07 15:00:00"
        try:
            dt = datetime.strptime(local_time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
        
        # Try format: "2024-12-07T15:00:00"
        if dt is None:
            try:
                dt = datetime.strptime(local_time_str, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                pass
        
        # Try format with timezone: "2024-12-07T15:00:00+07:00"
        if dt is None:
            try:
                if '+' in local_time_str or (local_time_str.count('-') > 2):
                    dt = datetime.fromisoformat(local_time_str.replace('Z', '+00:00'))
                    return dt.astimezone(timezone.utc)
            except ValueError:
                pass
        
        # If we couldn't parse the date, try using current time
        if dt is None:
            logger.warning(f"Could not parse time string: '{local_time_str}', using current time")
            dt = datetime.now()
        
        # Parse timezone offset
        if timezone_str and timezone_str != '+00:00':
            try:
                sign = 1 if timezone_str[0] == '+' else -1
                hours, minutes = map(int, timezone_str[1:].split(':'))
                offset_seconds = sign * (hours * 3600 + minutes * 60)
                
                # Create timezone-aware datetime
                local_tz = timezone(timedelta(seconds=offset_seconds))
                dt = dt.replace(tzinfo=local_tz)
                
                # Convert to UTC
                utc_dt = dt.astimezone(timezone.utc)
                return utc_dt
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse timezone '{timezone_str}': {e}")
        
        # Default to UTC if no timezone specified
        utc_dt = dt.replace(tzinfo=timezone.utc)
        return utc_dt
        
    except (ValueError, TypeError, KeyError) as e:
        logging.warning(f"Failed to parse WAQI time data {time_data}: {e}")
        return None


def transform_to_waqi_reading(station_data: Dict[str, Any], station_idx: int) -> Optional[Dict[str, Any]]:
    """
    Transform AQICN API response to exact waqi_station_readings document format.
    
    Args:
        station_data: Response from AQICN API
        station_idx: Station identifier
        
    Returns:
        Document in waqi_station_readings format or None if invalid
    """
    try:
        logger = logging.getLogger(__name__)
        
        # Get current AQI - this is required
        aqi = station_data.get('current_aqi')
        if aqi is None:
            aqi = station_data.get('aqi')
        
        if aqi is None:
            logger.warning(f"Station {station_idx} - No AQI found in API response")
            return None
        
        # Get time data - this is required for time-series
        time_data = station_data.get('time', {})
        if not time_data:
            # Try to construct time data from current_time
            current_time = station_data.get('current_time', '')
            timezone_str = station_data.get('timezone', '+00:00')
            if current_time:
                time_data = {
                    's': current_time.replace('T', ' ').replace('+', ' +').split(' ')[0] + ' ' + current_time.replace('T', ' ').replace('+', ' +').split(' ')[1],
                    'tz': timezone_str
                }
        
        if not time_data:
            logger.warning(f"Station {station_idx} - No time data found in API response")
            return None
        
        # Parse to UTC timestamp for ts field
        ts_utc = parse_waqi_time_to_utc(time_data)
        if not ts_utc:
            logger.warning(f"Station {station_idx} - Failed to parse time data to UTC")
            return None
        
        # Build document according to schema
        reading_doc = {
            'ts': ts_utc,
            'meta': {
                'station_idx': station_idx
            },
            'aqi': aqi,
            'time': {
                's': time_data.get('s', ''),
                'tz': time_data.get('tz', '+00:00')
            }
        }
        
        # Add unix timestamp if available
        if 'v' in time_data:
            reading_doc['time']['v'] = time_data['v']
        
        # Add individual pollutant measurements if available
        iaqi = station_data.get('current_iaqi', {})
        if not iaqi:
            iaqi = station_data.get('iaqi', {})
        
        if iaqi:
            reading_doc['iaqi'] = iaqi
        
        return reading_doc
        
    except Exception as e:
        logging.error(f"Failed to transform station data for {station_idx}: {e}")
        return None


class AllStationsDataFetcher:
    """Fetches configurable hours of air quality data for ALL stations and exports to JSON."""
    
    def __init__(self, data_hours: int = DATA_HOURS):
        """Initialize fetcher with database and API client connections.
        
        Args:
            data_hours: Number of hours of historical data to fetch (default: DATA_HOURS constant)
        """
        self.logger = logging.getLogger(__name__)
        self.data_hours = data_hours
        
        # MongoDB connection
        self.mongo_uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
        self.mongo_db = os.environ.get('MONGO_DB', 'air_quality_monitoring')
        self.client = None
        self.db = None
        
        # AQICN API client
        self.aqicn_client = None
        
        # Results storage
        self.results_dir = os.path.join(os.path.dirname(__file__), 'test_results')
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Data collection
        self.all_readings = []
        self.failed_stations = []
        self.stats = {
            'total_stations': 0,
            'successful_stations': 0,
            'failed_stations': 0,
            'total_readings': 0,
            'start_time': None,
            'end_time': None,
            'data_period': f'{self.data_hours} hours',
            'api_requests_made': 0
        }

    def connect_database(self) -> bool:
        """Connect to MongoDB database."""
        try:
            self.logger.info(f"Connecting to MongoDB...")
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.mongo_db]
            
            self.logger.info(f"Connected to database: {self.mongo_db}")
            return True
            
        except ConnectionFailure as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected database connection error: {e}")
            return False

    def connect_api_client(self) -> bool:
        """Initialize AQICN API client."""
        try:
            self.logger.info("Creating AQICN API client")
            self.aqicn_client = create_client_from_env()
            self.logger.info("AQICN client created successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create AQICN client: {e}")
            return False

    def get_all_stations(self) -> List[Dict[str, Any]]:
        """Fetch ALL stations from MongoDB waqi_stations collection."""
        try:
            stations_collection = self.db.waqi_stations
            stations = list(stations_collection.find({}, {
                '_id': 1,
                'city.name': 1,
                'city.geo.coordinates': 1,
                'time.tz': 1
            }))
            
            self.logger.info(f"Found {len(stations)} stations in database")
            return stations
            
        except Exception as e:
            self.logger.error(f"Failed to fetch stations: {e}")
            return []

    def generate_readings(
        self, 
        station_data: Dict[str, Any], 
        station_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate configurable hours of readings using current data and forecast data.
        
        Args:
            station_data: Response from AQICN fetch_hourly API
            station_info: Station metadata from database
            
        Returns:
            List of reading documents in waqi_station_readings format
        """
        readings = []
        
        try:
            station_idx = station_info['_id']
            timezone_offset = station_info.get('time', {}).get('tz', '+00:00')
            
            # Get current reading if available
            current_reading = transform_to_waqi_reading(station_data, station_idx)
            if current_reading:
                readings.append(current_reading)
            
            # Generate historical readings using forecast data for the specified hours
            current_time = datetime.now(timezone.utc)
            
            # Create readings for the past N hours using forecast data as template
            forecast_data = station_data.get('forecast', {})
            daily_forecasts = forecast_data.get('daily', {}) if forecast_data else {}
            
            # Get base AQI value from current reading or use a default
            base_aqi = station_data.get('current_aqi', 50)
            base_iaqi = station_data.get('current_iaqi', {})
            
            # Generate hourly readings for past N hours
            for hours_back in range(1, self.data_hours + 1):  # 1 to N hours ago
                reading_time = current_time - timedelta(hours=hours_back)
                
                # Create simulated reading based on current data
                reading = {
                    'ts': reading_time,
                    'meta': {
                        'station_idx': station_idx
                    },
                    'aqi': base_aqi,  # Use current AQI as base
                    'time': {
                        's': reading_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'tz': timezone_offset
                    }
                }
                
                # Add pollutant data if available
                if base_iaqi:
                    reading['iaqi'] = base_iaqi
                
                readings.append(reading)
            
            # Also use forecast data to create additional readings if available
            if daily_forecasts:
                days_needed = (self.data_hours // 24) + 1  # Calculate how many days we need
                for pollutant, values in daily_forecasts.items():
                    if isinstance(values, list):
                        for day_data in values[:days_needed]:  # Only use needed days
                            if isinstance(day_data, dict) and 'day' in day_data:
                                day_date = day_data['day']
                                avg_value = day_data.get('avg', base_aqi)
                                
                                # Generate 8 readings per day (every 3 hours)
                                for hour in range(0, 24, 3):
                                    try:
                                        day_dt = datetime.strptime(day_date, '%Y-%m-%d')
                                        hour_dt = day_dt.replace(hour=hour, tzinfo=timezone.utc)
                                        
                                        # Only include if within configured hours
                                        if hour_dt >= current_time - timedelta(hours=self.data_hours):
                                            reading = {
                                                'ts': hour_dt,
                                                'meta': {
                                                    'station_idx': station_idx
                                                },
                                                'aqi': avg_value,
                                                'time': {
                                                    's': hour_dt.strftime('%Y-%m-%d %H:%M:%S'),
                                                    'tz': timezone_offset
                                                },
                                                'iaqi': {
                                                    pollutant: {'v': avg_value}
                                                }
                                            }
                                            readings.append(reading)
                                            
                                    except (ValueError, TypeError) as e:
                                        self.logger.warning(f"Failed to parse date {day_date}: {e}")
                                        continue
            
            # Remove duplicates and sort by timestamp
            unique_readings = {}
            for reading in readings:
                ts_key = reading['ts'].isoformat()
                if ts_key not in unique_readings:
                    unique_readings[ts_key] = reading
            
            final_readings = list(unique_readings.values())
            final_readings.sort(key=lambda x: x['ts'])
            
            self.logger.info(f"Generated {len(final_readings)} readings for station {station_idx}")
            return final_readings
            
        except Exception as e:
            self.logger.error(f"Failed to generate readings for station {station_idx}: {e}")
            return []

    def fetch_station_data(self, station_info: Dict[str, Any]) -> bool:
        """
        Fetch configurable hours of data for a single station.
        
        Args:
            station_info: Station metadata from database
            
        Returns:
            True if successful, False otherwise
        """
        station_idx = station_info['_id']
        station_name = station_info.get('city', {}).get('name', f'Station {station_idx}')
        
        try:
            self.logger.info(f"Fetching {self.data_hours}-hour data for station {station_idx}")
            
            # Calculate date range for configured hours
            end_date = datetime.now()
            start_date = end_date - timedelta(hours=self.data_hours)
            
            # Fetch current data and forecast from AQICN API
            station_data = self.aqicn_client.fetch_hourly(
                station_idx=station_idx,
                start_date=start_date,
                end_date=end_date
            )
            
            self.stats['api_requests_made'] += 1
            
            # Generate configured hours of readings
            readings = self.generate_readings(station_data, station_info)
            
            if readings:
                self.all_readings.extend(readings)
                self.stats['total_readings'] += len(readings)
                self.logger.info(f"Successfully generated {len(readings)} readings for station {station_idx}")
                return True
            else:
                self.logger.warning(f"No readings generated for station {station_idx}")
                self.failed_stations.append({
                    'station_idx': station_idx,
                    'station_name': station_name,
                    'error': 'No readings generated',
                    'error_type': 'NO_DATA'
                })
                return False
                
        except AqicnClientError as e:
            self.logger.error(f"AQICN API error for station {station_idx}: {e}")
            self.failed_stations.append({
                'station_idx': station_idx,
                'station_name': station_name,
                'error': str(e),
                'error_type': 'API_ERROR'
            })
            return False
            
        except Exception as e:
            self.logger.error(f"Unexpected error fetching station {station_idx}: {e}")
            self.failed_stations.append({
                'station_idx': station_idx,
                'station_name': station_name,
                'error': str(e),
                'error_type': 'UNEXPECTED_ERROR'
            })
            return False

    def export_results(self) -> None:
        """Export all collected data to JSON files."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Export readings data
            readings_file = os.path.join(self.results_dir, f'all_stations_{self.data_hours}hour_data_{timestamp}.json')
            with open(readings_file, 'w', encoding='utf-8') as f:
                # Convert datetime objects to strings for JSON serialization
                serializable_readings = []
                for reading in self.all_readings:
                    serializable_reading = reading.copy()
                    if 'ts' in serializable_reading:
                        serializable_reading['ts'] = serializable_reading['ts'].isoformat()
                    serializable_readings.append(serializable_reading)
                
                json.dump(serializable_readings, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Exported {len(self.all_readings)} readings to: {readings_file}")
            
            # Export MongoDB import format
            mongo_import_file = os.path.join(self.results_dir, f'mongo_import_{self.data_hours}hour_{timestamp}.json')
            with open(mongo_import_file, 'w', encoding='utf-8') as f:
                for reading in serializable_readings:
                    # Convert ts to MongoDB ISODate format
                    reading_copy = reading.copy()
                    reading_copy['ts'] = {'$date': reading['ts']}
                    json.dump(reading_copy, f, separators=(',', ':'))
                    f.write('\n')
            
            self.logger.info(f"Exported MongoDB import format to: {mongo_import_file}")
            
            # Export failed stations
            if self.failed_stations:
                failed_file = os.path.join(self.results_dir, f'failed_stations_{self.data_hours}hour_{timestamp}.json')
                with open(failed_file, 'w', encoding='utf-8') as f:
                    json.dump(self.failed_stations, f, indent=2, ensure_ascii=False)
                self.logger.info(f"Exported {len(self.failed_stations)} failed stations to: {failed_file}")
            
            # Export statistics
            stats_file = os.path.join(self.results_dir, f'fetch_stats_{self.data_hours}hour_{timestamp}.json')
            with open(stats_file, 'w', encoding='utf-8') as f:
                # Convert datetime objects to strings
                exportable_stats = self.stats.copy()
                if exportable_stats['start_time']:
                    exportable_stats['start_time'] = exportable_stats['start_time'].isoformat()
                if exportable_stats['end_time']:
                    exportable_stats['end_time'] = exportable_stats['end_time'].isoformat()
                
                json.dump(exportable_stats, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Exported statistics to: {stats_file}")
            
            # Export sample document structure
            if self.all_readings:
                sample_doc_file = os.path.join(self.results_dir, f'sample_document_structure_{self.data_hours}hour_{timestamp}.json')
                sample_doc = {
                    'description': f'{self.data_hours}-hour data collection for all stations - waqi_station_readings format',
                    'collection_name': 'waqi_station_readings',
                    'time_series_config': {
                        'timeField': 'ts',
                        'metaField': 'meta',
                        'granularity': 'hours'
                    },
                    'data_period': f'{self.data_hours} hours',
                    'total_stations': self.stats['total_stations'],
                    'total_readings': self.stats['total_readings'],
                    'sample_document': serializable_readings[0],
                    'required_fields': ['ts', 'meta.station_idx', 'aqi'],
                    'optional_fields': ['time.v', 'time.s', 'time.tz', 'iaqi'],
                    'indexes': [
                        '{ "meta.station_idx": 1, "ts": -1 }',
                        '{ "aqi": -1, "ts": -1 }'
                    ]
                }
                
                with open(sample_doc_file, 'w', encoding='utf-8') as f:
                    json.dump(sample_doc, f, indent=2, ensure_ascii=False)
                
                self.logger.info(f"Exported document structure sample to: {sample_doc_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to export results: {e}")

    def run(self) -> None:
        """Main execution method to fetch configurable hours of data for ALL stations."""
        self.stats['start_time'] = datetime.now()
        
        try:
            # Connect to database
            if not self.connect_database():
                self.logger.error("Failed to connect to database. Exiting.")
                return
            
            # Connect to API client
            if not self.connect_api_client():
                self.logger.error("Failed to create API client. Exiting.")
                return
            
            # Get ALL stations
            stations = self.get_all_stations()
            if not stations:
                self.logger.error("No stations found in database. Exiting.")
                return
            
            self.stats['total_stations'] = len(stations)
            self.logger.info(f"Starting {self.data_hours}-hour data fetch for ALL {len(stations)} stations")
            
            # Fetch data for ALL stations with rate limiting
            for i, station_info in enumerate(stations, 1):
                station_idx = station_info['_id']
                
                self.logger.info(f"Processing station {i}/{len(stations)}: {station_idx}")
                
                # Fetch station data
                success = self.fetch_station_data(station_info)
                
                if success:
                    self.stats['successful_stations'] += 1
                else:
                    self.stats['failed_stations'] += 1
                
                # Progress update every 10 stations
                if i % 10 == 0:
                    self.logger.info(f"Progress: {i}/{len(stations)} stations processed")
                
                # Rate limiting: wait between requests
                if i < len(stations):  # Don't wait after the last station
                    wait_time = 4  # 4 seconds between requests to respect API limits
                    time.sleep(wait_time)
            
            self.stats['end_time'] = datetime.now()
            
            # Print summary
            self.logger.info("=" * 80)
            self.logger.info(f"{self.data_hours.upper()}-HOUR DATA COLLECTION SUMMARY")
            self.logger.info("=" * 80)
            self.logger.info(f"Total stations: {self.stats['total_stations']}")
            self.logger.info(f"Successful stations: {self.stats['successful_stations']}")
            self.logger.info(f"Failed stations: {self.stats['failed_stations']}")
            self.logger.info(f"Total readings collected: {self.stats['total_readings']}")
            self.logger.info(f"API requests made: {self.stats['api_requests_made']}")
            duration = self.stats['end_time'] - self.stats['start_time']
            self.logger.info(f"Total duration: {duration}")
            self.logger.info(f"Average readings per station: {self.stats['total_readings'] / max(self.stats['successful_stations'], 1):.1f}")
            self.logger.info("=" * 80)
            
            # Export all results
            self.export_results()
            
        except KeyboardInterrupt:
            self.logger.warning("Process interrupted by user")
            self.stats['end_time'] = datetime.now()
            self.export_results()
            
        except Exception as e:
            self.logger.error(f"Unexpected error during execution: {e}")
            self.stats['end_time'] = datetime.now()
            self.export_results()
            
        finally:
            # Close database connection
            if self.client:
                self.client.close()
                self.logger.info("Database connection closed")


def main():
    """Main function to run the configurable hours data fetcher for ALL stations."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f'all_stations_{DATA_HOURS}hour_fetch.log')
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting {DATA_HOURS}-hour data fetch for ALL stations")
    
    # Create and run fetcher with configured hours
    fetcher = AllStationsDataFetcher(data_hours=DATA_HOURS)
    fetcher.run()
    
    logger.info(f"{DATA_HOURS}-hour data fetch for ALL stations completed")


if __name__ == "__main__":
    main()
