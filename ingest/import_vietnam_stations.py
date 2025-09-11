#!/usr/bin/env python3
"""
Script to upsert Vietnam stations data to MongoDB.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ingest.mongo_utils import bulk_upsert_stations, MongoUpsertError
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_mongo_connection() -> MongoClient:
    """Get MongoDB connection from environment variables."""
    mongo_uri = os.getenv('MONGO_URI')
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable not set")
    
    try:
        client = MongoClient(mongo_uri)
        # Test connection
        client.admin.command('ping')
        logger.info("Connected to MongoDB successfully")
        return client
    except PyMongoError as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


def load_stations_data(file_path: str) -> Dict[str, Any]:
    """Load stations data from JSON file."""
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded {len(data['data'])} stations from {file_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in file {file_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {e}")
        raise


def validate_station_data(stations: list) -> bool:
    """Validate stations data structure."""
    required_fields = ['_id', 'city']
    city_required_fields = ['name', 'url', 'geo']
    geo_required_fields = ['type', 'coordinates']
    
    for i, station in enumerate(stations):
        # Check top-level required fields
        for field in required_fields:
            if field not in station:
                logger.error(f"Station {i}: Missing required field '{field}'")
                return False
        
        # Check city fields
        city = station.get('city', {})
        for field in city_required_fields:
            if field not in city:
                logger.error(f"Station {station['_id']}: Missing city.{field}")
                return False
        
        # Check geo fields
        geo = city.get('geo', {})
        for field in geo_required_fields:
            if field not in geo:
                logger.error(f"Station {station['_id']}: Missing city.geo.{field}")
                return False
        
        # Validate coordinates (fix coordinate order for GeoJSON)
        coordinates = geo.get('coordinates', [])
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            logger.error(f"Station {station['_id']}: Invalid coordinates format")
            return False
        
        try:
            lat, lon = float(coordinates[0]), float(coordinates[1])
            
            # Check if coordinates seem to be in lat,lon order (incorrect for GeoJSON)
            # GeoJSON requires [longitude, latitude] order
            if 8.2 <= lat <= 23.4 and 102.1 <= lon <= 109.5:
                # Coordinates are in lat,lon order, need to swap for GeoJSON
                logger.info(f"Station {station['_id']}: Swapping coordinates from [lat,lon] to [lon,lat] for GeoJSON")
                station['city']['geo']['coordinates'] = [lon, lat]
                lat, lon = lon, lat  # Update for validation
            
            # Validate GeoJSON coordinates [longitude, latitude]
            if not (-180 <= lat <= 180 and -90 <= lon <= 90):
                logger.error(f"Station {station['_id']}: Coordinates out of range after correction")
                return False
                
        except (ValueError, TypeError):
            logger.error(f"Station {station['_id']}: Invalid coordinate values")
            return False
    
    logger.info("All stations data validated successfully")
    return True


def upsert_vietnam_stations(json_file_path: str, db_name: str = None) -> Dict[str, Any]:
    """
    Upsert Vietnam stations data to MongoDB.
    
    Args:
        json_file_path: Path to the JSON file containing stations data
        db_name: Database name (defaults to MONGO_DB env var)
        
    Returns:
        Dict with upsert results
    """
    # Load environment variables
    if db_name is None:
        db_name = os.getenv('MONGO_DB', 'air_quality_db')
    
    logger.info(f"Starting Vietnam stations upsert to database: {db_name}")
    
    try:
        # Load stations data
        data = load_stations_data(json_file_path)
        stations = data['data']
        metadata = data['metadata']
        
        logger.info(f"Metadata: {metadata}")
        
        # Validate data structure
        if not validate_station_data(stations):
            raise ValueError("Data validation failed")
        
        # Connect to MongoDB
        client = get_mongo_connection()
        db = client[db_name]
        collection = db.waqi_stations
        
        logger.info(f"Using collection: {db_name}.waqi_stations")
        
        # Check if collection exists and has indexes
        indexes = list(collection.list_indexes())
        logger.info(f"Existing indexes: {[idx['name'] for idx in indexes]}")
        
        # Perform bulk upsert
        logger.info("Starting bulk upsert operation...")
        result = bulk_upsert_stations(collection, stations)
        
        # Log results
        logger.info("Upsert operation completed successfully!")
        logger.info(f"Processed: {result['processed_count']} stations")
        logger.info(f"Inserted: {result['upserted_count']} new stations")
        logger.info(f"Updated: {result['modified_count']} existing stations")
        logger.info(f"Matched: {result['matched_count']} existing records")
        
        # Get final count
        total_count = collection.count_documents({})
        logger.info(f"Total stations in collection: {total_count}")
        
        return {
            'success': True,
            'file_processed': json_file_path,
            'metadata': metadata,
            'upsert_result': result,
            'total_stations_in_db': total_count
        }
        
    except Exception as e:
        logger.error(f"Error during upsert operation: {e}")
        return {
            'success': False,
            'error': str(e),
            'file_processed': json_file_path
        }
    finally:
        if 'client' in locals():
            client.close()
            logger.info("MongoDB connection closed")


def main():
    """Main function to run the upsert operation."""
    # Look for the most recent vietnam_stations_*.json file
    data_dir = Path("ingest/data_results")
    
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)
    
    json_files = list(data_dir.glob("vietnam_stations_*.json"))
    if not json_files:
        logger.error("No vietnam_stations_*.json files found in data_results")
        sys.exit(1)
    
    # Use the most recent file
    latest_file = str(max(json_files, key=lambda p: p.stat().st_mtime))
    logger.info(f"Using most recent file: {latest_file}")
    
    # Run upsert
    result = upsert_vietnam_stations(latest_file)
    
    if result['success']:
        logger.info("Vietnam stations successfully upserted to MongoDB!")
        print(f"\n{'='*60}")
        print("UPSERT SUMMARY")
        print(f"{'='*60}")
        print(f"File: {result['file_processed']}")
        print(f"Collection: {result['metadata']['collection']}")
        print(f"Stations processed: {result['upsert_result']['processed_count']}")
        print(f"New stations inserted: {result['upsert_result']['upserted_count']}")
        print(f"Existing stations updated: {result['upsert_result']['modified_count']}")
        print(f"Total stations in database: {result['total_stations_in_db']}")
        print(f"{'='*60}")
    else:
        logger.error(f"Upsert operation failed: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
