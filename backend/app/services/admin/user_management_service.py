"""Admin user management service layer.

Wraps repository access for admin CRUD endpoints, centralizes validation,
provides reusable serialization helpers, and emits audit-friendly logs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

import bcrypt
from bson import ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from backend.app.repositories import stations_repo, users_repo
from backend.app import db as db_module

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("backend.app.audit.admin_users")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_ROLES = {"user", "admin"}
VALID_STATUSES = {"active", "inactive"}
DEFAULT_SORT_FIELD = "createdAt"
ALLOWED_SORT_FIELDS = {
    "createdAt": "createdAt",
    "updatedAt": "updatedAt",
    "email": "email",
    "username": "username",
    "role": "role",
    "status": "status",
}


class UserServiceError(Exception):
    """Base exception for admin user management errors."""

    def __init__(self, message: str, *, status: int = 400, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class ValidationError(UserServiceError):
    """Raised when incoming data fails validation."""

    def __init__(self, message: str, *, code: str = "validation_failed") -> None:
        super().__init__(message, status=400, code=code)


class ConflictError(UserServiceError):
    """Raised when a unique constraint is violated."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status=409, code="conflict")


class NotFoundError(UserServiceError):
    """Raised when the requested user cannot be located."""

    def __init__(self, message: str = "User not found") -> None:
        super().__init__(message, status=404, code="not_found")


def list_users(
    *,
    page: int,
    page_size: int,
    filters: Optional[Dict[str, Any]] = None,
    sort_field: str = DEFAULT_SORT_FIELD,
    sort_direction: str = "desc",
    initiator_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return paginated users for admin dashboards."""
    if page < 1:
        raise ValidationError("page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise ValidationError("page_size must be between 1 and 100")

    mongo_filter = _build_filter(filters or {})
    sort_spec = _resolve_sort(sort_field, sort_direction)

    try:
        docs, total = users_repo.list_with_filters(mongo_filter, page, page_size, [sort_spec])
    except PyMongoError as exc:
        logger.error("Failed to list users: %s", exc)
        raise UserServiceError("Failed to list users", status=500) from exc

    payload = {
        "users": [_serialize_user(doc) for doc in docs],
        "pagination": _pagination_meta(page, page_size, total),
    }

    _log_action("list_users", initiator_id, details={"filters": filters or {}, "sort": sort_spec})
    return payload


def get_user_detail(user_id: str, *, initiator_id: Optional[str] = None) -> Dict[str, Any]:
    """Return a single user with preference and location data."""
    user = users_repo.find_by_id(user_id)
    if not user:
        raise NotFoundError()

    detail = _serialize_user(user, include_preferences=True)
    detail["favoriteLocations"] = _build_favorite_locations(user)
    detail["alertSettings"] = (user.get("preferences") or {}).get("notifications")

    _log_action("get_user_detail", initiator_id, target_id=detail.get("id"))
    return detail


def create_user(payload: Dict[str, Any], *, initiator_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a new user on behalf of an admin."""
    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    role = payload.get("role") or "user"
    status = payload.get("status") or "active"
    preferences = payload.get("preferences") or {}

    _validate_username(username)
    _validate_email(email)
    _validate_role(role)
    _validate_status(status)
    _validate_preferences(preferences)
    _enforce_password(password)

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    doc = {
        "username": username.lower(),
        "email": email.lower(),
        "passwordHash": pw_hash,
        "role": role,
        "status": status,
        "preferences": preferences,
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }

    try:
        new_id = users_repo.create_user(doc)
    except DuplicateKeyError as exc:
        logger.info("Admin create_user duplicate: %s", exc)
        raise ConflictError("Email or username already exists")
    except PyMongoError as exc:
        logger.error("Failed to create user: %s", exc)
        raise UserServiceError("Failed to create user", status=500) from exc

    created = users_repo.find_by_id(new_id)
    result = _serialize_user(created or doc)

    _log_action("create_user", initiator_id, target_id=result.get("id"), details={"role": role, "status": status})
    return result


def update_user(
    user_id: str,
    payload: Dict[str, Any],
    *,
    initiator_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update user profile, role, status, or preferences."""
    existing = users_repo.find_by_id(user_id)
    if not existing:
        raise NotFoundError()

    set_fields: Dict[str, Any] = {}
    unset_fields: Dict[str, Any] = {}

    if "username" in payload:
        username = (payload.get("username") or "").strip()
        _validate_username(username)
        lower_username = username.lower()
        if lower_username != existing.get("username"):
            other = users_repo.find_by_username(lower_username)
            if other and other.get("_id") != existing.get("_id"):
                raise ConflictError("Username already exists")
        set_fields["username"] = lower_username

    if "email" in payload:
        email = (payload.get("email") or "").strip()
        _validate_email(email)
        lower_email = email.lower()
        if lower_email != existing.get("email"):
            other = users_repo.find_by_email(lower_email)
            if other and other.get("_id") != existing.get("_id"):
                raise ConflictError("Email already exists")
        set_fields["email"] = lower_email

    if "role" in payload:
        role = payload.get("role") or "user"
        _validate_role(role)
        set_fields["role"] = role

    if "status" in payload:
        status = payload.get("status") or "active"
        _validate_status(status)
        set_fields["status"] = status
        if status == "active" and "deletedAt" in existing:
            unset_fields["deletedAt"] = ""

    if "preferences" in payload:
        preferences = payload.get("preferences") or {}
        _validate_preferences(preferences)
        if preferences:
            set_fields["preferences"] = preferences
        else:
            unset_fields["preferences"] = ""

    if "password" in payload and payload.get("password"):
        _enforce_password(payload["password"])
        pw_hash = bcrypt.hashpw(payload["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        set_fields["passwordHash"] = pw_hash

    if not set_fields and not unset_fields:
        raise ValidationError("No updatable fields provided")

    set_fields["updatedAt"] = datetime.now(timezone.utc)

    update_ops: Dict[str, Any] = {}
    if set_fields:
        update_ops["$set"] = set_fields
    if unset_fields:
        update_ops["$unset"] = unset_fields

    try:
        modified = users_repo.update_user_by_id(ObjectId(existing["_id"]), update_ops)
    except DuplicateKeyError as exc:
        logger.info("Admin update duplicate: %s", exc)
        raise ConflictError("Email or username already exists")
    except PyMongoError as exc:
        logger.error("Failed to update user %s: %s", user_id, exc)
        raise UserServiceError("Failed to update user", status=500) from exc

    if not modified:
        logger.debug("No fields changed for user %s", user_id)

    updated = users_repo.find_by_id(user_id)
    result = _serialize_user(updated or existing, include_preferences=True)

    _log_action("update_user", initiator_id, target_id=result.get("id"), details={"fields": list(update_ops.keys())})
    return result


def soft_delete_user(user_id: str, *, initiator_id: Optional[str] = None) -> Dict[str, Any]:
    """Soft delete a user by marking status inactive and capturing timestamp."""
    existing = users_repo.find_by_id(user_id)
    if not existing:
        raise NotFoundError()

    now = datetime.now(timezone.utc)
    update_ops = {
        "$set": {
            "status": "inactive",
            "deletedAt": now,
            "updatedAt": now,
        }
    }

    try:
        users_repo.update_user_by_id(ObjectId(existing["_id"]), update_ops)
    except PyMongoError as exc:
        logger.error("Failed to soft delete user %s: %s", user_id, exc)
        raise UserServiceError("Failed to delete user", status=500) from exc

    updated = users_repo.find_by_id(user_id)
    result = _serialize_user(updated or existing)

    _log_action("soft_delete_user", initiator_id, target_id=result.get("id"))
    return result


def get_user_locations(user_id: str, *, initiator_id: Optional[str] = None) -> Dict[str, Any]:
    """Return favorite locations and alert settings for a user."""
    user = users_repo.find_by_id(user_id)
    if not user:
        raise NotFoundError()

    favorites = _build_favorite_locations(user)
    alert_settings = (user.get("preferences") or {}).get("notifications")

    # Load active subscriptions for this user and merge with favorites
    try:
        database = db_module.get_db()
        subs_cursor = database.alert_subscriptions.find({
            'user_id': ObjectId(user_id),
            'status': {'$ne': 'expired'}
        }).sort('createdAt', -1)
        subscriptions = list(subs_cursor)
    except PyMongoError as exc:
        logger.error("Failed to load subscriptions for user %s: %s", user.get("_id"), exc)
        raise UserServiceError("Failed to load subscriptions", status=500) from exc

    # Resolve station documents for subscriptions to include station name/country
    station_ids = []
    for s in subscriptions:
        station_ids.append(s.get('station_id'))
    try:
        station_docs = stations_repo.find_by_station_ids(station_ids)
    except PyMongoError as exc:
        logger.error("Failed to load station docs for subscriptions user %s: %s", user.get("_id"), exc)
        raise UserServiceError("Failed to load subscriptions stations", status=500) from exc

    # Build map by station_id for quick lookup (station_id can be int or str)
    station_map = {}
    for st in station_docs:
        station_map[st.get('station_id')] = st

    serialized_subs: List[Dict[str, Any]] = []
    # favorite ids for quick check
    fav_ids = [(f.get('station_id')) for f in favorites]
    for sub in subscriptions:
        sid = sub.get('station_id')
        st = station_map.get(sid) or station_map.get(str(sid))
        nickname = (sub.get('metadata') or {}).get('nickname') or (st and (st.get('city') or {}).get('name'))
        serialized_subs.append(
            {
                'id': str(sub.get('_id')),
                'station_id': sid,
                'nickname': nickname,
                'threshold': sub.get('alert_threshold'),
                'status': sub.get('status'),
                'alert_enabled': sub.get('status') == 'active',
                'station_name': (st and ((st.get('city') or {}).get('name'))) if st else None,
                'is_favorite': sid in fav_ids,
                'createdAt': _serialize_datetime(sub.get('createdAt')),
            }
        )

    _log_action("get_user_locations", initiator_id, target_id=str(user.get("_id")))
    return {
        "userId": str(user.get("_id")),
        "favoriteLocations": favorites,
        "alertSettings": alert_settings,
        "subscriptions": serialized_subs,
    }


def _build_filter(filters: Dict[str, Any]) -> Dict[str, Any]:
    query: Dict[str, Any] = {}

    role = filters.get("role")
    if role:
        _validate_role(role)
        query["role"] = role

    status = filters.get("status")
    if status:
        _validate_status(status)
        query["status"] = status

    created_after = filters.get("created_after")
    created_before = filters.get("created_before")
    if created_after or created_before:
        rng: Dict[str, Any] = {}
        if created_after:
            rng["$gte"] = created_after
        if created_before:
            rng["$lte"] = created_before
        query["createdAt"] = rng

    search = (filters.get("search") or "").strip()
    if search:
        regex = re.compile(re.escape(search), re.IGNORECASE)
        query.setdefault("$or", [
            {"username": regex},
            {"email": regex},
        ])

    return query


def _resolve_sort(field: str, direction: str) -> Tuple[str, int]:
    mongo_field = ALLOWED_SORT_FIELDS.get(field, DEFAULT_SORT_FIELD)
    normalized = direction.lower()
    order = -1 if normalized in {"desc", "-1", "descending"} else 1
    return mongo_field, order


def _pagination_meta(page: int, page_size: int, total: int) -> Dict[str, Any]:
    pages = ceil(total / page_size) if page_size else 0
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
    }


def _serialize_user(user: Dict[str, Any], *, include_preferences: bool = False) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": str(user.get("_id")) if user.get("_id") is not None else None,
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role", "user"),
        "status": user.get("status", "active"),
        "createdAt": _serialize_datetime(user.get("createdAt")),
        "updatedAt": _serialize_datetime(user.get("updatedAt")),
    }
    if user.get("deletedAt"):
        data["deletedAt"] = _serialize_datetime(user.get("deletedAt"))
    if include_preferences:
        data["preferences"] = user.get("preferences") or {}
    return data


def _serialize_datetime(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_favorite_locations(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    preferences = user.get("preferences") or {}
    favorite_ids = preferences.get("favoriteStations") or []
    if not favorite_ids:
        return []
    try:
        stations = stations_repo.find_by_station_ids(favorite_ids)
    except PyMongoError as exc:
        logger.error("Failed to load favorite stations for user %s: %s", user.get("_id"), exc)
        raise UserServiceError("Failed to load favorite locations", status=500) from exc

    serialized: List[Dict[str, Any]] = []
    for station in stations:
        serialized.append(
            {
                "id": station.get("_id"),
                "station_id": station.get("station_id"),
                "name": (station.get("city") or {}).get("name"),
                "country": station.get("country"),
            }
        )
    return serialized


def _log_action(
    action: str,
    initiator_id: Optional[str],
    *,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    audit_logger.info(
        "admin_action",
        extra={
            "action": action,
            "admin_id": initiator_id,
            "target_user_id": target_id,
            "details": details or {},
        },
    )


def _validate_username(username: str) -> None:
    if not username:
        raise ValidationError("username is required")
    if len(username) < 3:
        raise ValidationError("username must be at least 3 characters")


def _validate_email(email: str) -> None:
    if not email:
        raise ValidationError("email is required")
    if not EMAIL_PATTERN.match(email):
        raise ValidationError("invalid email format")


def _validate_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise ValidationError("role must be 'user' or 'admin'")


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValidationError("status must be 'active' or 'inactive'")


def _validate_preferences(preferences: Any) -> None:
    if preferences and not isinstance(preferences, dict):
        raise ValidationError("preferences must be an object")


def _enforce_password(password: str) -> None:
    violations: List[str] = []
    if not isinstance(password, str) or len(password) < 8:
        violations.append("at least 8 characters")
    if not re.search(r"[A-Z]", password or ""):
        violations.append("at least one uppercase letter")
    if not re.search(r"[a-z]", password or ""):
        violations.append("at least one lowercase letter")
    if not re.search(r"\d", password or ""):
        violations.append("at least one number")
    if not re.search(r"[^\w\s]", password or ""):
        violations.append("at least one special character")
    if violations:
        raise ValidationError(
            "Password does not meet complexity requirements",
            code="weak_password",
        )
