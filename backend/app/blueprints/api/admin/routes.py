"""Admin user management API blueprint.

Provides CRUD endpoints for admins to manage users and inspect alert locations.
All persistence and validation lives in the service layer to keep routes thin.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt

from backend.app.middleware.admin_required import admin_required
from backend.app.services.admin import user_management_service as svc
from backend.app.services.admin.user_management_service import UserServiceError

admin_users_bp = Blueprint("admin_users", __name__)
logger = logging.getLogger(__name__)


@admin_users_bp.route("/", methods=["GET"])
@admin_required
def list_admin_users():
    """List users with pagination, filtering, and sorting."""
    claims = get_jwt() or {}
    admin_id = str(claims.get("sub")) if claims.get("sub") is not None else None

    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except ValueError:
        return jsonify({"error": "validation_failed", "message": "page and page_size must be integers"}), 400

    filters: Dict[str, Any] = {}
    if request.args.get("role"):
        filters["role"] = request.args["role"]
    if request.args.get("status"):
        filters["status"] = request.args["status"]
    if request.args.get("search"):
        filters["search"] = request.args["search"]

    try:
        if request.args.get("registered_after"):
            filters["created_after"] = _parse_iso8601(request.args["registered_after"])
        if request.args.get("registered_before"):
            filters["created_before"] = _parse_iso8601(request.args["registered_before"])
    except ValueError as exc:
        return jsonify({"error": "validation_failed", "message": str(exc)}), 400

    sort_field = request.args.get("sort", svc.DEFAULT_SORT_FIELD)
    sort_direction = request.args.get("order", "desc")

    try:
        result = svc.list_users(
            page=page,
            page_size=page_size,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            initiator_id=admin_id,
        )
        return jsonify(result), 200
    except UserServiceError as error:
        return _service_error_response(error)
    except Exception:
        logger.exception("Unexpected error listing users")
        return jsonify({"error": "internal_server_error"}), 500


@admin_users_bp.route("/<user_id>", methods=["GET"])
@admin_required
def get_admin_user(user_id: str):
    """Fetch details for a single user."""
    claims = get_jwt() or {}
    admin_id = str(claims.get("sub")) if claims.get("sub") is not None else None
    try:
        result = svc.get_user_detail(user_id, initiator_id=admin_id)
        return jsonify(result), 200
    except UserServiceError as error:
        return _service_error_response(error)
    except Exception:
        logger.exception("Unexpected error retrieving user %s", user_id)
        return jsonify({"error": "internal_server_error"}), 500


@admin_users_bp.route("/", methods=["POST"])
@admin_required
def create_admin_user():
    """Create a new user via admin."""
    claims = get_jwt() or {}
    admin_id = str(claims.get("sub")) if claims.get("sub") is not None else None
    data = request.get_json(silent=True) or {}

    try:
        result = svc.create_user(data, initiator_id=admin_id)
        return jsonify(result), 201
    except UserServiceError as error:
        return _service_error_response(error)
    except Exception:
        logger.exception("Unexpected error creating user")
        return jsonify({"error": "internal_server_error"}), 500


@admin_users_bp.route("/<user_id>", methods=["PUT"])
@admin_required
def update_admin_user(user_id: str):
    """Update an existing user."""
    claims = get_jwt() or {}
    admin_id = str(claims.get("sub")) if claims.get("sub") is not None else None
    data = request.get_json(silent=True) or {}

    try:
        result = svc.update_user(user_id, data, initiator_id=admin_id)
        return jsonify(result), 200
    except UserServiceError as error:
        return _service_error_response(error)
    except Exception:
        logger.exception("Unexpected error updating user %s", user_id)
        return jsonify({"error": "internal_server_error"}), 500


@admin_users_bp.route("/<user_id>", methods=["DELETE"])
@admin_required
def delete_admin_user(user_id: str):
    """Soft delete the selected user."""
    claims = get_jwt() or {}
    admin_id = str(claims.get("sub")) if claims.get("sub") is not None else None

    try:
        result = svc.soft_delete_user(user_id, initiator_id=admin_id)
        return jsonify(result), 200
    except UserServiceError as error:
        return _service_error_response(error)
    except Exception:
        logger.exception("Unexpected error deleting user %s", user_id)
        return jsonify({"error": "internal_server_error"}), 500


@admin_users_bp.route("/<user_id>/locations", methods=["GET"])
@admin_required
def get_admin_user_locations(user_id: str):
    """Return favorite locations and alert preferences for a user."""
    claims = get_jwt() or {}
    admin_id = str(claims.get("sub")) if claims.get("sub") is not None else None

    try:
        # allow admins to optionally request expired subscriptions by passing ?include_expired=1
        include_expired = request.args.get('include_expired') in ('1', 'true', 'True')
        result = svc.get_user_locations(user_id, initiator_id=admin_id, include_expired=include_expired)
        return jsonify(result), 200
    except UserServiceError as error:
        return _service_error_response(error)
    except Exception:
        logger.exception("Unexpected error loading user %s locations", user_id)
        return jsonify({"error": "internal_server_error"}), 500


def _parse_iso8601(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _service_error_response(error: UserServiceError):
    return (
        jsonify({
            "error": error.code,
            "message": error.message,
        }),
        error.status,
    )
