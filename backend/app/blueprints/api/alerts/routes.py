"""Alerts blueprint: user notification preferences and basic admin hooks.

This module exposes small endpoints to read/update a user's notification
preferences (used by the UI) and contains lightweight helpers so the
Celery task can reuse the same validation/shape. Business logic for
monitoring favorite stations runs in a background task (see
`backend.app.tasks.alerts`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from bson import ObjectId
from flask import Blueprint, request, jsonify, current_app
import os

from backend.app.repositories import users_repo
from flask_jwt_extended import verify_jwt_in_request, get_jwt

logger = logging.getLogger(__name__)

alerts_bp = Blueprint('alerts', __name__, url_prefix='/api/alerts')


@alerts_bp.route('/user/<user_id>/notifications', methods=['GET'])
def get_user_notifications(user_id: str):
	"""Return the user's notification preferences.

	Returns 404 if user not found. Response shape mirrors stored
	`preferences.notifications` object.
	"""
	user = users_repo.find_by_id(user_id)
	if not user:
		return jsonify({"error": "user not found"}), 404
	prefs = (user.get('preferences') or {}).get('notifications') or {}
	return jsonify({"userId": str(user.get('_id')), "notifications": prefs}), 200


@alerts_bp.route('/user/<user_id>/notifications', methods=['PUT'])
def update_user_notifications(user_id: str):
	"""Update notification preferences for a user.

	Body should be a JSON object that will replace `preferences.notifications`.
	Minimal validation is applied: preferences must be an object.
	"""
	data = request.get_json() or {}
	if not isinstance(data, dict):
		return jsonify({"error": "preferences must be an object"}), 400

	user = users_repo.find_by_id(user_id)
	if not user:
		return jsonify({"error": "user not found"}), 404

	# Merge into user's preferences preserving other preference keys.
	preferences = user.get('preferences') or {}
	preferences['notifications'] = data
	now = datetime.now(timezone.utc)
	try:
		users_repo.update_user_by_id(ObjectId(user.get('_id')), {'$set': {'preferences': preferences, 'updatedAt': now}})
	except Exception as exc:
		logger.exception('Failed to update notifications for user %s: %s', user_id, exc)
		return jsonify({"error": "failed to update preferences"}), 500

	return jsonify({"message": "notifications updated", "notifications": data}), 200


@alerts_bp.route('/health', methods=['GET'])
def health():
	return jsonify({"status": "ok"}), 200



@alerts_bp.route('/trigger', methods=['POST'])
def trigger_monitor():
	"""Admin/test endpoint: trigger the favorite-stations monitor.

	Protection: requires a key provided via header `X-ALERT-TEST-KEY` or
	query param `key` that must match the `ALERT_TEST_KEY` environment
	variable. This endpoint exists to help QA/development safely invoke
	the monitor over HTTP. It should NOT be enabled in production without
	proper authentication.
	"""
	# Check provided key
	provided = request.headers.get('X-ALERT-TEST-KEY') or request.args.get('key')
	secret = os.environ.get('ALERT_TEST_KEY')
	if not secret:
		return jsonify({"error": "ALERT_TEST_KEY not configured on server"}), 503
	if not provided or provided != secret:
		return jsonify({"error": "forbidden"}), 403

	# Run monitor (import inside handler to avoid circular imports at module load)
	try:
		from backend.app.tasks.alerts import monitor_favorite_stations
		monitor_favorite_stations()
		return jsonify({"message": "monitor invoked"}), 200
	except Exception as exc:
		current_app.logger.exception('Trigger monitor failed: %s', exc)
		return jsonify({"error": "monitor_failed", "details": str(exc)}), 500



@alerts_bp.route('/user/<user_id>/favorites', methods=['PUT'])
def update_user_favorites(user_id: str):
	"""Update a user's favorite stations list.

	Authentication: requires a valid JWT. Users may only update their own
	favorites; admins may update any user. The request body should be JSON
	with a `favoriteStations` array (list of station ids — numeric or string).
	"""
	try:
		# Ensure a JWT is present and get claims
		verify_jwt_in_request()
		claims = get_jwt() or {}
	except Exception:
		return jsonify({"error": "authorization_required"}), 401

	# Only allow the owning user or admins
	subject = str(claims.get('sub')) if claims.get('sub') is not None else None
	role = claims.get('role')
	if subject != str(user_id) and role != 'admin':
		return jsonify({"error": "forbidden"}), 403

	data = request.get_json(silent=True) or {}
	favs = data.get('favoriteStations') or data.get('favorites')
	if favs is None:
		return jsonify({"error": "favoriteStations is required"}), 400
	if not isinstance(favs, list):
		return jsonify({"error": "favoriteStations must be an array"}), 400

	user = users_repo.find_by_id(user_id)
	if not user:
		return jsonify({"error": "user not found"}), 404

	preferences = user.get('preferences') or {}
	preferences['favoriteStations'] = favs
	now = datetime.now(timezone.utc)
	try:
		users_repo.update_user_by_id(ObjectId(user.get('_id')), {'$set': {'preferences': preferences, 'updatedAt': now}})
	except Exception as exc:
		current_app.logger.exception('Failed to update favorites for user %s: %s', user_id, exc)
		return jsonify({"error": "failed_to_update"}), 500

	return jsonify({"message": "favorites updated", "favoriteStations": favs}), 200



# --- alert_subscriptions CRUD -------------------------------------------------


@alerts_bp.route('/subscriptions', methods=['GET'])
def list_subscriptions():
	"""List alert subscriptions.

	Optional query params:
	  - user_id: filter by user ObjectId string
	  - station_id: filter by station id string
	"""
	try:
		db = __import__('backend.app.db', fromlist=['get_db']).get_db()
		q = {}
		user_id = request.args.get('user_id')
		if user_id:
			try:
				q['user_id'] = ObjectId(user_id)
			except Exception:
				return jsonify({"error": "invalid user_id"}), 400
		station_id = request.args.get('station_id')
		if station_id:
			q['station_id'] = str(station_id)
		docs = list(db.alert_subscriptions.find(q).sort('createdAt', -1).limit(200))
		# Convert ObjectId to string for JSON
		for d in docs:
			d['_id'] = str(d.get('_id'))
			if isinstance(d.get('user_id'), ObjectId):
				d['user_id'] = str(d['user_id'])
		return jsonify({'subscriptions': docs}), 200
	except Exception as exc:
		current_app.logger.exception('Failed to list subscriptions: %s', exc)
		return jsonify({"error": "internal"}), 500


@alerts_bp.route('/subscriptions', methods=['POST'])
def create_subscription():
	"""Create a new alert subscription.

	Body JSON expected: { "user_id": "<oid>", "station_id": "<id>", "alert_threshold": 100 }
	"""
	data = request.get_json() or {}
	user_id = data.get('user_id')
	station_id = data.get('station_id')
	if not user_id or not station_id:
		return jsonify({"error": "user_id and station_id required"}), 400
	try:
		uid = ObjectId(user_id)
	except Exception:
		return jsonify({"error": "invalid user_id"}), 400
	try:
		db = __import__('backend.app.db', fromlist=['get_db']).get_db()
		now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
		doc = {
			'user_id': uid,
			'station_id': str(station_id),
			'alert_threshold': int(data.get('alert_threshold', 100)),
			'status': data.get('status', 'active'),
			'createdAt': now,
			'updatedAt': None,
			'last_triggered': None,
			'email_count': 0,
			'metadata': data.get('metadata', {}),
		}
		res = db.alert_subscriptions.insert_one(doc)
		return jsonify({'subscription_id': str(res.inserted_id)}), 201
	except Exception as exc:
		current_app.logger.exception('Failed to create subscription: %s', exc)
		return jsonify({"error": "internal"}), 500


@alerts_bp.route('/subscriptions/<sub_id>', methods=['GET'])
def get_subscription(sub_id: str):
	try:
		db = __import__('backend.app.db', fromlist=['get_db']).get_db()
		try:
			oid = ObjectId(sub_id)
		except Exception:
			return jsonify({"error": "invalid id"}), 400
		doc = db.alert_subscriptions.find_one({'_id': oid})
		if not doc:
			return jsonify({"error": "not found"}), 404
		doc['_id'] = str(doc['_id'])
		if isinstance(doc.get('user_id'), ObjectId):
			doc['user_id'] = str(doc['user_id'])
		return jsonify({'subscription': doc}), 200
	except Exception as exc:
		current_app.logger.exception('Failed to get subscription: %s', exc)
		return jsonify({"error": "internal"}), 500


@alerts_bp.route('/subscriptions/<sub_id>', methods=['PUT'])
def update_subscription(sub_id: str):
	data = request.get_json() or {}
	allowed = {'alert_threshold', 'status', 'metadata'}
	update = {k: data[k] for k in data.keys() if k in allowed}
	if not update:
		return jsonify({"error": "no updatable fields provided"}), 400
	try:
		oid = ObjectId(sub_id)
	except Exception:
		return jsonify({"error": "invalid id"}), 400
	try:
		db = __import__('backend.app.db', fromlist=['get_db']).get_db()
		update['updatedAt'] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
		db.alert_subscriptions.update_one({'_id': oid}, {'$set': update})
		return jsonify({'message': 'updated'}), 200
	except Exception as exc:
		current_app.logger.exception('Failed to update subscription: %s', exc)
		return jsonify({"error": "internal"}), 500


@alerts_bp.route('/subscriptions/<sub_id>', methods=['DELETE'])
def delete_subscription(sub_id: str):
	# Soft-delete: set status to 'deleted'
	try:
		oid = ObjectId(sub_id)
	except Exception:
		return jsonify({"error": "invalid id"}), 400
	try:
		db = __import__('backend.app.db', fromlist=['get_db']).get_db()
		# Use 'expired' to match the collection JSON schema enum
		db.alert_subscriptions.update_one(
			{'_id': oid},
			{'$set': {'status': 'expired', 'updatedAt': __import__('datetime').datetime.now(__import__('datetime').timezone.utc)}}
		)
		return jsonify({'message': 'deleted'}), 200
	except Exception as exc:
		current_app.logger.exception('Failed to delete subscription: %s', exc)
		return jsonify({"error": "internal"}), 500



@alerts_bp.route('/logs', methods=['GET'])
def list_notification_logs():
	"""Admin endpoint to list `notification_logs` entries.

	Query params:
	  - user_id: ObjectId string
	  - station_id: station id string
	  - status: delivered|failed|bounced|deferred
	  - page, page_size: pagination (defaults: 1, 50)
	"""
	try:
		db = __import__('backend.app.db', fromlist=['get_db']).get_db()
		q = {}
		user_id = request.args.get('user_id')
		if user_id:
			try:
				q['user_id'] = ObjectId(user_id)
			except Exception:
				return jsonify({"error": "invalid user_id"}), 400
		station_id = request.args.get('station_id')
		if station_id:
			q['station_id'] = str(station_id)
		status = request.args.get('status')
		if status:
			q['status'] = status

		try:
			page = int(request.args.get('page', '1'))
			page_size = int(request.args.get('page_size', '50'))
		except Exception:
			return jsonify({"error": "invalid pagination"}), 400

		skip = max(0, (page - 1) * page_size)
		cursor = db.notification_logs.find(q).sort('sentAt', -1).skip(skip).limit(page_size)
		docs = list(cursor)
		# serialise ObjectIds
		for d in docs:
			d['_id'] = str(d.get('_id'))
			if isinstance(d.get('subscription_id'), ObjectId):
				d['subscription_id'] = str(d['subscription_id'])
			if isinstance(d.get('user_id'), ObjectId):
				d['user_id'] = str(d['user_id'])

		return jsonify({'logs': docs, 'page': page, 'page_size': page_size}), 200
	except Exception as exc:
		current_app.logger.exception('Failed to list notification_logs: %s', exc)
		return jsonify({"error": "internal"}), 500

