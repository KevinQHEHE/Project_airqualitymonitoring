"""Lightweight tests for favorites service.

These tests are minimal and focus on validation paths.
"""
from backend.app.services.user.favorites_service import (
    _validate_coordinates,
    _validate_threshold,
    FavoritesServiceError,
)


def test_validate_coordinates():
    assert _validate_coordinates(0, 0)
    assert _validate_coordinates(45.0, 90.0)
    assert not _validate_coordinates(100.0, 0)
    assert not _validate_coordinates(0, 200.0)


def test_validate_threshold():
    assert _validate_threshold(0)
    assert _validate_threshold(250)
    assert _validate_threshold(500)
    assert not _validate_threshold(-1)
    assert not _validate_threshold(501)
