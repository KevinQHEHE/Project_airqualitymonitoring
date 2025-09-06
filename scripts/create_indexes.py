# scripts/create_indexes.py
"""
Create base indexes for stations and air_quality_data.
Idempotent: create_index won't duplicate existing ones.
Usage:
    python scripts/create_indexes.py
Requires:
    MONGO_URI, MONGO_DB in environment.
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
    db = get_db()

    # stations
    print("[indexes] stations")
    db.stations.create_index([("code", ASCENDING)], name="uq_code", unique=True)
    db.stations.create_index([("loc", GEOSPHERE)], name="idx_loc_2dsphere")

    # air_quality_data
    print("[indexes] air_quality_data")
    db.air_quality_data.create_index(
        [("station_id", ASCENDING), ("ts_utc", DESCENDING)],
        name="idx_station_ts",
    )
    db.air_quality_data.create_index(
        [("lat", ASCENDING), ("lon", ASCENDING), ("ts_utc", DESCENDING)],
        name="idx_lat_lon_ts",
    )

    print("[done] indexes ensured.")

if __name__ == "__main__":
    create_indexes()