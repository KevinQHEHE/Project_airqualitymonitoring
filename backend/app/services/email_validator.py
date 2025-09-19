"""Wrapper service used by routes to validate emails.

Provides a simple function `validate_email_for_registration` which returns
an actionable tuple (allowed: bool, result: ValidationResult).
"""
from __future__ import annotations

from backend.app.services.email_validation_service import get_default_service, ValidationResult
from flask import current_app


def validate_email_for_registration(email: str) -> tuple[bool, ValidationResult]:
    svc = get_default_service()
    strictness = current_app.config.get('EMAIL_VALIDATION_STRICTNESS', 'medium')
    res = svc.validate(email, strict=strictness)
    # Allowed if explicit 'valid'
    allowed = res.status == 'valid'
    # If strictness low, accept 'risky' too
    if not allowed and strictness == 'low' and res.status == 'risky':
        allowed = True
    return allowed, res
