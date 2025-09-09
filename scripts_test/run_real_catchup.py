"""
Run a real catch-up against configured MongoDB and AQICN.

Purpose: lightweight script to execute `ingest.catchup.catchup_all_stations()`
inside the Flask application context. It expects environment variables (or
Flask config) to provide `MONGO_URI`, `MONGO_DB` and `AQICN_API_KEY`.

Usage (PowerShell):
    $env:MONGO_URI='mongodb://user:pass@host:27017'
    $env:MONGO_DB='my_db'
    $env:AQICN_API_KEY='your_key'
    python .\scripts_test\run_real_catchup.py

Safety: recommended to run against staging or backup the relevant collections
before running in production.
"""
from __future__ import annotations

import logging
from typing import Any, Dict
import argparse


def main() -> int:
    """Create Flask app and run the real catchup job.

    Returns an exit code: 0 on success, non-zero on failure.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        from backend.app import create_app
        from ingest import catchup
    except Exception as e:  # pragma: no cover - environment import issues
        logging.exception("Failed to import application or catchup module: %s", e)
        return 2

    app = create_app()

    parser = argparse.ArgumentParser(description='Run real catchup')
    parser.add_argument('--dry-run', action='store_true', help='Do not upsert, only log what would be done')
    parser.add_argument('--station', type=int, help='Only run catchup for a single station id')
    args = parser.parse_args()

    try:
        with app.app_context():
            logging.info("Starting real catchup: scanning stations and filling missing hours")
            summary: Dict[str, Any] = catchup.catchup_all_stations(dry_run=args.dry_run, station=args.station)
            logging.info("Catchup summary: %s", summary)
    except Exception as e:
        logging.exception("Unhandled exception while running catchup: %s", e)
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
