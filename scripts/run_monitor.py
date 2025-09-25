"""Run the favorite-stations monitor in-process and print a short summary.

This imports the monitor function and runs it inside the Flask app context.
Use this in local/dev to perform a one-off run.
"""
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
