"""Backfill script to populate GeoJSON `location` and ensure indexes.

This script is idempotent and safe to run multiple times. It will:
- find `waqi_stations` documents missing the top-level `location` field but
  which have legacy coordinates in `geo.coordinates` or `latitude`/`longitude`;
- compute a GeoJSON `Point` and write it to the `location` field using an
  atomic `update_one` (only when `location` does not exist);
- optionally create a `2dsphere` index on `location` and a TTL index on
  `api_response_cache.expiresAt`.

Usage (PowerShell):
  # dry-run (default) - only report what would be changed
  python scripts\fix_waqi_locations.py --dry-run

  # perform changes
  python scripts\fix_waqi_locations.py

Notes:
- Always run with `--dry-run` first, and consider a backup/snapshot for
  production data before mass updates.
"""
from __future__ import annotations

import argparse
import logging
from typing import Optional

# Ensure the repository root is on sys.path so `from backend.app import db` works
# when the script is run with `python scripts\fix_waqi_locations.py` from the repo root.
import os
from pymongo import MongoClient


# Prefer not to import the full application package here because importing
# `backend.app` pulls in the application config which expects `python-dotenv`.
# Instead create a small local MongoDB connection using environment variables
# (and load .env if python-dotenv is installed). This makes the script runnable
# in minimal dev environments without installing the entire project deps.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv not installed; rely on environment variables
    pass


def get_database() -> MongoClient:
    """Create a pymongo database object using MONGO_URI / MONGO_DB env vars."""
    mongo_uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    mongo_db = os.environ.get('MONGO_DB', 'air_quality_monitoring')
    client = MongoClient(mongo_uri)
    return client[mongo_db]

logger = logging.getLogger("fix_waqi_locations")
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def ensure_indexes(database) -> None:
    """Create 2dsphere on `location` and TTL index on api_response_cache.expiresAt."""
    try:
        logger.info("Ensuring 2dsphere index on waqi_stations.location")
        database.waqi_stations.create_index([("location", "2dsphere")], background=True)
    except Exception as e:
        logger.exception("Failed to create 2dsphere index: %s", e)

    try:
        logger.info("Ensuring TTL index on api_response_cache.expiresAt")
        database.api_response_cache.create_index("expiresAt", expireAfterSeconds=0, background=True)
    except Exception as e:
        logger.exception("Failed to create TTL index: %s", e)


def to_float_safe(v) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def backfill_locations(database, dry_run: bool = True, batch_size: int = 1000) -> dict:
    """Backfill missing `location` from legacy fields.

    Returns a summary dict.
    """
    filter_q = {
        "$and": [
            {"location": {"$exists": False}},
            {"$or": [
                {"geo.coordinates": {"$exists": True}},
                {"city.geo.coordinates": {"$exists": True}},
                {"latitude": {"$exists": True}, "longitude": {"$exists": True}}
            ]}
        ]
    }

    cursor = database.waqi_stations.find(
        filter_q,
        projection={"geo": 1, "city": 1, "location": 1, "latitude": 1, "longitude": 1}
    ).batch_size(batch_size)

    scanned = 0
    to_update = 0
    updated = 0
    skipped = 0

    for doc in cursor:
        scanned += 1
        lat = lng = None

        # legacy geo.coordinates expected as [lng, lat]
        geo = doc.get("geo")
        if isinstance(geo, dict):
            coords = geo.get("coordinates")
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                try:
                    lng = to_float_safe(coords[0])
                    lat = to_float_safe(coords[1])
                except Exception:
                    lat = lng = None

        if lat is None or lng is None:
            # try numeric latitude/longitude fields
            lat = to_float_safe(doc.get("latitude"))
            lng = to_float_safe(doc.get("longitude"))

        # some docs store coords under city.geo: { city: { geo: { coordinates: [lng, lat] } } }
        if lat is None or lng is None:
            city = doc.get("city")
            if isinstance(city, dict):
                city_geo = city.get("geo")
                if isinstance(city_geo, dict):
                    coords = city_geo.get("coordinates")
                    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                        try:
                            lng = to_float_safe(coords[0])
                            lat = to_float_safe(coords[1])
                        except Exception:
                            lat = lng = None

        if lat is None or lng is None:
            skipped += 1
            continue

        # ensure sensible ranges
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            skipped += 1
            continue

        to_update += 1
        if dry_run:
            # just report
            continue

        location = {"type": "Point", "coordinates": [lng, lat]}

        # atomic update: set location only if it still does not exist
        res = database.waqi_stations.update_one(
            {"_id": doc.get("_id"), "location": {"$exists": False}},
            {"$set": {"location": location}}
        )
        if res.modified_count:
            updated += 1
        else:
            # might be a race or existing location, count as skipped
            skipped += 1

    summary = {"scanned": scanned, "to_update": to_update, "updated": updated, "skipped": skipped}
    return summary


def main():
    parser = argparse.ArgumentParser(description="Backfill waqi_stations.location from legacy fields and ensure indexes.")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes, only show what would be done")
    parser.add_argument("--batch-size", type=int, default=1000, help="Cursor batch size for scanning")
    parser.add_argument("--ensure-indexes", action="store_true", help="Create 2dsphere and TTL indexes after backfill")

    args = parser.parse_args()

    try:
        database = get_database()
    except Exception as e:
        logger.exception("Failed to get DB connection: %s", e)
        return

    logger.info("Starting waqi_stations.location backfill (dry_run=%s)" % args.dry_run)
    summary = backfill_locations(database, dry_run=args.dry_run, batch_size=args.batch_size)
    logger.info("Backfill summary: %s", summary)

    if args.ensure_indexes:
        ensure_indexes(database)

    logger.info("Done.")


if __name__ == '__main__':
    main()
