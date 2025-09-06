# scripts/create_indexes.py
"""
Create MongoDB indexes for optimal query performance.

This script creates essential indexes for the air quality monitoring system:
- Unique index on station codes
- Geospatial index for location-based queries  
- Compound indexes for time-series data queries

The script is idempotent - safe to run multiple times.

Usage:
    python scripts/create_indexes.py
    
Requires:
    MONGO_URI, MONGO_DB environment variables (loaded from .env file)
"""

import os
from pymongo import MongoClient, ASCENDING, DESCENDING, GEOSPHERE
from pymongo.database import Database
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_db() -> Database:
    mongo_uri = os.environ.get('MONGO_URI')
    mongo_db = os.environ.get('MONGO_DB')
    if not mongo_uri or not mongo_db:
        raise ValueError("MONGO_URI and MONGO_DB environment variables must be set")
    client = MongoClient(mongo_uri)
    return client[mongo_db]

def create_indexes():
    """Create all required database indexes for optimal performance."""
    db = get_db()

    print("[INFO] Creating indexes for optimal query performance...")
    
    # stations collection indexes
    print("[INDEXES] stations collection")
    db.stations.create_index([("code", ASCENDING)], name="uq_code", unique=True)
    print("  ✓ Created unique index on station code")
    
    db.stations.create_index([("loc", GEOSPHERE)], name="idx_loc_2dsphere")
    print("  ✓ Created geospatial index on location")

    # air_quality_data collection indexes
    print("[INDEXES] air_quality_data collection")
    db.air_quality_data.create_index(
        [("station_id", ASCENDING), ("ts_utc", DESCENDING)],
        name="idx_station_ts",
    )
    print("  ✓ Created compound index on station_id + ts_utc")
    
    db.air_quality_data.create_index(
        [("lat", ASCENDING), ("lon", ASCENDING), ("ts_utc", DESCENDING)],
        name="idx_lat_lon_ts",
    )
    print("  ✓ Created compound index on lat + lon + ts_utc")

    print("[SUCCESS] All indexes created successfully!")

if __name__ == "__main__":
    create_indexes()