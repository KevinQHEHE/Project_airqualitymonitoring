"""Service layer for managing user favorite locations and alert preferences.

Provides business logic: validation, user limits, CRUD operations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from backend.app.repositories import users_repo
from bson import ObjectId

MAX_FAVORITES_PER_USER = 10
DEFAULT_ALERT_THRESHOLD = 100


class FavoritesServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status


def _validate_coordinates(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _validate_threshold(value: int) -> bool:
    return isinstance(value, int) and 0 <= value <= 500


def _normalize_location(location: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure location.coordinates are numeric (floats) and in [lon, lat] order.

    Returns a shallow-copied location dict with coordinates coerced to floats.
    """
    if not location or not isinstance(location, dict):
        return location
    coords = location.get('coordinates')
    if not isinstance(coords, list) or len(coords) < 2:
        return location
    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except Exception:
        return location
    return {'type': location.get('type'), 'coordinates': [lon, lat]}


def create_favorite(user_id: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure user exists
    user = users_repo.find_by_id(user_id)
    if not user:
        raise FavoritesServiceError('user_not_found', 'User not found', 404)

    # For the current simplified model we store a single location on the user
    # document at `users.location` (GeoJSON Point). This keeps the DB schema
    # identical to the `create_users.js` validator which requires `location`.

    nickname = payload.get('nickname') or None
    if nickname and (not isinstance(nickname, str) or len(nickname) > 100):
        raise FavoritesServiceError('validation_failed', 'nickname must be a string up to 100 characters')

    alert_threshold = payload.get('alert_threshold', DEFAULT_ALERT_THRESHOLD)
    try:
        alert_threshold = int(alert_threshold)
    except Exception:
        raise FavoritesServiceError('validation_failed', 'alert_threshold must be an integer')
    if not _validate_threshold(alert_threshold):
        raise FavoritesServiceError('validation_failed', 'alert_threshold must be between 0 and 500')

    # Location validation: prefer a GeoJSON `location` object; accept legacy lat/lon
    location = payload.get('location')
    if not location:
        lat = payload.get('latitude')
        lon = payload.get('longitude')
        if lat is None or lon is None:
            raise FavoritesServiceError('validation_failed', 'location (GeoJSON) or latitude/longitude required')
        try:
            lat = float(lat); lon = float(lon)
        except Exception:
            raise FavoritesServiceError('validation_failed', 'latitude and longitude must be numbers')
        if not _validate_coordinates(lat, lon):
            raise FavoritesServiceError('validation_failed', 'latitude or longitude out of range')
        location = {'type': 'Point', 'coordinates': [lon, lat]}

    if not isinstance(location, dict):
        raise FavoritesServiceError('validation_failed', 'location must be an object')

    # validate GeoJSON shape
    if location.get('type') != 'Point' or not isinstance(location.get('coordinates'), list):
        raise FavoritesServiceError('validation_failed', 'location must be GeoJSON Point with coordinates array')
    coords = location.get('coordinates')
    if len(coords) < 2:
        raise FavoritesServiceError('validation_failed', 'location.coordinates must have at least two numbers')
    try:
        lon = float(coords[0]); lat = float(coords[1])
    except Exception:
        raise FavoritesServiceError('validation_failed', 'location.coordinates must be numbers')
    if not _validate_coordinates(lat, lon):
        raise FavoritesServiceError('validation_failed', 'latitude or longitude out of range')
    # Normalize coordinates to floats (Mongo validator requires doubles)
    location = _normalize_location(location)

    now = datetime.now(timezone.utc)
    update_ops = {'$set': {'location': location, 'updatedAt': now}}
    try:
        success = users_repo.update_user_by_id(user['_id'], update_ops)
    except Exception as e:
        # bubble up as a service error with internal status
        raise FavoritesServiceError('create_failed', f'Failed to set user location: {e}', 500)
    if not success:
        raise FavoritesServiceError('create_failed', 'Failed to set user location', 500)

    # Return a minimal favorite representation (single user location)
    return {
        'user_id': str(user['_id']),
        'nickname': nickname,
        'alert_threshold': alert_threshold,
        'location': _normalize_location(location),
        'createdAt': now.isoformat(),
        'updatedAt': now.isoformat(),
    }


def list_favorites(user_id: Any) -> List[Dict[str, Any]]:
    user = users_repo.find_by_id(user_id)
    if not user:
        raise FavoritesServiceError('user_not_found', 'User not found', 404)
    loc = user.get('location')
    if not loc:
        return []
    return [{
        'user_id': str(user.get('_id')),
        'location': _normalize_location(loc),
    }]


def get_favorite(user_id: Any, fav_id: Any) -> Dict[str, Any]:
    # Single-user location model: ignore fav_id and return user's location
    user = users_repo.find_by_id(user_id)
    if not user:
        raise FavoritesServiceError('user_not_found', 'User not found', 404)
    loc = user.get('location')
    if not loc:
        raise FavoritesServiceError('not_found', 'Favorite location not found', 404)
    return {'user_id': str(user.get('_id')), 'location': _normalize_location(loc)}


def update_favorite(user_id: Any, fav_id: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    # Update the single user location. fav_id is ignored in this simplified model.
    user = users_repo.find_by_id(user_id)
    if not user:
        raise FavoritesServiceError('user_not_found', 'User not found', 404)

    update_ops: Dict[str, Any] = {'$set': {}}
    if 'alert_threshold' in payload:
        try:
            thr = int(payload.get('alert_threshold'))
        except Exception:
            raise FavoritesServiceError('validation_failed', 'alert_threshold must be an integer')
        if not _validate_threshold(thr):
            raise FavoritesServiceError('validation_failed', 'alert_threshold must be between 0 and 500')
        update_ops['$set']['alert_threshold'] = thr

    if 'latitude' in payload or 'longitude' in payload or 'location' in payload:
        if 'location' in payload:
            location = payload.get('location')
        else:
            lat = payload.get('latitude')
            lon = payload.get('longitude')
            if lat is None or lon is None:
                raise FavoritesServiceError('validation_failed', 'both latitude and longitude required to update coordinates')
            try:
                lat = float(lat); lon = float(lon)
            except Exception:
                raise FavoritesServiceError('validation_failed', 'latitude and longitude must be numbers')
            if not _validate_coordinates(lat, lon):
                raise FavoritesServiceError('validation_failed', 'latitude or longitude out of range')
            location = {'type': 'Point', 'coordinates': [lon, lat]}

        if not isinstance(location, dict) or location.get('type') != 'Point' or not isinstance(location.get('coordinates'), list):
            raise FavoritesServiceError('validation_failed', 'location must be GeoJSON Point with coordinates array')
        # Normalize before saving to ensure coordinates are doubles for MongoDB validation
        update_ops['$set']['location'] = _normalize_location(location)

    if update_ops['$set']:
        update_ops['$set']['updatedAt'] = datetime.now(timezone.utc)
        try:
            success = users_repo.update_user_by_id(user['_id'], update_ops)
        except Exception as e:
            raise FavoritesServiceError('update_failed', f'Failed to update favorite: {e}', 500)
        if not success:
            raise FavoritesServiceError('update_failed', 'Failed to update favorite', 500)

    updated = users_repo.find_by_id(user_id)
    return {'user_id': str(updated.get('_id')), 'location': _normalize_location(updated.get('location'))}


def delete_favorite(user_id: Any, fav_id: Any) -> None:
    # Remove the user's single location. fav_id ignored.
    user = users_repo.find_by_id(user_id)
    if not user:
        raise FavoritesServiceError('user_not_found', 'User not found', 404)
    if not user.get('location'):
        raise FavoritesServiceError('not_found', 'Favorite location not found', 404)
    users_repo.update_user_by_id(user['_id'], {'$unset': {'location': ''}, '$set': {'updatedAt': datetime.now(timezone.utc)}})


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    out['id'] = str(out.get('_id'))
    out.pop('_id', None)
    # user_id should be string
    out['user_id'] = str(out.get('user_id'))
    # Convert timestamps to isoformat
    for k in ('createdAt', 'updatedAt'):
        v = out.get(k)
        if hasattr(v, 'isoformat'):
            out[k] = v.isoformat()
    return out
