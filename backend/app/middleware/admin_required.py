"""Admin RBAC decorator for API endpoints.

Validates JWT tokens and enforces the admin role before hitting route handlers.
Keep this lightweight so future admin middlewares can chain on top easily.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request

logger = logging.getLogger(__name__)


def admin_required(func: Callable[..., Any]) -> Callable[..., Any]:
    """Ensure the current request is authorized as an admin."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        verify_jwt_in_request()
        claims = get_jwt() or {}
        if claims.get("role") != "admin":
            logger.warning(
                "Admin access denied",
                extra={
                    "admin_id": claims.get("sub"),
                    "role": claims.get("role"),
                    "endpoint": func.__name__,
                },
            )
            return jsonify({"error": "admin_privileges_required"}), 403
        return func(*args, **kwargs)

    return wrapper
