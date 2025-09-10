"""Run catchup scenarios without pytest.

This script runs two scenarios from `test_catchup.py` directly:
 - no existing readings -> expect one reading inserted
 - last_ts already current hour -> expect up-to-date

Run with:
    python .\scripts_test\run_catchup_script.py
"""
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import json


def scenario_insert_one():
    import ingest.catchup as catchup

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    sample_time_iso = now.isoformat().replace('+00:00', 'Z')

    fake_client = MagicMock()
    fake_client.fetch_hourly.return_value = {
        'data': {'time': {'s': sample_time_iso}, 'aqi': 42}
    }

    def fake_upsert(collection, station_idx, readings):
        return {'processed_count': len(readings)}

    with patch('ingest.catchup.create_client_from_env', lambda: fake_client), \
         patch('ingest.catchup._get_last_ts_for_station', lambda station_idx: None), \
         patch('ingest.catchup.upsert_readings', fake_upsert):
        res = catchup.catchup_station(999, client=None)
        print('scenario_insert_one:', json.dumps(res, default=str))


def scenario_up_to_date():
    import ingest.catchup as catchup

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    fake_client = MagicMock()

    with patch('ingest.catchup._get_last_ts_for_station', lambda station_idx: now), \
         patch('ingest.catchup.create_client_from_env', lambda: fake_client):
        res = catchup.catchup_station(1000, client=None)
        print('scenario_up_to_date:', json.dumps(res, default=str))


if __name__ == '__main__':
    print('Running catchup script (no pytest)')
    # Create Flask app and run scenarios inside application context so
    # backend.app.db.get_db() and other context-bound functions work.
    try:
        from backend.app import create_app
    except Exception as e:
        print('Could not import create_app from backend.app:', e)
        # fallback to running scenarios without app context (may error)
        scenario_insert_one()
        scenario_up_to_date()
    else:
        app = create_app()
        with app.app_context():
            scenario_insert_one()
            scenario_up_to_date()
