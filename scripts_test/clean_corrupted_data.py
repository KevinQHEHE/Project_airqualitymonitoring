"""
Clean up corrupted forecast data from waqi_station_readings and reset checkpoints.

Purpose: Remove all existing readings data and checkpoints to allow fresh ingestion
of current real-time data (not forecast data).
"""
from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timezone

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure


def load_env_file():
    """Load environment variables manually from .env file."""
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    """Main function to clean up corrupted data."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Load environment variables
    load_env_file()
    
    # Get MongoDB connection details
    mongo_uri = os.environ.get('MONGO_URI')
    mongo_db = os.environ.get('MONGO_DB', 'air_quality_db')
    
    if not mongo_uri:
        logger.error("MONGO_URI environment variable is required")
        sys.exit(1)
    
    try:
        # Connect to MongoDB
        logger.info(f"Connecting to MongoDB: {mongo_db}")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        db = client[mongo_db]
        
        logger.info(f"Connected to database: {mongo_db}")
        
        # Collections to clean
        readings_collection = db['waqi_station_readings']
        checkpoints_collection = db['checkpoints']
        stations_collection = db['waqi_stations']
        
        # 1. Check current data in readings collection
        total_readings = readings_collection.count_documents({})
        logger.info(f"Found {total_readings} existing readings to clean")
        
        # Show sample of current data
        if total_readings > 0:
            sample = list(readings_collection.find().limit(3))
            logger.info("Sample of current readings data:")
            for i, doc in enumerate(sample, 1):
                logger.info(f"  Sample {i}: station_idx={doc.get('meta', {}).get('station_idx')}, "
                           f"ts={doc.get('ts')}, aqi={doc.get('aqi')}")
        
        # 2. Clean up readings collection
        logger.info("Cleaning up waqi_station_readings collection...")
        result = readings_collection.delete_many({})
        logger.info(f"Deleted {result.deleted_count} reading documents")
        
        # 3. Clean up checkpoints collection
        total_checkpoints = checkpoints_collection.count_documents({})
        logger.info(f"Found {total_checkpoints} checkpoints to clean")
        
        if total_checkpoints > 0:
            logger.info("Cleaning up checkpoints collection...")
            result = checkpoints_collection.delete_many({})
            logger.info(f"Deleted {result.deleted_count} checkpoint documents")
        
        # 4. Reset latest_update_time and latest_reading_at in stations collection
        logger.info("Resetting latest_update_time and latest_reading_at in stations...")
        result = stations_collection.update_many(
            {},
            {'$unset': {
                'latest_update_time': '',
                'latest_reading_at': ''
            }}
        )
        logger.info(f"Reset latest_update_time and latest_reading_at for {result.modified_count} stations")
        
        # 5. Verify cleanup
        remaining_readings = readings_collection.count_documents({})
        remaining_checkpoints = checkpoints_collection.count_documents({})
        
        logger.info(f"Cleanup completed:")
        logger.info(f"  - Remaining readings: {remaining_readings}")
        logger.info(f"  - Remaining checkpoints: {remaining_checkpoints}")
        logger.info(f"  - Stations reset: {result.modified_count}")
        
        if remaining_readings == 0 and remaining_checkpoints == 0:
            logger.info("✅ Database successfully cleaned and ready for fresh ingestion")
        else:
            logger.warning("⚠️ Some data may not have been cleaned properly")
        
        # Close connection
        client.close()
        logger.info("Database connection closed")
        
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during cleanup: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
