import pytest
from flask import Flask
import json


class FakeCollection:
    def __init__(self, agg_result=None):
        self.agg_result = agg_result or []
        self._cache = {}

    def aggregate(self, pipeline):
        # Return an iterator like pymongo cursor
        return iter(self.agg_result)

    def replace_one(self, filter_doc, doc, upsert=False):
        self._cache[filter_doc['_id']] = doc

    def create_index(self, *args, **kwargs):
        return None

    def find_one(self, filter_doc):
        return self._cache.get(filter_doc.get('_id'))


class FakeDB:
    def __init__(self, stations_result=None):
        self.waqi_stations = FakeCollection(agg_result=stations_result)
        self.api_response_cache = FakeCollection()


@pytest.fixture
def app(monkeypatch):
    from backend.app.blueprints.api.stations.routes import stations_bp

    app = Flask(__name__)
    app.register_blueprint(stations_bp, url_prefix='/api/stations')
    app.testing = True

    # Provide a default fake DB; individual tests will override if needed
    fake_db = FakeDB()
    monkeypatch.setattr('backend.app.db.get_db', lambda: fake_db)
    return app


def test_nearest_success(app, monkeypatch):
    # Prepare a fake station doc returned by aggregate (with dist in meters)
    station_doc = {
        '_id': 'station1',
        'station_id': 'S1',
        'name': 'Test Station',
        'location': {'type': 'Point', 'coordinates': [106.6297, 10.8231]},
        'dist': {'calculated': 2000},
        'latest_reading': {'aqi': 42, 'timestamp': '2025-09-24T00:00:00Z'}
    }

    fake_db = FakeDB(stations_result=[station_doc])
    monkeypatch.setattr('backend.app.db.get_db', lambda: fake_db)

    client = app.test_client()
    resp = client.get('/api/stations/nearest?lat=10.8231&lng=106.6297&radius=5&limit=1')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'stations' in data
    assert len(data['stations']) == 1
    st = data['stations'][0]
    # dist 2000 meters => 2.00 km
    assert st['_distance_km'] == 2.0
    assert st['latest_reading']['aqi'] == 42


def test_nearest_no_results(app, monkeypatch):
    fake_db = FakeDB(stations_result=[])
    monkeypatch.setattr('backend.app.db.get_db', lambda: fake_db)

    client = app.test_client()
    resp = client.get('/api/stations/nearest?lat=10.0&lng=105.0&radius=1&limit=1')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['stations'] == []
    assert 'message' in data


def test_nearest_cache_used(app, monkeypatch):
    # First call returns one station and caches it
    station_a = {
        '_id': 'stationA',
        'station_id': 'A',
        'name': 'A',
        'location': {'type': 'Point', 'coordinates': [106.0, 10.0]},
        'dist': {'calculated': 1000},
        'latest_reading': {'aqi': 10}
    }

    fake_db = FakeDB(stations_result=[station_a])
    monkeypatch.setattr('backend.app.db.get_db', lambda: fake_db)

    client = app.test_client()
    url = '/api/stations/nearest?lat=10.0&lng=106.0&radius=5&limit=1'
    resp1 = client.get(url)
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert len(data1['stations']) == 1

    # Now change the underlying stations result to something else; cached response should be returned
    station_b = {
        '_id': 'stationB',
        'station_id': 'B',
        'name': 'B',
        'location': {'type': 'Point', 'coordinates': [106.1, 10.1]},
        'dist': {'calculated': 500},
        'latest_reading': {'aqi': 99}
    }
    fake_db.waqi_stations.agg_result = [station_b]

    resp2 = client.get(url)
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    # Should return cached first response (stationA)
    assert data2 == data1
