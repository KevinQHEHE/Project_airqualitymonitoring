"""API endpoints for managing user favorite locations and alert preferences.

Routes:
- POST /api/user/favorites
- GET /api/user/favorites
- PUT /api/user/favorites/<id>
- DELETE /api/user/favorites/<id>
- GET /api/user/favorites/<id>/current
"""
from __future__ import annotations

import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from backend.app.services.user.favorites_service import (
    create_favorite,
    list_favorites,
    get_favorite,
    update_favorite,
    delete_favorite,
    FavoritesServiceError,
)

logger = logging.getLogger(__name__)
favorites_bp = Blueprint('user_favorites', __name__)


def _get_user_id_from_jwt():
    claims = get_jwt() or {}
    return claims.get('sub') or claims.get('identity') or claims.get('id')


@favorites_bp.route('/', methods=['POST'])
@jwt_required()
def add_favorite():
    user_id = _get_user_id_from_jwt()
    payload = request.get_json(silent=True) or {}
    try:
        fav = create_favorite(user_id, payload)
        return jsonify(fav), 201
    except FavoritesServiceError as e:
        return jsonify({'error': e.code, 'message': e.message}), e.status
    except Exception as e:
        logger.exception('Unexpected error creating favorite')
        return jsonify({'error': 'internal_server_error'}), 500


@favorites_bp.route('/', methods=['GET'])
@jwt_required()
def list_user_favorites():
    user_id = _get_user_id_from_jwt()
    try:
        items = list_favorites(user_id)
        return jsonify({'favorites': items}), 200
    except FavoritesServiceError as e:
        return jsonify({'error': e.code, 'message': e.message}), e.status
    except Exception:
        logger.exception('Unexpected error listing favorites')
        return jsonify({'error': 'internal_server_error'}), 500


@favorites_bp.route('/<fav_id>', methods=['PUT'])
@jwt_required()
def update_user_favorite(fav_id: str):
    user_id = _get_user_id_from_jwt()
    payload = request.get_json(silent=True) or {}
    logger.debug('update_user_favorite payload: %s', payload)
    try:
        fav = update_favorite(user_id, fav_id, payload)
        return jsonify(fav), 200
    except FavoritesServiceError as e:
        return jsonify({'error': e.code, 'message': e.message}), e.status
    except Exception as e:
        logger.exception('Unexpected error updating favorite')
        # Return the exception message to the client for easier debugging (no secrets expected here)
        return jsonify({'error': 'internal_server_error', 'message': str(e)}), 500


@favorites_bp.route('/<fav_id>', methods=['DELETE'])
@jwt_required()
def delete_user_favorite(fav_id: str):
    user_id = _get_user_id_from_jwt()
    try:
        delete_favorite(user_id, fav_id)
        return jsonify({'message': 'deleted'}), 200
    except FavoritesServiceError as e:
        return jsonify({'error': e.code, 'message': e.message}), e.status
    except Exception:
        logger.exception('Unexpected error deleting favorite')
        return jsonify({'error': 'internal_server_error'}), 500


@favorites_bp.route('/<fav_id>/current', methods=['GET'])
@jwt_required()
def get_favorite_current(fav_id: str):
    # For now, return a placeholder - integrating AQI lookup is a follow-up
    user_id = _get_user_id_from_jwt()
    try:
        fav = get_favorite(user_id, fav_id)
        # TODO: fetch current AQI from readings repository or external API
        fav['current_aqi'] = None
        return jsonify(fav), 200
    except FavoritesServiceError as e:
        return jsonify({'error': e.code, 'message': e.message}), e.status
    except Exception:
        logger.exception('Unexpected error fetching current AQI for favorite')
        return jsonify({'error': 'internal_server_error'}), 500
