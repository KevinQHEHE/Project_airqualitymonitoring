"""Tests covering admin user management endpoints.

Focus on RBAC enforcement and that routes delegate to the service layer
without touching the database during unit tests.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from flask import Flask
try:
    from flask_jwt_extended import JWTManager, create_access_token
except ModuleNotFoundError:
    pytest.skip("flask_jwt_extended is required for admin endpoint tests", allow_module_level=True)

import backend.app.blueprints.api.admin.routes as admin_users_module
from backend.app.services.admin import user_management_service as svc


@pytest.fixture(name="app")
def fixture_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-key",
    )
    JWTManager(app)
    app.register_blueprint(admin_users_module.admin_users_bp, url_prefix="/api/admin/users")
    return app


@pytest.fixture(name="client")
def fixture_client(app: Flask):
    return app.test_client()


def _auth_header(app: Flask, role: str = "admin") -> Dict[str, str]:
    with app.app_context():
        token = create_access_token(identity="admin-1", additional_claims={"role": role})
    return {"Authorization": f"Bearer {token}"}


def test_list_users_success(app: Flask, client, monkeypatch) -> None:
    expected: Dict[str, Any] = {
        "users": [{"id": "1", "username": "alice", "status": "active"}],
        "pagination": {"page": 1, "page_size": 20, "total": 1, "pages": 1},
    }
    captured: Dict[str, Any] = {}

    def fake_list_users(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(admin_users_module.svc, "list_users", fake_list_users)

    response = client.get("/api/admin/users/", headers=_auth_header(app))
    assert response.status_code == 200
    assert response.get_json() == expected
    assert captured["initiator_id"] == "admin-1"
    assert captured["page"] == 1


def test_list_users_requires_token(client) -> None:
    response = client.get("/api/admin/users/")
    assert response.status_code == 401


def test_list_users_non_admin_forbidden(app: Flask, client, monkeypatch) -> None:
    def fake_list_users(**_kwargs):  # pragma: no cover - should not be called
        raise AssertionError("service should not be invoked for non-admin tokens")

    monkeypatch.setattr(admin_users_module.svc, "list_users", fake_list_users)

    response = client.get("/api/admin/users/", headers=_auth_header(app, role="user"))
    assert response.status_code == 403


def test_delete_user_success(app: Flask, client, monkeypatch) -> None:
    expected = {"id": "507f1f77bcf86cd799439011", "status": "inactive"}

    def fake_soft_delete(user_id: str, **kwargs):
        assert user_id == "507f1f77bcf86cd799439011"
        assert kwargs["initiator_id"] == "admin-1"
        return expected

    monkeypatch.setattr(admin_users_module.svc, "soft_delete_user", fake_soft_delete)

    response = client.delete(
        "/api/admin/users/507f1f77bcf86cd799439011",
        headers=_auth_header(app),
    )
    assert response.status_code == 200
    assert response.get_json() == expected


def test_get_user_locations_not_found(app: Flask, client, monkeypatch) -> None:
    def fake_locations(*_args, **_kwargs):
        raise svc.NotFoundError()

    monkeypatch.setattr(admin_users_module.svc, "get_user_locations", fake_locations)

    response = client.get(
        "/api/admin/users/unknown/locations",
        headers=_auth_header(app),
    )
    body = response.get_json()
    assert response.status_code == 404
    assert body["error"] == "not_found"


def test_get_user_locations_with_subscriptions(app: Flask, client, monkeypatch) -> None:
    # Prepare fake response from service to include subscriptions
    fake_result = {
        "userId": "507f1f77bcf86cd799439011",
        "favoriteLocations": [{"id": "1", "station_id": 123, "name": "Hanoi"}],
        "alertSettings": {"daily": True},
        "subscriptions": [
            {"id": "sub1", "station_id": 123, "nickname": "Home", "threshold": 150, "status": "active", "station_name": "Hanoi", "is_favorite": True}
        ],
    }

    def fake_locations(user_id: str, **_kwargs):
        assert user_id == "507f1f77bcf86cd799439011"
        return fake_result

    monkeypatch.setattr(admin_users_module.svc, "get_user_locations", fake_locations)

    response = client.get(
        "/api/admin/users/507f1f77bcf86cd799439011/locations",
        headers=_auth_header(app),
    )
    assert response.status_code == 200
    assert response.get_json() == fake_result
