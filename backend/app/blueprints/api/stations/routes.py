"""Stations blueprint for managing air quality monitoring stations.

This module implements the stations endpoints. The `/nearest` endpoint is
implemented inline using a geospatial aggregation (`$geoNear`) and a
`$lookup` to fetch the latest reading for each station. This keeps the
implementation local to the blueprint so the service/middleware helpers can
be removed if desired.
"""
from flask import Blueprint, request, jsonify, current_app
import logging
from datetime import datetime, timedelta
from backend.app.repositories import stations_repo
import math


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
from backend.app.extensions import limiter
from backend.app import db
from backend.app.db import DatabaseError
import traceback
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

stations_bp = Blueprint('stations', __name__)


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

    Implementation notes:
    - Validates coordinates locally.
    - Uses `$geoNear` to get nearest stations (distance in meters).
    - Uses `$lookup` pipeline to attach latest reading (one document) to each station.
    - Caches response in `api_response_cache` with `expiresAt` for TTL.
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

        # Check cache (if DB reachable)
        cached = cache_coll.find_one({"_id": cache_key})
        if cached:
            return jsonify(cached['response']), 200
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
        except OperationFailure as e:
            msg = str(e).lower()
            logger.warning("Aggregation failed with OperationFailure: %s", e)
            # If failure due to missing geospatial index, try to create indexes and retry once
            if 'geonear' in msg or 'geo near' in msg or 'unable to find index' in msg or '$geonear' in msg:
                logger.info("Attempting to create geospatial indexes and retry aggregation")
                try:
                    db.ensure_indexes()
                except Exception as idx_e:
                    logger.error("Failed to create indexes during geo fallback: %s", idx_e)
                    # Fall through to return 500 below
                else:
                    try:
                        results = list(database.waqi_stations.aggregate(pipeline))
                    except Exception as retry_e:
                        logger.exception("Retry after index creation failed: %s", retry_e)
                        return jsonify({"error": "Internal server error"}), 500
                    # success on retry continues flow
            else:
                logger.exception("Aggregation OperationFailure not related to missing index: %s", e)
                return jsonify({"error": "Internal server error"}), 500

        if not results:
            return jsonify({"stations": [], "message": "No stations found within radius"}), 200

        response_list = []
        for doc in results:
            dist_km = None
            # `dist` may be a dict like {'calculated': <meters>} or a numeric value depending on driver/version
            dist_field = doc.get('dist', None)
            dist_m = None
            if isinstance(dist_field, dict):
                dist_m = dist_field.get('calculated')
            elif isinstance(dist_field, (int, float)):
                dist_m = dist_field

            if isinstance(dist_m, (int, float)):
                dist_km = round(dist_m / 1000.0 + 1e-12, 2)
            else:
                # fallback: if location present, compute haversine
                loc = doc.get('location') or {}
                coords = loc.get('coordinates') if isinstance(loc, dict) else None
                if coords and isinstance(coords, list) and len(coords) >= 2:
                    station_lng, station_lat = coords[0], coords[1]
                    dist_km = format_km(haversine_distance_km((lat, lng), (station_lat, station_lng)))

            item = doc.copy()
            item['_distance_km'] = dist_km
            if '_id' in item:
                item['_id'] = str(item['_id'])
            response_list.append(item)

        response = {"stations": response_list}

        # write cache with expiresAt so a TTL index can remove it after 5 minutes
        try:
            expires_at = datetime.utcnow() + timedelta(seconds=300)
            cache_coll.replace_one({"_id": cache_key}, {"_id": cache_key, "response": response, "expiresAt": expires_at}, upsert=True)
            # ensure TTL index exists (idempotent): expire documents at the time in expiresAt
            try:
                cache_coll.create_index('expiresAt', expireAfterSeconds=0)
            except Exception:
                # ignore index creation errors
                pass
        except Exception:
            logger.debug("Failed to write nearest cache, continuing")

        return jsonify(response), 200

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
                # Convert to int and look up by numeric ID if applicable
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
