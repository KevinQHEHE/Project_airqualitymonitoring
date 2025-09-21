"""Registration-time email validator wrapper.

Provides `validate_registration_email(email)` which delegates to the
existing email validation service but exposes a clearer contract for
routes to consume. Kept intentionally minimal — it returns (allowed, result).
"""
from __future__ import annotations

from .email_validator import validate_email_for_registration


def validate_registration_email(email: str) -> tuple[bool, object]:
    """Validate email for registration.

    Returns:
        (allowed: bool, result: ValidationResult|None)
    """
    return validate_email_for_registration(email)
