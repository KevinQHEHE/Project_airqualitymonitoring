"""User Subscriptions API - wrapper around alerts subscriptions with JWT auth."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import logging
import unicodedata
import re

from backend.app.repositories import users_repo, readings_repo
from backend.app import db as db_module

logger = logging.getLogger(__name__)

_GENERIC_STATION_LABEL_RE = re.compile(r'^\s*(?:TRAM|STATION)(?:[\s\-_/]*)\d+\s*$', re.IGNORECASE)

def _normalize_station_label(name: str) -> str:
    normalized = unicodedata.normalize('NFKD', name)
    stripped = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    collapsed = re.sub(r'\s+', ' ', stripped.replace('đ', 'd').replace('Đ', 'D')).strip()
    return collapsed.upper()

def _is_generic_station_label(name: str) -> bool:
    if not isinstance(name, str) or not name.strip():
        return True
    return bool(_GENERIC_STATION_LABEL_RE.match(_normalize_station_label(name)))


def _resolve_station_names(sub, station, station_id_int):
    metadata = sub.get('metadata') or {}
    nickname_meta = metadata.get('nickname')

    def normalize_candidate(value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    def collect_from_mapping(mapping, keys):
        results = []
        if isinstance(mapping, dict):
            for key in keys:
                val = mapping.get(key)
                if isinstance(val, dict):
                    results.extend([
                        normalize_candidate(val.get('name')),
                        normalize_candidate(val.get('description')),
                        normalize_candidate(val.get('label')),
                    ])
                else:
                    results.append(normalize_candidate(val))
        return [v for v in results if v]

    nickname_meta = normalize_candidate(nickname_meta)
    if nickname_meta and _is_generic_station_label(nickname_meta):
        nickname_meta = None

    candidates = [
        nickname_meta,
        normalize_candidate(sub.get('station_name')),
        normalize_candidate(sub.get('name')),
        normalize_candidate(sub.get('display_name')),
        normalize_candidate(metadata.get('label')),
        normalize_candidate(metadata.get('description')),
    ]

    if station:
        station_candidates = [
            normalize_candidate(station.get('name')),
            normalize_candidate(station.get('displayName')),
            normalize_candidate(station.get('station_name')),
            normalize_candidate(station.get('full_name')),
            normalize_candidate(station.get('label')),
            normalize_candidate(station.get('description')),
        ]
        station_candidates.extend(collect_from_mapping(station.get('meta') or {}, ['name', 'label', 'displayName', 'description']))
        location = station.get('location')
        if isinstance(location, dict):
            station_candidates.extend(collect_from_mapping(location, ['name', 'displayName', 'label', 'description', 'address']))
            station_candidates.extend(collect_from_mapping(location.get('city') or {}, ['name', 'label']))
            station_candidates.extend(collect_from_mapping(location.get('region') or {}, ['name', 'label']))
        else:
            station_candidates.append(normalize_candidate(location))
        city_name = normalize_candidate((station.get('city') or {}).get('name'))
        if city_name:
            station_candidates.append(city_name)
        station_candidates = [c for c in station_candidates if c]
        candidates.extend(station_candidates)

    friendly = next((candidate for candidate in candidates if candidate and not _is_generic_station_label(candidate)), None)
    if not friendly:
        friendly = next((candidate for candidate in candidates if candidate), None)
    if not friendly:
        friendly = f"Station {station_id_int}"

    nickname = nickname_meta or friendly
    return friendly, nickname

subscriptions_bp = Blueprint('subscriptions', __name__, url_prefix='/api')


@subscriptions_bp.route('/subscriptions', methods=['GET'])
@jwt_required()
def get_user_subscriptions():
    """Get all subscriptions for the current authenticated user."""
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({"error": "unauthorized"}), 401
            
        # Get user to ensure they exist and get their email
        user = users_repo.find_by_id(user_id)
        if not user:
            return jsonify({"error": "user not found"}), 404
            
        db = db_module.get_db()
        
        # Find active subscriptions for this user
        subscriptions = list(db.alert_subscriptions.find({
            'user_id': ObjectId(user_id),
            'status': {'$ne': 'expired'}
        }).sort('createdAt', -1))

        # Transform for frontend
        result = []
        seen_stations = set()
        for sub in subscriptions:
            station_id = sub['station_id']
            # Normalize to int when possible to keep API surface consistent
            try:
                station_id_int = int(station_id)
            except Exception:
                station_id_int = station_id
            key = str(station_id_int)
            if key in seen_stations:
                logger.debug(f'Skipping duplicate subscription for station_id {key}')
                continue
            seen_stations.add(key)
            logger.info(f"Processing subscription for station_id: {station_id_int}")
            
            # Try to get latest AQI for this station using direct DB lookup
            try:
                # Prefer direct DB lookup for latest reading to avoid network dependency
                current_aqi = None
                last_updated = None
                readings = readings_repo.find_latest_by_station(station_id_int, limit=1)
                if readings:
                    latest_measurement = readings[0]
                    current_aqi = latest_measurement.get('aqi')
                    # try common timestamp fields
                    ts = latest_measurement.get('ts') or latest_measurement.get('time') or latest_measurement.get('timestamp')
                    try:
                        # Convert timestamp to Vietnam timezone (UTC+7) when possible
                        if hasattr(ts, 'isoformat'):
                            dt = ts
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            vn = dt.astimezone(timezone(timedelta(hours=7)))
                            last_updated = vn.isoformat()
                        else:
                            last_updated = str(ts) if ts is not None else None
                    except Exception:
                        last_updated = str(ts) if ts is not None else None
                    logger.info(f"Station {station_id_int} - DB AQI: {current_aqi}, timestamp: {last_updated}")
                else:
                    logger.info(f"No readings found in DB for station {station_id_int}")
            except Exception as e:
                logger.error(f"Error fetching AQI for station {station_id_int}: {e}")
                current_aqi = None
                last_updated = None
            
            # Get station info: try integer form first, then string (legacy)
            station = None
            try:
                station = db.waqi_stations.find_one({'station_id': station_id_int})
            except Exception:
                station = None
            if not station:
                try:
                    station = db.waqi_stations.find_one({'station_id': str(station_id_int)})
                except Exception:
                    station = None
            logger.info(f"Station info for {station_id_int}: {station is not None}")

            metadata = sub.get('metadata') or {}
            nickname_meta = metadata.get('nickname')
            if nickname_meta and _is_generic_station_label(nickname_meta):
                nickname_meta = None

            subscription_name_candidate = sub.get('station_name') or sub.get('name') or sub.get('display_name')
            if subscription_name_candidate and _is_generic_station_label(subscription_name_candidate):
                subscription_name_candidate = None

            station_name_candidate = None
            if station:
                for field in (station.get('name'), station.get('displayName'), station.get('station_name')):
                    if field and not _is_generic_station_label(field):
                        station_name_candidate = field
                        break
                if not station_name_candidate:
                    for field in (station.get('name'), station.get('displayName'), station.get('station_name')):
                        if field:
                            station_name_candidate = field
                            break

            friendly_name = next((value for value in [nickname_meta, subscription_name_candidate, station_name_candidate] if value), None)
            if not friendly_name or _is_generic_station_label(friendly_name):
                friendly_name = f"Station {station_id_int}"

            friendly_name, nickname_value = _resolve_station_names(sub, station, station_id_int)

            # Format createdAt to VN timezone if available
            created_at_raw = sub.get('createdAt')
            try:
                if created_at_raw and hasattr(created_at_raw, 'isoformat'):
                    dtc = created_at_raw
                    if dtc.tzinfo is None:
                        dtc = dtc.replace(tzinfo=timezone.utc)
                    created_at = dtc.astimezone(timezone(timedelta(hours=7))).isoformat()
                else:
                    created_at = created_at_raw.isoformat() if created_at_raw else ''
            except Exception:
                created_at = str(created_at_raw) if created_at_raw else ''

            result.append({
                'id': str(sub['_id']),
                'station_id': station_id_int,
                'station_name': friendly_name,
                'location': station.get('location') if station else '',
                'nickname': nickname_value,
                'threshold': sub.get('alert_threshold', 100),
                'alert_enabled': sub.get('status') == 'active',
                'created_at': created_at,
                'current_aqi': current_aqi,  # Real AQI from air-quality API
                'last_updated': last_updated  # Already VN-formatted above when present
            })
            
        return jsonify({"subscriptions": result}), 200
        
    except Exception as e:
        logger.exception("Error fetching subscriptions")
        return jsonify({"error": "internal server error"}), 500


@subscriptions_bp.route('/subscriptions/subscribe', methods=['POST'])
@jwt_required()
def subscribe_to_station():
    """Subscribe current user to a station."""
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({"error": "unauthorized"}), 401
            
        data = request.get_json() or {}
        station_id = data.get('station_id')
        if not station_id:
            return jsonify({"error": "station_id is required"}), 400
            
        try:
            station_id = int(station_id)
        except ValueError:
            return jsonify({"error": "invalid station_id"}), 400
            
        # Get user to ensure they exist
        user = users_repo.find_by_id(user_id)
        if not user:
            return jsonify({"error": "user not found"}), 404
            
        db = db_module.get_db()
        
        # Check if already subscribed
        existing = db.alert_subscriptions.find_one({
            'user_id': ObjectId(user_id),
            'station_id': {'$in': [station_id, str(station_id)]},
            'status': {'$ne': 'expired'}
        })
        if existing:
            return jsonify({"error": "already subscribed to this station"}), 409
            
        # Check subscription limit (max 10)
        count = db.alert_subscriptions.count_documents({
            'user_id': ObjectId(user_id),
            'status': {'$ne': 'expired'}
        })
        if count >= 10:
            return jsonify({"error": "subscription limit reached (maximum 10 stations)"}), 400
            
        # Create subscription
        now = datetime.now(timezone.utc)
        subscription = {
            'user_id': ObjectId(user_id),
            'station_id': station_id,
            'alert_threshold': int(data.get('threshold', 100)),
            'status': 'active' if data.get('alert_enabled', True) else 'paused',
            'createdAt': now,
            'updatedAt': None,
            'last_triggered': None,
            'email_count': 0,
            'metadata': {
                'nickname': data.get('nickname', data.get('station_name', f'Station {station_id}'))
            }
        }
        
        result = db.alert_subscriptions.insert_one(subscription)
        
        return jsonify({
            "message": "subscribed successfully",
            "subscription_id": str(result.inserted_id)
        }), 201
        
    except Exception as e:
        logger.exception("Error subscribing to station")
        return jsonify({"error": "internal server error"}), 500


@subscriptions_bp.route('/subscriptions/unsubscribe', methods=['POST'])
@jwt_required()
def unsubscribe_from_station():
    """Unsubscribe current user from a station."""
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({"error": "unauthorized"}), 401
            
        data = request.get_json() or {}
        station_id = data.get('station_id')
        if not station_id:
            return jsonify({"error": "station_id is required"}), 400
            
        try:
            station_id = int(station_id)
        except ValueError:
            return jsonify({"error": "invalid station_id"}), 400
            
        db = db_module.get_db()
        
        # Find and update subscription to expired status
        result = db.alert_subscriptions.update_one(
            {
                'user_id': ObjectId(user_id),
                'station_id': {'$in': [station_id, str(station_id)]},
                'status': {'$ne': 'expired'}
            },
            {
                '$set': {
                    'status': 'expired',
                    'updatedAt': datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            return jsonify({"error": "subscription not found"}), 404
            
        return jsonify({"message": "unsubscribed successfully"}), 200
        
    except Exception as e:
        logger.exception("Error unsubscribing from station")
        return jsonify({"error": "internal server error"}), 500


@subscriptions_bp.route('/subscriptions/<subscription_id>', methods=['PUT'])
@jwt_required()
def update_subscription(subscription_id):
    """Update subscription settings (nickname, threshold, alert_enabled)."""
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({"error": "unauthorized"}), 401
            
        try:
            sub_id = ObjectId(subscription_id)
        except Exception:
            return jsonify({"error": "invalid subscription_id"}), 400
            
        data = request.get_json() or {}
        logger.info(f"PUT /api/subscriptions/{subscription_id} - Request data: {data}")
        
        db = db_module.get_db()
        
        # Build update document
        update_doc = {'updatedAt': datetime.now(timezone.utc)}
        
        if 'threshold' in data:
            try:
                threshold = int(data['threshold'])
                logger.info(f"Processing threshold update: {threshold}")
                if 0 <= threshold <= 500:
                    update_doc['alert_threshold'] = threshold
                    logger.info(f"Threshold {threshold} added to update_doc")
                else:
                    logger.warning(f"Threshold {threshold} out of range")
                    return jsonify({"error": "threshold must be between 0 and 500"}), 400
            except ValueError:
                return jsonify({"error": "invalid threshold value"}), 400
                
        if 'alert_enabled' in data:
            update_doc['status'] = 'active' if data['alert_enabled'] else 'paused'
            
        if 'nickname' in data:
            update_doc['metadata.nickname'] = str(data['nickname'])[:100]  # limit length
            
        if len(update_doc) == 1:  # only updatedAt
            return jsonify({"error": "no valid fields to update"}), 400
            
        # Update only if user owns this subscription
        result = db.alert_subscriptions.update_one(
            {
                '_id': sub_id,
                'user_id': ObjectId(user_id),
                'status': {'$ne': 'expired'}
            },
            {'$set': update_doc}
        )
        
        if result.matched_count == 0:
            return jsonify({"error": "subscription not found or access denied"}), 404
            
        return jsonify({"message": "subscription updated successfully"}), 200
        
    except Exception as e:
        logger.exception("Error updating subscription")
        return jsonify({"error": "internal server error"}), 500

