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


def _is_signed_int(s: str) -> bool:
    try:
        if s is None:
            return False
        int(s)
        return True
    except Exception:
        return False


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
        # support single 'station' or list 'stations'
        if 'station' in response and isinstance(response['station'], dict):
            stations_iter = [response['station']]
            single = True
        else:
            stations_iter = response.get('stations') if isinstance(response.get('stations'), list) else []
            single = False

        for s in stations_iter:
            if isinstance(s, dict):
                s.pop('dist', None)
                s.pop('city_geo', None)
                # remove nested city.geo when location already present to avoid duplicate coords
                if isinstance(s.get('city'), dict) and 'geo' in s.get('city', {}):
                    try:
                        # if we also have a top-level location, drop the city's geo to avoid duplication
                        if s.get('location'):
                            s['city'].pop('geo', None)
                    except Exception:
                        s['city'].pop('geo', None)
                lr = s.get('latest_reading')
                if isinstance(lr, dict):
                    trimmed = {k: lr[k] for k in ('aqi', 'time', 'iaqi', 'meta') if k in lr}
                    s['latest_reading'] = trimmed if trimmed else None

                # Ensure minimal fallbacks so clients always get an id/name when possible
                if not s.get('station_id') and s.get('_id') is not None:
                    try:
                        s['station_id'] = str(s.get('_id'))
                    except Exception:
                        s['station_id'] = s.get('_id')

                # drop duplicate _id if station_id is present (client-facing id is station_id)
                if s.get('station_id') and s.get('_id') is not None:
                    s.pop('_id', None)

                if not s.get('name') and isinstance(s.get('city'), dict):
                    cname = s['city'].get('name')
                    if cname:
                        s['name'] = cname

                # ensure location present from city.geo when missing
                if not s.get('location') and isinstance(s.get('city'), dict):
                    city_geo = s['city'].get('geo')
                    if isinstance(city_geo, dict):
                        s['location'] = city_geo

        # if single, ensure response contains 'station' cleaned
        if single:
            response['station'] = stations_iter[0]
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


def _extract_latest_from_station_doc(doc):
    """Return a minimal latest_reading dict from a station document if possible.

    Tries several common fields used across codepaths: 'latest_reading_at',
    'latest_update_time', 'latest', 'timestamp'. Returns None if not found.
    If pollutant fields like 'aqi' or 'iaqi' exist, include them.
    """
    if not isinstance(doc, dict):
        return None
    candidates = ['latest_reading_at', 'latest_update_time', 'latest', 'timestamp', 'last_reading', 'last_update']
    for key in candidates:
        val = doc.get(key)
        if val is not None:
            lr = {'time': val, 'meta': {'source': f'station.{key}'}}
            if 'aqi' in doc and doc.get('aqi') is not None:
                lr['aqi'] = doc.get('aqi')
            if 'iaqi' in doc and isinstance(doc.get('iaqi'), dict):
                lr['iaqi'] = doc.get('iaqi')
            return lr
    # sometimes nested under city
    city = doc.get('city') if isinstance(doc.get('city'), dict) else None
    if city:
        for key in ('latest_reading_at', 'latest_update_time', 'latest'):
            val = city.get(key)
            if val is not None:
                lr = {'time': val, 'meta': {'source': f'station.city.{key}'}}
                if 'aqi' in doc and doc.get('aqi') is not None:
                    lr['aqi'] = doc.get('aqi')
                if 'iaqi' in doc and isinstance(doc.get('iaqi'), dict):
                    lr['iaqi'] = doc.get('iaqi')
                return lr
    return None


def get_latest_reading(database, station_id):
    """Return latest reading document for station_id or None (safe wrapper)."""
    try:
        if station_id is None:
            return None
        return database.waqi_station_readings.find_one({'station_id': station_id}, sort=[('ts', -1)])
    except Exception:
        return None


def _sanitize_for_cache(response: dict) -> dict:
    """Return a cache-safe copy of response with debug/internal fields removed.

    This mirrors `prepare_response` but forces debug_mode=False so cached
    entries never include debug-only fields and have trimmed latest_reading.
    """
    if not isinstance(response, dict):
        return response
    cleaned_list = []
    # handle single station or stations list
    if 'station' in response and isinstance(response['station'], dict):
        src = [response['station']]
    else:
        src = response.get('stations') if isinstance(response.get('stations'), list) else []

    for s in src:
        if not isinstance(s, dict):
            continue
        item = dict(s)
        item.pop('dist', None)
        item.pop('city_geo', None)
        # remove nested city.geo to avoid storing duplicate coordinates in cache
        if isinstance(item.get('city'), dict) and 'geo' in item.get('city', {}):
            try:
                if item.get('location'):
                    item['city'].pop('geo', None)
            except Exception:
                item['city'].pop('geo', None)
        lr = item.get('latest_reading')
        if isinstance(lr, dict):
            trimmed = {k: lr[k] for k in ('aqi', 'time', 'iaqi', 'meta') if k in lr}
            item['latest_reading'] = trimmed if trimmed else None
        cleaned_list.append(item)

    # always return single-station shape for cache
    if cleaned_list:
        return {'station': cleaned_list[0]}
    return {'station': None}


def _build_station_item(doc: dict, database, lat: float, lng: float) -> dict:
    """Normalize a station document into the single-station response format."""
    station = {}
    # normalize identifier: try several common fields
    raw_id = doc.get('_id') or doc.get('id') or doc.get('uid') or doc.get('station_id')
    station['_id'] = str(raw_id) if raw_id is not None else None
    station['station_id'] = doc.get('station_id') or doc.get('id') or doc.get('uid') or None
    # name fallbacks
    station['name'] = doc.get('name') or doc.get('station_name') or doc.get('station') or None
    station['country'] = doc.get('country') if doc.get('country') is not None else None
    station['city'] = doc.get('city') if isinstance(doc.get('city'), dict) else None
    # ensure location present
    loc = doc.get('location') or (doc.get('city', {}).get('geo') if isinstance(doc.get('city'), dict) else None) or doc.get('geo')
    station['location'] = loc if isinstance(loc, dict) else None
    dist = _compute_distance_km_from_doc(doc, lat, lng)
    # if distance couldn't be computed but coordinates exactly match, set 0.0
    if dist is None:
        # attempt to extract coords
        doc_lat, doc_lng = extract_coords_from_doc(doc)
        try:
            if doc_lat is not None and doc_lng is not None and abs(doc_lat - lat) < 1e-9 and abs(doc_lng - lng) < 1e-9:
                dist = 0.0
        except Exception:
            pass
    station['_distance_km'] = dist
    # attach latest reading (trimmed later in prepare_response)
    latest = None
    try:
        # If aggregation already included a latest_reading, prefer it
        if doc.get('latest_reading'):
            latest = doc.get('latest_reading')
        else:
            sid = doc.get('station_id')
            if sid is not None:
                latest = database.waqi_station_readings.find_one({'station_id': sid}, sort=[('ts', -1)])
        # fallback: try numeric document id
        if not latest:
            raw_id = doc.get('_id')
            if raw_id is not None:
                try:
                    latest = database.waqi_station_readings.find_one({'station_id': int(raw_id)}, sort=[('ts', -1)])
                except Exception:
                    pass
        # fallback: try stringified id
        if not latest:
            raw_id = doc.get('_id')
            if raw_id is not None:
                try:
                    latest = database.waqi_station_readings.find_one({'station_id': str(raw_id)}, sort=[('ts', -1)])
                except Exception:
                    pass
        # fallback: match by exact location coordinates in readings if available
        if not latest:
            loc = doc.get('location')
            coords = loc.get('coordinates') if isinstance(loc, dict) else None
            if coords and isinstance(coords, list) and len(coords) >= 2:
                station_lng, station_lat = coords[0], coords[1]
                try:
                    latest = database.waqi_station_readings.find_one({'location.coordinates': [station_lng, station_lat]}, sort=[('ts', -1)])
                except Exception:
                    latest = None
    except Exception:
        latest = None
    station['latest_reading'] = latest if latest else None
    # If no reading document exists, fall back to station metadata timestamp
    # Many station documents carry `latest_reading_at` (ISO string) when
    # a full reading object hasn't been persisted to `waqi_station_readings`.
    # Provide a minimal `latest_reading` object so clients receive at least
    # a time indicator (prepare_response will trim fields to a safe subset).
    if station.get('latest_reading') is None:
        lr = _extract_latest_from_station_doc(doc)
        if lr is not None:
            station['latest_reading'] = lr
            try:
                logger.info("Populated latest_reading for station %s from station doc (source=%s)", station.get('station_id') or station.get('_id'), lr.get('meta', {}).get('source'))
            except Exception:
                pass
    # fallback: if no explicit station_id, use the document id
    if not station.get('station_id') and station.get('_id'):
        station['station_id'] = station.get('_id')
    # coerce station_id to string when present
    if station.get('station_id') is not None:
        try:
            station['station_id'] = str(station['station_id'])
        except Exception:
            pass
    # If station name missing or appears to be placeholder/test data, try to
    # enrich from latest_reading.meta.station_idx by looking up the real
    # station document in the database. This handles cases where readings
    # reference the original WAQI station index but the station doc is a
    # test placeholder (e.g. 'Test City').
    try:
        name_val = station.get('name')
        is_placeholder = False
        if not name_val:
            is_placeholder = True
        else:
            try:
                lname = str(name_val).lower()
                if 'test' in lname or '__test' in lname:
                    is_placeholder = True
            except Exception:
                pass

        if is_placeholder:
            lr = station.get('latest_reading')
            meta_idx = None
            if isinstance(lr, dict):
                meta = lr.get('meta') if isinstance(lr.get('meta'), dict) else None
                if meta is not None:
                    meta_idx = meta.get('station_idx')

            if meta_idx is not None:
                # Try to find a corresponding station document by station_id
                # or by numeric/_id match using the meta index.
                cand = None
                try:
                    cand = database.waqi_stations.find_one({'station_id': str(meta_idx)})
                except Exception:
                    cand = None
                if not cand:
                    try:
                        # try numeric _id match
                        cand = database.waqi_stations.find_one({'_id': int(meta_idx)})
                    except Exception:
                        cand = None

                if cand:
                    # prefer explicit name from candidate, else city.name
                    cand_name = cand.get('name') or (cand.get('city') or {}).get('name')
                    if cand_name:
                        station['name'] = cand_name
                    # update station_id if we can
                    if not station.get('station_id') and cand.get('station_id'):
                        try:
                            station['station_id'] = str(cand.get('station_id'))
                        except Exception:
                            station['station_id'] = cand.get('station_id')
                    # copy location/city if missing
                    if not station.get('location') and cand.get('location'):
                        station['location'] = cand.get('location')
                    if not station.get('city') and cand.get('city'):
                        station['city'] = cand.get('city')
    except Exception:
        # don't fail the whole response if enrichment fails
        pass
    # ALWAYS use city name as station name (since stations don't have explicit names)
    if isinstance(station.get('city'), dict):
        cname = station['city'].get('name')
        if cname:
            station['name'] = cname
            # Clear any test city artifacts
            if 'city' in station and isinstance(station['city'], dict):
                # If the original city had 'Test City', update it to the real name
                if station['city'].get('name') == 'Test City':
                    station['city']['name'] = cname
    # ensure location from city.geo if absent
    if not station.get('location') and isinstance(station.get('city'), dict):
        city_geo = station['city'].get('geo')
        if isinstance(city_geo, dict):
            station['location'] = city_geo

    # prune top-level None values for cleaner client response
    pruned = {k: v for k, v in station.items() if v is not None}
    return pruned


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
            # If city looks like a signed integer (users sometimes paste station ids
            # into the city search box), support searching by station_id/_id as well
            # so negative indices are matched correctly.
            if _is_signed_int(city):
                try:
                    sid_int = int(city)
                except Exception:
                    sid_int = None
                or_clauses = []
                # match station_id as string
                or_clauses.append({'station_id': str(city)})
                # match station_id as numeric (some docs use numeric station_id)
                if sid_int is not None:
                    or_clauses.append({'station_id': sid_int})
                    or_clauses.append({'_id': sid_int})
                # fallback: also match city.name and city.location regex (some station docs
                # include a human-readable address in city.location). Keep case-insensitive.
                or_clauses.append({'city.name': {"$regex": city, "$options": "i"}})
                or_clauses.append({'city.location': {"$regex": city, "$options": "i"}})
                filter_criteria['$or'] = or_clauses
            else:
                # Match either the city name or the city.location (address) field
                filter_criteria['$or'] = [
                    {'city.name': {"$regex": city, "$options": "i"}},
                    {'city.location': {"$regex": city, "$options": "i"}}
                ]
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

        # For this endpoint we only return the single nearest station
        limit = 1

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
            # cached shapes may vary; prepare_response will normalize
            response.pop('_diagnostics', None)
            # Ensure cached station.latest_reading is fresh: compare with
            # the most recent reading in `waqi_station_readings` (sorted by 'ts').
            try:
                station_obj = None
                if isinstance(response, dict):
                    station_obj = response.get('station') if isinstance(response.get('station'), dict) else None
                    if station_obj is None:
                        sts = response.get('stations')
                        if isinstance(sts, list) and len(sts) > 0 and isinstance(sts[0], dict):
                            station_obj = sts[0]

                if station_obj is not None:
                    # Lookup the latest reading document from readings collection
                    latest_doc = None
                    sid = station_obj.get('station_id')
                    if sid is not None:
                        try:
                            latest_doc = database.waqi_station_readings.find_one({'station_id': sid}, sort=[('ts', -1)])
                        except Exception:
                            latest_doc = None

                    # fallback: numeric _id
                    if latest_doc is None and station_obj.get('_id') is not None:
                        try:
                            latest_doc = database.waqi_station_readings.find_one({'station_id': int(station_obj.get('_id'))}, sort=[('ts', -1)])
                        except Exception:
                            latest_doc = None

                    # fallback: match by location coordinates
                    if latest_doc is None and isinstance(station_obj.get('location'), dict):
                        coords = station_obj['location'].get('coordinates')
                        if isinstance(coords, list) and len(coords) >= 2:
                            try:
                                latest_doc = database.waqi_station_readings.find_one({'location.coordinates': [coords[0], coords[1]]}, sort=[('ts', -1)])
                            except Exception:
                                latest_doc = None

                    # If latest_doc exists, check if it's newer than cached one
                    if latest_doc is not None:
                        cached_lr = station_obj.get('latest_reading')
                        need_update = False
                        try:
                            # Determine cached timestamp / epoch
                            cached_v = None
                            cached_time_iso = None
                            if isinstance(cached_lr, dict):
                                t = cached_lr.get('time')
                                if isinstance(t, dict):
                                    cached_v = t.get('v')
                                    cached_time_iso = t.get('iso') or t.get('s')
                                else:
                                    cached_time_iso = t
                            # Latest doc values
                            latest_v = None
                            latest_time_iso = None
                            if isinstance(latest_doc.get('time'), dict):
                                latest_v = latest_doc['time'].get('v')
                                latest_time_iso = latest_doc['time'].get('iso') or latest_doc['time'].get('s')
                            # Compare using epoch if available
                            if latest_v is not None and cached_v is not None:
                                try:
                                    if int(latest_v) != int(cached_v):
                                        need_update = True
                                except Exception:
                                    need_update = True
                            elif latest_time_iso is not None and cached_time_iso is not None:
                                if latest_time_iso != cached_time_iso:
                                    need_update = True
                            else:
                                # fallback: if aqi differs
                                if isinstance(cached_lr, dict) and cached_lr.get('aqi') != latest_doc.get('aqi'):
                                    need_update = True
                        except Exception:
                            need_update = True

                        if need_update:
                            station_obj['latest_reading'] = latest_doc
                            try:
                                _cache_response(response, cache_coll, cache_key)
                            except Exception:
                                pass
            except Exception:
                # ignore enrichment failures and return cached response
                pass

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
                        {'$match': {'$expr': {'$or': [
                            {'$eq': ['$station_id', '$$sid']},
                            {'$eq': ['$meta.station_idx', {'$toInt': '$$sid'}]}
                        ]}}},
                        {'$sort': {'ts': -1}},
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
            # Only first (nearest) result is needed
            doc = results[0]
            station_item = _build_station_item(doc, database, lat, lng)
            response = {"station": station_item}
            _cache_response(response, cache_coll, cache_key)
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
                            {'$match': {'$expr': {'$or': [
                                {'$eq': ['$station_id', '$$sid']},
                                {'$eq': ['$meta.station_idx', {'$toInt': '$$sid'}]}
                            ]}}},
                            {'$sort': {'ts': -1}},
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
                for doc in alt_results:
                    if not doc.get('location') and isinstance(doc.get('city_geo'), dict):
                        doc['location'] = doc.get('city_geo')
                doc = alt_results[0]
                station_item = _build_station_item(doc, database, lat, lng)
                response = {"station": station_item}
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
                                latest = database.waqi_station_readings.find_one({'station_id': sid}, sort=[('ts', -1)])
                        except Exception:
                            latest = None
                        item = normalized.copy()
                        item['latest_reading'] = latest if latest else None
                        response = {"station": item}
                        _cache_response(response, cache_coll, cache_key)
                        return jsonify(prepare_response(response)), 200

            # Build response from selected candidates
            # Use first selected candidate (nearest)
            dist_km, doc, normalized = selected[0]
            latest = None
            try:
                sid = doc.get('station_id')
                if sid is not None:
                    latest = database.waqi_station_readings.find_one({'station_id': sid}, sort=[('ts', -1)])
            except Exception:
                latest = None

            item = normalized.copy()
            item['latest_reading'] = latest if latest else None
            response = {"station": item}
            _cache_response(response, cache_coll, cache_key)
            return jsonify(prepare_response(response)), 200

        except Exception as e:
            logger.exception("Legacy geo fallback failed: %s", e)
            resp = {"station": None, "message": "No stations found within radius"}
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


# @stations_bp.route('/health', methods=['GET'])
# def health():
#     """Lightweight health endpoint returning DB connectivity and basic server info."""
#     try:
#         status = db.health_check()
#         return jsonify(status), 200 if status.get('status') == 'healthy' else 503
#     except Exception as e:
#         logger.exception("Health check failed: %s", e)
#         return jsonify({"status": "unhealthy", "error": "Health check failed"}), 503


@stations_bp.route('/by_meta_idx/<int:meta_idx>', methods=['GET'])
def get_station_by_meta_idx(meta_idx: int):
    """Lookup a station document by numeric meta index (either station_id or _id).

    This endpoint helps clients recover a human-friendly station name when the
    nearest aggregation returned a placeholder/test document. Optional query
    params `lat` and `lng` may be provided so distance can be computed.
    """
    try:
        try:
            lat = float(request.args.get('lat')) if request.args.get('lat') is not None else None
            lng = float(request.args.get('lng')) if request.args.get('lng') is not None else None
        except Exception:
            lat = lng = None

        database = db.get_db()
    except DatabaseError:
        return jsonify({'error': 'Database unavailable'}), 503

    # Try station_id (string) then numeric _id
    doc = None
    try:
        doc = database.waqi_stations.find_one({'station_id': str(meta_idx)})
    except Exception:
        doc = None

    if not doc:
        try:
            doc = database.waqi_stations.find_one({'_id': meta_idx})
        except Exception:
            doc = None

    if not doc:
        return jsonify({'error': 'Station not found'}), 404

    station_item = _build_station_item(doc, database, lat if lat is not None else 0.0, lng if lng is not None else 0.0)
    response = {'station': station_item}
    return jsonify(prepare_response(response)), 200


@stations_bp.route('/<station_id>', methods=['GET'])
def get_station(station_id):
    """Get details for a specific station.

    Args:
        station_id: Station ID (can be numeric ID or station_id string)

    Returns:
        JSON: Station details or error message
    """
    try:
        # Try common lookup strategies in order of likelihood:
        # 1) explicit station_id string
        # 2) flexible find_by_station_ids helper (handles numeric/string mix)
        # 3) numeric id lookup
        # 4) direct _id ObjectId lookup
        station = None

        # direct station_id string match
        try:
            station = stations_repo.find_by_station_id(station_id)
        except Exception:
            station = None

        # repository helper that accepts mixed id types (tries _id and station_id)
        if not station:
            try:
                results = stations_repo.find_by_station_ids([station_id])
                if results:
                    station = results[0]
            except Exception:
                station = None

        # try numeric id (some station documents store numeric ids)
        if not station:
            try:
                numeric_id = int(station_id)
                results = stations_repo.find_by_station_ids([numeric_id])
                if results:
                    station = results[0]
            except (ValueError, TypeError):
                pass

        # try ObjectId _id lookup as a last resort
        if not station:
            try:
                station = stations_repo.find_one({'_id': ObjectId(station_id)})
            except Exception:
                station = None

        if not station:
            return jsonify({"error": "Station not found"}), 404

        # At this point `station` may be a raw DB document. To ensure
        # clients always receive a normalized shape (including an attached
        # latest_reading when available) reuse the same normalizer used by
        # the nearest/list endpoints: `_build_station_item` + `prepare_response`.
        try:
            database = db.get_db()
        except Exception:
            database = None

        try:
            # Use lat/lng from query params for distance computation when present
            try:
                lat = float(request.args.get('lat')) if request.args.get('lat') is not None else 0.0
                lng = float(request.args.get('lng')) if request.args.get('lng') is not None else 0.0
            except Exception:
                lat = 0.0
                lng = 0.0

            if isinstance(station, dict) and database is not None:
                station_item = _build_station_item(station, database, lat, lng)
                response = {'station': station_item}
                return jsonify(prepare_response(response)), 200
        except Exception:
            # If normalization fails for any reason, fall back to returning
            # the raw station document (but ensure _id is JSON-serializable).
            pass

        # Convert ObjectId to string for JSON serialization when returning raw doc
        if '_id' in station:
            try:
                station['_id'] = str(station['_id'])
            except Exception:
                pass

        return jsonify(station), 200

    except Exception as e:
        logger.error(f"Get station error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# @stations_bp.route('/', methods=['POST'])
# def create_station():
#     """Create a new monitoring station.

#     Expected JSON body:
#     {
#         "name": "Station Name",
#         "city": "City Name",
#         "country": "Country Code",
#         "latitude": 12.345,
#         "longitude": 67.890
#     }

#     Returns:
#         JSON: Created station info or error message
#     """
#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({"error": "JSON data required"}), 400

#         required_fields = ['name', 'city', 'country', 'latitude', 'longitude']
#         for field in required_fields:
#             if field not in data:
#                 return jsonify({"error": f"Missing required field: {field}"}), 400

#         # TODO: Implement station creation in MongoDB
#         return jsonify({
#             "message": "Station created successfully",
#             "station": data
#         }), 201

#     except Exception as e:
#         logger.error(f"Create station error: {str(e)}")
#         return jsonify({"error": "Internal server error"}), 500

