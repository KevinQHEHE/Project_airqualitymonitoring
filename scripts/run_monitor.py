"""Run the favorite-stations monitor in-process and print a short summary.

This helper is intended for local development. When executed directly from
the repository root Python may not be able to import the `backend` package
unless the repo root is on PYTHONPATH. To make this script easy to run we
add the repo root to sys.path when needed.

Usage:
    python scripts/run_monitor.py
"""
import os
import sys

# Ensure repo root is on sys.path so `backend` package can be imported
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.app import create_app

app = create_app()

with app.app_context():
    try:
        from backend.app.tasks.alerts import monitor_favorite_stations
        print("Invoking monitor_favorite_stations() ...")
        monitor_favorite_stations()
        print("Monitor completed (check notification_logs collection for details).")
    except Exception as e:
        print("Failed to run monitor:", e)
        raise
