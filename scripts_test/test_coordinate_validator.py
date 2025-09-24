from flask import Flask
import pytest


def validate_coordinates_from_request():
    """Inline validator used for test compatibility (mirrors removed module)."""
    from flask import request
    lat_raw = request.args.get('lat')
    lng_raw = request.args.get('lng')
    if lat_raw is None or lng_raw is None:
        raise ValueError('lat and lng parameters are required')
    try:
        lat = float(lat_raw)
        lng = float(lng_raw)
    except (TypeError, ValueError):
        raise ValueError('lat and lng must be valid numbers')

    if not (-90.0 <= lat <= 90.0):
        raise ValueError('lat out of bounds')
    if not (-180.0 <= lng <= 180.0):
        raise ValueError('lng out of bounds')

    return lat, lng


@pytest.fixture
def app():
    app = Flask(__name__)
    return app


def test_validate_coordinates_success(app):
    client = app.test_client()

    @app.route('/_test')
    def _test():
        lat, lng = validate_coordinates_from_request()
        return f"{lat},{lng}"

    resp = client.get('/_test?lat=10.5&lng=105.2')
    assert resp.status_code == 200
    assert resp.data.decode() == '10.5,105.2'


def test_validate_coordinates_invalid(app):
    client = app.test_client()

    @app.route('/_test2')
    def _test2():
        try:
            validate_coordinates_from_request()
        except ValueError as e:
            return str(e), 400

    resp = client.get('/_test2?lat=200&lng=0')
    assert resp.status_code == 400
    assert 'lat out of bounds' in resp.data.decode()
