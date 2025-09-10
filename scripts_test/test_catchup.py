from unittest.mock import MagicMock
from datetime import datetime, timezone


def test_catchup_station_inserts_one_reading(monkeypatch):
    """When no previous readings exist, catchup_station should insert the current reading."""
    import ingest.catchup as catchup

    # Fake client that returns a single current reading
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    sample_time_iso = now.isoformat().replace('+00:00', 'Z')
    fake_client = MagicMock()
    fake_client.fetch_hourly.return_value = {
        'data': {'time': {'s': sample_time_iso}, 'aqi': 42}
    }

    # Patch client creation to return our fake client
    monkeypatch.setattr('ingest.catchup.create_client_from_env', lambda: fake_client)

    # Patch internal last-ts lookup to simulate no existing readings
    monkeypatch.setattr('ingest.catchup._get_last_ts_for_station', lambda station_idx: None)

    # Patch upsert_readings to return processed_count = number of readings
    def fake_upsert(collection, station_idx, readings):
        return {'processed_count': len(readings)}

    monkeypatch.setattr('ingest.catchup.upsert_readings', fake_upsert)

    res = catchup.catchup_station(999, client=None)
    assert res['status'] == 'ok'
    assert res['processed'] == 1


def test_catchup_station_up_to_date(monkeypatch):
    """When last_ts is already current hour, function reports up-to-date and does nothing."""
    import ingest.catchup as catchup

    # Set last_ts to now so from_ts > now_hour path is taken
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr('ingest.catchup._get_last_ts_for_station', lambda station_idx: now)

    # Create a client but it should not be called
    fake_client = MagicMock()
    monkeypatch.setattr('ingest.catchup.create_client_from_env', lambda: fake_client)

    res = catchup.catchup_station(1000, client=None)
    assert res['status'] == 'up-to-date'
    assert res['processed'] == 0
