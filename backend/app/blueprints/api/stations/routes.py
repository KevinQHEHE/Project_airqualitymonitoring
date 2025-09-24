"""Stations blueprint for managing air quality monitoring stations.

This module implements the stations endpoints. The `/nearest` endpoint is
implemented inline using a geospatial aggregation (`$geoNear`) and a
`$lookup` to fetch the latest reading for each station. A legacy fallback
supports documents that use `geo` or `latitude`/`longitude` fields.
"""
from flask import Blueprint, request, jsonify, current_app
import logging
from datetime import datetime, timedelta
from backend.app.repositories import stations_repo
import math

from backend.app.extensions import limiter
from backend.app import db
from backend.app.db import DatabaseError
import traceback
from pymongo.errors import OperationFailure
from bson import ObjectId

logger = logging.getLogger(__name__)

stations_bp = Blueprint('stations', __name__)


def haversine_distance_km(a, b):
    """Calculate great-circle distance between two (lat, lng) pairs in km."""
    lat1, lon1 = a
    lat2, lon2 = b
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    hav = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    R = 6371.0088
    c = 2 * math.asin(min(1, math.sqrt(hav)))
    return R * c


def format_km(value: float) -> float:
    return round(value + 1e-12, 2)


def sanitize_for_json(obj):
    """Recursively convert types that Flask/json can't serialize (ObjectId, datetime)."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def prepare_response(response: dict) -> dict:
    """Prune debug/internal fields from response unless debug is requested.

    - removes `dist` and `city_geo` used for debugging/indexing
    - trims `latest_reading` to a small useful subset when not debugging
    """
    # Always prune internal aggregation/debug fields from responses served to clients
    if isinstance(response, dict):
        stations = response.get('stations')
        if isinstance(stations, list):
            for s in stations:
                if isinstance(s, dict):
                    # remove internal aggregation fields
                    s.pop('dist', None)
                    s.pop('city_geo', None)
                    # trim latest_reading to essential fields to avoid large payloads
                    lr = s.get('latest_reading')
                    if isinstance(lr, dict):
                        trimmed = {k: lr[k] for k in ('aqi', 'time', 'iaqi', 'meta') if k in lr}
                        s['latest_reading'] = trimmed if trimmed else None
    return sanitize_for_json(response)


def _compute_distance_km_from_doc(doc, lat: float, lng: float):
    """Compute an approximate distance in km for a station document.

    Uses the aggregation 'dist' field when present, otherwise falls back to
    location coordinates and the haversine formula.
    """
    dist_field = doc.get('dist', None)
    dist_m = None
    if isinstance(dist_field, dict):
        dist_m = dist_field.get('calculated')
    elif isinstance(dist_field, (int, float)):
        dist_m = dist_field

    if isinstance(dist_m, (int, float)):
        return round(dist_m / 1000.0 + 1e-12, 2)

    loc = doc.get('location') or {}
    coords = loc.get('coordinates') if isinstance(loc, dict) else None
    if coords and isinstance(coords, list) and len(coords) >= 2:
        station_lng, station_lat = coords[0], coords[1]
        return format_km(haversine_distance_km((lat, lng), (station_lat, station_lng)))

    return None


def _cache_response(response: dict, cache_coll, cache_key: str, ttl_seconds: int = 300):
    """Write `response` to the cache, ensuring debug-only fields are not persisted."""
    try:
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        response_to_cache = _sanitize_for_cache(response)
        cache_coll.replace_one({"_id": cache_key}, {"_id": cache_key, "response": response_to_cache, "expiresAt": expires_at}, upsert=True)
    except Exception:
        logger.debug("Failed to write nearest cache, continuing")


def is_debug() -> bool:
    """Return True when debug query param present or app is running in debug mode."""
    return request.args.get('debug') == '1' or (current_app and getattr(current_app, 'debug', False))


def extract_coords_from_doc(doc):
    """Return (lat, lng) from a station document using known fields, or (None, None)."""
    if isinstance(doc.get('location'), dict):
        coords = doc['location'].get('coordinates')
        if isinstance(coords, list) and len(coords) >= 2:
            return coords[1], coords[0]
    if isinstance(doc.get('geo'), dict):
        coords = doc['geo'].get('coordinates')
        if isinstance(coords, list) and len(coords) >= 2:
            return coords[1], coords[0]
    if isinstance(doc.get('city'), dict):
        city_geo = doc['city'].get('geo')
        if isinstance(city_geo, dict):
            coords = city_geo.get('coordinates')
            if isinstance(coords, list) and len(coords) >= 2:
                return coords[1], coords[0]
    if 'latitude' in doc and 'longitude' in doc:
        return doc.get('latitude'), doc.get('longitude')
    return None, None


def get_latest_reading(database, station_id):
    """Return latest reading document for station_id or None (safe wrapper)."""
    try:
        if station_id is None:
            return None
        return database.waqi_station_readings.find_one({'station_id': station_id}, sort=[('timestamp', -1)])
    except Exception:
        return None


def _sanitize_for_cache(response: dict) -> dict:
    """Return a cache-safe copy of response with debug/internal fields removed.

    This mirrors `prepare_response` but forces debug_mode=False so cached
    entries never include debug-only fields and have trimmed latest_reading.
    """
    if not isinstance(response, dict):
        return response
    cleaned = {'stations': []}
    stations = response.get('stations')
    if isinstance(stations, list):
        for s in stations:
            if not isinstance(s, dict):
                continue
            # shallow copy and remove internals
            item = dict(s)
            item.pop('dist', None)
            item.pop('city_geo', None)
            # trim latest_reading similar to prepare_response
            lr = item.get('latest_reading')
            if isinstance(lr, dict):
                trimmed = {}
                for key in ('aqi', 'time', 'iaqi', 'meta'):
                    if key in lr:
                        trimmed[key] = lr[key]
                item['latest_reading'] = trimmed if trimmed else None
            cleaned['stations'].append(item)
    return cleaned


@stations_bp.route('', methods=['GET'])
@stations_bp.route('/', methods=['GET'])
def get_stations():
    """Get list of air quality monitoring stations with pagination.

    Query parameters:
    - limit: Number of items per page (default: 20, max: 100)
    - offset: Number of items to skip (default: 0)
    - city: Filter by city name
    - country: Filter by country code

    Returns:
        JSON: List of stations with pagination info
    """
    try:
        # Parse and validate pagination parameters
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))

        # Validate limit bounds
        if limit <= 0:
            return jsonify({"error": "limit must be greater than 0"}), 400
        if limit > 100:
            return jsonify({"error": "limit cannot exceed 100"}), 400
        if offset < 0:
            return jsonify({"error": "offset must be non-negative"}), 400

        # Parse filter parameters
        city = request.args.get('city')
        country = request.args.get('country')

        # Build filter criteria
        filter_criteria = {}
        if city:
            filter_criteria['city.name'] = {"$regex": city, "$options": "i"}
        if country:
            filter_criteria['country'] = country.upper()

        # Get stations with pagination from repository
        stations, total_count = stations_repo.find_with_pagination(
            filter_dict=filter_criteria,
            limit=limit,
            offset=offset
        )

        # Convert ObjectId to string for JSON serialization
        for station in stations:
            if '_id' in station:
                station['_id'] = str(station['_id'])

        # Calculate pagination metadata
        total_pages = (total_count + limit - 1) // limit
        current_page = (offset // limit) + 1

        return jsonify({
            "stations": stations,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total_count,
                "pages": total_pages,
                "current_page": current_page,
                "has_next": offset + limit < total_count,
                "has_prev": offset > 0
            }
        }), 200

    except ValueError as e:
        return jsonify({"error": f"Invalid parameter: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Get stations error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@stations_bp.route('/nearest', methods=['GET'])
@limiter.limit("100 per hour")
def get_nearest_stations():
    """Find nearest station(s) to provided coordinates.

    Uses `$geoNear` with a geospatial index if available. If no results are
    returned (or index is missing) the function falls back to a server-side
    haversine scan over legacy `geo` or `latitude`/`longitude` fields and an
    exact-coordinate lookup as a last resort.
    """
    try:
        # Validate coordinates
        lat_raw = request.args.get('lat')
        lng_raw = request.args.get('lng')
        if lat_raw is None or lng_raw is None:
            return jsonify({"error": "lat and lng parameters are required"}), 400
        try:
            lat = float(lat_raw)
            lng = float(lng_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "lat and lng must be valid numbers"}), 400
        if not (-90.0 <= lat <= 90.0):
            return jsonify({"error": "lat out of bounds"}), 400
        if not (-180.0 <= lng <= 180.0):
            return jsonify({"error": "lng out of bounds"}), 400

        # radius parameter
        try:
            radius = float(request.args.get('radius', 25.0))
        except ValueError:
            return jsonify({"error": "Invalid radius"}), 400
        if radius <= 0:
            return jsonify({"error": "radius must be > 0"}), 400
        if radius > 50:
            return jsonify({"error": "radius cannot exceed 50 km"}), 400

        # limit
        try:
            limit = int(request.args.get('limit', 1))
        except ValueError:
            return jsonify({"error": "Invalid limit"}), 400
        if limit <= 0 or limit > 10:
            return jsonify({"error": "limit must be between 1 and 10"}), 400

        # caching key
        cache_key = f"nearest:{lat:.6f}:{lng:.6f}:{radius:.1f}:{limit}"
        # Acquire database and cache collection (handle DB unavailability)
        try:
            database = db.get_db()
            cache_coll = database.api_response_cache
        except DatabaseError as e:
            logger.error("Database unavailable for nearest lookup: %s", e)
            return jsonify({"error": "Database unavailable"}), 503

        # Diagnostics removed in production code; responses are always sanitized

        # Check cache (if DB reachable)
        cached = cache_coll.find_one({"_id": cache_key})
        if cached:
            response = cached['response']
            response.pop('_diagnostics', None)
            return jsonify(prepare_response(response)), 200

        max_meters = int(radius * 1000)
        pipeline = [
            {
                '$geoNear': {
                    'near': {'type': 'Point', 'coordinates': [lng, lat]},
                    'distanceField': 'dist.calculated',
                    'maxDistance': max_meters,
                    'spherical': True,
                    'key': 'location'
                }
            },
            {'$limit': limit},
            {
                '$lookup': {
                    'from': 'waqi_station_readings',
                    'let': {'sid': '$station_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$station_id', '$$sid']}}},
                        {'$sort': {'timestamp': -1}},
                        {'$limit': 1}
                    ],
                    'as': 'latest_reading'
                }
            },
            {
                '$project': {
                    'latest_reading': {'$arrayElemAt': ['$latest_reading', 0]},
                    'station_id': 1,
                    'name': 1,
                    'country': 1,
                    'city': 1,
                    'location': 1,
                    'dist': 1
                }
            }
        ]

        # Run aggregation with a retry for missing geospatial index
        try:
            results = list(database.waqi_stations.aggregate(pipeline))
            # geo aggregation returned N results
        except OperationFailure as e:
            msg = str(e).lower()
            logger.warning("Aggregation failed with OperationFailure: %s", e)
            # record geo aggregation error (removed diagnostics for responses)
            # If failure due to missing geospatial index, try to create indexes and retry once
            if 'geonear' in msg or 'geo near' in msg or 'unable to find index' in msg or '$geonear' in msg:
                logger.info("Attempting to create geospatial indexes and retry aggregation")
                try:
                    db.ensure_indexes()
                except Exception as idx_e:
                    logger.error("Failed to create indexes during geo fallback: %s", idx_e)
                else:
                    try:
                        results = list(database.waqi_stations.aggregate(pipeline))
                        # geo retry aggregation returned N results
                    except Exception as retry_e:
                        logger.exception("Retry after index creation failed: %s", retry_e)
                        return jsonify({"error": "Internal server error"}), 500
            else:
                logger.exception("Aggregation OperationFailure not related to missing index: %s", e)
                return jsonify({"error": "Internal server error"}), 500

        # If aggregation returned results, format and return
        if results:
            response_list = []
            for doc in results:
                dist_km = _compute_distance_km_from_doc(doc, lat, lng)
                item = doc.copy()
                item['_distance_km'] = dist_km
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                response_list.append(item)

            response = {"stations": response_list}

            # Cache response (sanitized inside helper)
            _cache_response(response, cache_coll, cache_key)

                # debug diagnostics removed from responses

            return jsonify(prepare_response(response)), 200

        # Try alternate geo field `city.geo` (some documents keep coordinates there)
        try:
            alt_pipeline = [
                {
                    '$geoNear': {
                        'near': {'type': 'Point', 'coordinates': [lng, lat]},
                        'distanceField': 'dist.calculated',
                        'maxDistance': max_meters,
                        'spherical': True,
                        'key': 'city.geo'
                    }
                },
                {'$limit': limit},
                {
                    '$lookup': {
                        'from': 'waqi_station_readings',
                        'let': {'sid': '$station_id'},
                        'pipeline': [
                            {'$match': {'$expr': {'$eq': ['$station_id', '$$sid']}}},
                            {'$sort': {'timestamp': -1}},
                            {'$limit': 1}
                        ],
                        'as': 'latest_reading'
                    }
                },
                {
                    '$project': {
                        'latest_reading': {'$arrayElemAt': ['$latest_reading', 0]},
                        'station_id': 1,
                        'name': 1,
                        'country': 1,
                        'city': 1,
                        'location': 1,
                        'dist': 1,
                        'city_geo': '$city.geo'
                    }
                }
            ]

            alt_results = list(database.waqi_stations.aggregate(alt_pipeline))
            if alt_results:
                # Normalize docs to include `location` from `city.geo` when missing
                normalized_results = []
                for doc in alt_results:
                    if not doc.get('location') and isinstance(doc.get('city_geo'), dict):
                        doc['location'] = doc.get('city_geo')
                    normalized_results.append(doc)

                results = normalized_results

                response_list = []
                for doc in results:
                    dist_km = _compute_distance_km_from_doc(doc, lat, lng)
                    item = doc.copy()
                    item['_distance_km'] = dist_km
                    if '_id' in item:
                        item['_id'] = str(item['_id'])
                    response_list.append(item)

                response = {"stations": response_list}

                _cache_response(response, cache_coll, cache_key)
                return jsonify(prepare_response(response)), 200
        except OperationFailure as e:
            logger.warning("Alternate geoNear on city.geo failed: %s", e)
            # continue to legacy fallback

        # No results from geo-indexed aggregation: perform legacy fallback
        logger.info("No geo-indexed results; attempting legacy-geo fallback")
        try:
            cursor = database.waqi_stations.find(
                {
                    '$or': [
                        {'location.coordinates': {'$exists': True}},
                        {'geo.coordinates': {'$exists': True}},
                        {'city.geo.coordinates': {'$exists': True}},
                        {'latitude': {'$exists': True}, 'longitude': {'$exists': True}}
                    ]
                },
                {
                    'station_id': 1,
                    'name': 1,
                    'country': 1,
                    'city': 1,
                    'geo': 1,
                    'location': 1,
                    'latitude': 1,
                    'longitude': 1,
                    'timestamp': 1
                }
            )

            candidates = []
            scanned = 0
            for doc in cursor:
                scanned += 1
                station_lng = station_lat = None
                if isinstance(doc.get('location'), dict):
                    coords = doc['location'].get('coordinates')
                    if isinstance(coords, list) and len(coords) >= 2:
                        station_lng, station_lat = coords[0], coords[1]
                if station_lng is None and isinstance(doc.get('geo'), dict):
                    coords = doc['geo'].get('coordinates')
                    if isinstance(coords, list) and len(coords) >= 2:
                        station_lng, station_lat = coords[0], coords[1]
                # some documents store coordinates under city.geo per schema
                if station_lng is None and isinstance(doc.get('city'), dict):
                    city_geo = doc['city'].get('geo')
                    if isinstance(city_geo, dict):
                        coords = city_geo.get('coordinates')
                        if isinstance(coords, list) and len(coords) >= 2:
                            station_lng, station_lat = coords[0], coords[1]
                if station_lng is None and 'latitude' in doc and 'longitude' in doc:
                    station_lat = doc.get('latitude')
                    station_lng = doc.get('longitude')

                if station_lat is None or station_lng is None:
                    continue

                try:
                    dist_km = haversine_distance_km((lat, lng), (station_lat, station_lng))
                except Exception:
                    continue

                if dist_km <= radius:
                    normalized = {
                        'station_id': doc.get('station_id'),
                        'name': doc.get('name'),
                        'country': doc.get('country'),
                        'city': doc.get('city'),
                        'location': {'type': 'Point', 'coordinates': [station_lng, station_lat]},
                        '_id': str(doc.get('_id')) if doc.get('_id') else None,
                        '_distance_km': format_km(dist_km)
                    }
                    candidates.append((dist_km, doc, normalized))

            logger.debug("Legacy fallback scanned %d documents, found %d candidates", scanned, len(candidates))
            # legacy scanned/ candidates recorded in logs only
            logger.debug("Legacy scanned %d candidates", len(candidates))

            candidates.sort(key=lambda x: x[0])
            selected = candidates[:limit]

            # Exact-match fallback if still empty
            if not selected:
                exact_q = {
                    '$or': [
                        {'location.coordinates.0': lng, 'location.coordinates.1': lat},
                        {'geo.coordinates.0': lng, 'geo.coordinates.1': lat},
                        {'city.geo.coordinates.0': lng, 'city.geo.coordinates.1': lat},
                        {'latitude': lat, 'longitude': lng}
                    ]
                }
                logger.debug('Attempting exact-coordinate lookup with query: %s', exact_q)
                doc = database.waqi_stations.find_one(exact_q, {'station_id':1, 'name':1, 'country':1, 'city':1, 'geo':1, 'location':1, 'latitude':1, 'longitude':1, '_id':1})
                if doc:
                    station_lng = station_lat = None
                    if isinstance(doc.get('location'), dict):
                        coords = doc['location'].get('coordinates')
                        if isinstance(coords, list) and len(coords) >= 2:
                            station_lng, station_lat = coords[0], coords[1]
                    if station_lng is None and isinstance(doc.get('geo'), dict):
                        coords = doc['geo'].get('coordinates')
                        if isinstance(coords, list) and len(coords) >= 2:
                            station_lng, station_lat = coords[0], coords[1]
                    if station_lng is None and isinstance(doc.get('city'), dict):
                        city_geo = doc['city'].get('geo')
                        if isinstance(city_geo, dict):
                            coords = city_geo.get('coordinates')
                            if isinstance(coords, list) and len(coords) >= 2:
                                station_lng, station_lat = coords[0], coords[1]
                    if station_lng is None and 'latitude' in doc and 'longitude' in doc:
                        station_lat = doc.get('latitude')
                        station_lng = doc.get('longitude')

                    if station_lat is not None and station_lng is not None:
                        normalized = {
                            'station_id': doc.get('station_id'),
                            'name': doc.get('name'),
                            'country': doc.get('country'),
                            'city': doc.get('city'),
                            'location': {'type': 'Point', 'coordinates': [station_lng, station_lat]},
                            '_id': str(doc.get('_id')) if doc.get('_id') else None,
                            '_distance_km': format_km(haversine_distance_km((lat, lng), (station_lat, station_lng)))
                        }
                        latest = None
                        try:
                            sid = doc.get('station_id')
                            if sid is not None:
                                latest = database.waqi_station_readings.find_one({'station_id': sid}, sort=[('timestamp', -1)])
                        except Exception:
                            latest = None
                        item = normalized.copy()
                        item['latest_reading'] = latest if latest else None
                        response = {"stations": [item]}
                        # exact match found
                        # Cache sanitized response
                        _cache_response(response, cache_coll, cache_key)
                        # exact match found
                        return jsonify(prepare_response(response)), 200

            # Build response from selected candidates
            response_list = []
            for dist_km, doc, normalized in selected:
                latest = None
                try:
                    sid = doc.get('station_id')
                    if sid is not None:
                        latest = database.waqi_station_readings.find_one({'station_id': sid}, sort=[('timestamp', -1)])
                except Exception:
                    latest = None

                item = normalized.copy()
                item['latest_reading'] = latest if latest else None
                response_list.append(item)

            response = {"stations": response_list}

            # Cache sanitized response
            _cache_response(response, cache_coll, cache_key)

            return jsonify(prepare_response(response)), 200

        except Exception as e:
            logger.exception("Legacy geo fallback failed: %s", e)
            resp = {"stations": [], "message": "No stations found within radius"}
            # debug diagnostics removed from responses
            return jsonify(resp), 200

    except Exception as e:
        # Log the exception with a short error code to help triage without leaking stack traces to clients
        error_code = f"NS-{int(datetime.utcnow().timestamp())}"
        logger.exception("Nearest station lookup failed (%s): %s", error_code, e)
        # In development only, include traceback in response to aid debugging
        if current_app and getattr(current_app, 'debug', False):
            tb = traceback.format_exc()
            return jsonify({"error": "Internal server error", "code": error_code, "traceback": tb}), 500
        return jsonify({"error": "Internal server error", "code": error_code}), 500


@stations_bp.route('/health', methods=['GET'])
def health():
    """Lightweight health endpoint returning DB connectivity and basic server info."""
    try:
        status = db.health_check()
        return jsonify(status), 200 if status.get('status') == 'healthy' else 503
    except Exception as e:
        logger.exception("Health check failed: %s", e)
        return jsonify({"status": "unhealthy", "error": "Health check failed"}), 503


@stations_bp.route('/<station_id>', methods=['GET'])
def get_station(station_id):
    """Get details for a specific station.

    Args:
        station_id: Station ID (can be numeric ID or station_id string)

    Returns:
        JSON: Station details or error message
    """
    try:
        # Try to find by station_id first (string identifier)
        station = stations_repo.find_by_station_id(station_id)

        if not station:
            # If not found, try numeric lookup for backwards compatibility
            try:
                numeric_id = int(station_id)
                station = stations_repo.find_one({"id": numeric_id})
            except ValueError:
                pass

        if not station:
            return jsonify({"error": "Station not found"}), 404

        # Convert ObjectId to string for JSON serialization
        if '_id' in station:
            station['_id'] = str(station['_id'])

        return jsonify(station), 200

    except Exception as e:
        logger.error(f"Get station error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@stations_bp.route('/', methods=['POST'])
def create_station():
    """Create a new monitoring station.

    Expected JSON body:
    {
        "name": "Station Name",
        "city": "City Name",
        "country": "Country Code",
        "latitude": 12.345,
        "longitude": 67.890
    }

    Returns:
        JSON: Created station info or error message
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400

        required_fields = ['name', 'city', 'country', 'latitude', 'longitude']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # TODO: Implement station creation in MongoDB
        return jsonify({
            "message": "Station created successfully",
            "station": data
        }), 201

    except Exception as e:
        logger.error(f"Create station error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

