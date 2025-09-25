"""Insert a synthetic high-AQI reading for a station, run the monitor, and print notification_logs.

This script will:
 - login as test user
 - ensure user has favoriteStations set to the chosen station and notifications enabled
 - insert a waqi_station_readings doc with high aqi (e.g., 300)
 - run monitor_favorite_stations() in-process
 - query /api/alerts/logs for that user/station and print results

Run from project root.
"""
import sys
import time
import json
from datetime import datetime, timezone

BASE = 'http://localhost:5000'
EMAIL = 'chungkhoa45@gmail.com'
PASSWORD = '22110166@Kh'

try:
    import requests
except Exception:
    print('requests required; pip install requests')
    sys.exit(1)

session = requests.Session()


def login():
    r = session.post(f'{BASE}/api/auth/login', json={'email': EMAIL, 'password': PASSWORD}, timeout=10)
    print('LOGIN', r.status_code)
    if r.status_code != 200:
        print(r.text)
        sys.exit(2)
    data = r.json()
    return data.get('access_token'), (data.get('user') or {}).get('id')


if __name__ == '__main__':
    token, user_id = login()
    print('user_id:', user_id)

    # Choose stations that are in the DB and accepted earlier
    station_ids = [5506, 8688]

    # 1) Ensure favorites + notifications via API
    headers = {'Authorization': f'Bearer {token}'}
    fav_body = {'favoriteStations': station_ids}
    r = session.put(f'{BASE}/api/alerts/user/{user_id}/favorites', json=fav_body, headers=headers, timeout=30)
    print('PUT favorites:', r.status_code, r.text)

    notif_body = {'enabled': True, 'threshold': 80}
    r = session.put(f'{BASE}/api/alerts/user/{user_id}/notifications', json=notif_body, headers=headers, timeout=10)
    print('PUT notifications:', r.status_code, r.text)

    # 1b) Create an alert subscription via the API so the monitor can attach subscription_id.
    # Use the authenticated session and retry on transient failures (DB/timeout).
    # Create a subscription for each station (with retries)
    sub_url = f'{BASE}/api/alerts/subscriptions'
    created_subscriptions = {}
    max_attempts = 5
    for station_id in station_ids:
        sub_body = {'user_id': user_id, 'station_id': str(station_id), 'alert_threshold': 200}
        sub_id = None
        backoff = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                r = session.post(sub_url, json=sub_body, headers=headers, timeout=10)
            except Exception as e:
                print(f'Attempt {attempt} for station {station_id}: network/timeout error creating subscription: {e}')
                if attempt < max_attempts:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    print(f'Giving up creating subscription for station {station_id} after network errors')
                    break

            if r.status_code in (200, 201):
                try:
                    sub_id = r.json().get('subscription_id')
                except Exception:
                    sub_id = None
                print(f'Created subscription for station {station_id}:', r.status_code, sub_id)
                created_subscriptions[str(station_id)] = sub_id
                break

            if r.status_code >= 500 and attempt < max_attempts:
                print(f'Attempt {attempt} for station {station_id}: server error creating subscription ({r.status_code}), retrying in {backoff}s')
                time.sleep(backoff)
                backoff *= 2
                continue

            print(f'Create subscription failed or already exists for station {station_id}:', r.status_code, r.text)
            break

    # 2) Insert a synthetic reading directly into MongoDB via app context
    from backend.app import create_app
    from backend.app.db import get_db
    app = create_app()
    # Insert a synthetic reading for each station
    ts = datetime.now(timezone.utc)
    readings = []
    for station_id in station_ids:
        reading = {
        # store ts as a real datetime (BSON UTC datetime) so the collection
        # validator accepts it and repository queries by ts work correctly
            'ts': ts,
            # include station_id string (many parts of the code look up readings
            # by station_id) and meta.station_idx for backwards compatibility
            'station_id': str(station_id),
            'meta': {'station_idx': station_id},
            'aqi': 300,
            'time': {'s': ts.isoformat(), 'tz': '+00:00'}
        }
        readings.append((station_id, reading))

    with app.app_context():
        db = get_db()
        for station_id, reading in readings:
            res = db.waqi_station_readings.insert_one(reading)
            print(f'Inserted reading id for station {station_id}:', res.inserted_id)

        # 3) Run the monitor once after inserting all readings
        from backend.app.tasks.alerts import monitor_favorite_stations
        print('Running monitor...')
        monitor_favorite_stations()
        print('Monitor done')

    # 4) Give a small delay then query the logs via API
    # Query the logs for each station
    time.sleep(0.5)
    for station_id in station_ids:
        r = session.get(f'{BASE}/api/alerts/logs', params={'user_id': user_id, 'station_id': str(station_id)}, timeout=10)
        print(f'GET logs for station {station_id}:', r.status_code)
        try:
            print(json.dumps(r.json(), indent=2, default=str))
        except Exception:
            print(r.text)

    print('done')
