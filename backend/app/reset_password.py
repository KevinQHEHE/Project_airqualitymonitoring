"""Password reset service: token generation, storage, and email sending.

This module provides helpers used by the auth blueprint for the forgot/reset
password flow. It stores only a hash of the reset token in MongoDB and emails
the opaque token to the user. Tokens expire within a short window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid
from typing import Optional, Tuple

from flask import current_app
from flask_mail import Message
import logging
from urllib.parse import quote_plus

from backend.app.extensions import mail
from backend.app.repositories import users_repo
from backend.app.repositories import (
    BaseRepository,  # type: ignore
)
from backend.app import db as db_module


class PasswordResetsRepository(BaseRepository):
    """Repository for password reset tokens."""

    def __init__(self):
        super().__init__('password_resets')

    def create_reset(self, *, user_id: str, email: str, token_hash: str, expires_at: datetime) -> str:
        now = datetime.now(timezone.utc)
        doc = {
            'user_id': user_id,
            'email': email.lower(),
            'tokenHash': token_hash,
            'createdAt': now,
            'expiresAt': expires_at,
            'usedAt': None,
        }
        inserted_id = self.insert_one(doc)
        return str(inserted_id)

    def find_valid_by_token_hash(self, token_hash: str) -> Optional[dict]:
        now = datetime.now(timezone.utc)
        return self.find_one({
            'tokenHash': token_hash,
            'usedAt': None,
            'expiresAt': { '$gt': now },
        })

    def mark_used(self, token_hash: str) -> bool:
        return self.update_one(
            {'tokenHash': token_hash, 'usedAt': None},
            {'$set': {'usedAt': datetime.now(timezone.utc)}}
        )

    def count_recent_requests(self, email: str, *, hours: int = 1) -> int:
        """Count reset requests for an email within the past `hours` hours.

        Used for simple rate limiting (e.g. max 3 per hour).
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=hours)
        try:
            return self.collection.count_documents({
                'email': email.lower(),
                'createdAt': {'$gte': window_start}
            })
        except Exception:
            # On DB error, be permissive (avoid denying legitimate users)
            return 0


password_resets_repo = PasswordResetsRepository()



def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def generate_reset_token(nbytes: Optional[int] = None) -> str:
    """Generate a URL-safe token. Length is configurable via Flask config

    - If `nbytes` passed, it is forwarded to `secrets.token_urlsafe` behavior.
    - Otherwise, we consult `current_app.config['PASSWORD_RESET_TOKEN_NBYTES']` if available,
      else fall back to a compact default (16 bytes -> ~22 chars).
    """
    try:
        from flask import current_app
        cfg_n = current_app.config.get('PASSWORD_RESET_TOKEN_NBYTES')
    except Exception:
        cfg_n = None

    if nbytes is None:
        nbytes = cfg_n or 16

    # Use token_urlsafe to produce URL-safe characters; length roughly 4/3*nbytes
    return secrets.token_urlsafe(int(nbytes))


def create_password_reset_request(email: str, *, token_ttl_minutes: Optional[int] = None, token_ttl_hours: int = 24) -> Tuple[bool, Optional[str]]:
    """Create a password reset request if the user exists.

    Returns (created, token_or_none). To avoid user enumeration, callers
    should not expose whether the user existed.
    """
    user = users_repo.find_by_email(email)
    if not user:
        # Do not indicate non-existence to caller
        return False, None

    # Rate limiting: allow max 4 reset requests per email per hour
    try:
        recent = password_resets_repo.count_recent_requests(email, hours=1)
    except Exception:
        recent = 0
    if recent >= 4:
        logger = logging.getLogger(__name__)
        logger.warning(f"Password reset rate limit exceeded for {email} (recent={recent})")
        # For security, act like the request succeeded but do not create a new token
        return False, None

    token = generate_reset_token()
    token_hash = _hash_token(token)

    # Backwards-compatible TTL behavior: if minutes provided, use minutes; else use hours
    if token_ttl_minutes is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=token_ttl_minutes)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=token_ttl_hours)

    # Persist reset request
    password_resets_repo.create_reset(
        user_id=user.get('_id'),
        email=user.get('email'),
        token_hash=token_hash,
        expires_at=expires_at,
    )

    return True, token


def send_password_reset_email(recipient_email: str, *, token: str, reset_link: Optional[str] = None) -> None:
    """Send a password reset email with the opaque token.

    If reset_link is provided, it will be included in the email; otherwise a generic
    instruction with the token will be sent.
    """
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or 'no-reply@example.com'
    subject = 'Reset your password'

    if not reset_link:
        # Fallback to a generic API hint if frontend URL is unknown
        api_url = (current_app.config.get('PUBLIC_BASE_URL') or '').rstrip('/') or 'http://localhost:5000'
        # Default to API endpoint if no frontend reset page is configured
        reset_link = f"{api_url}/api/auth/reset-password"

    # Prepare a clickable reset link that includes the token as a query parameter
    try:
        token_q = quote_plus(token)
        # If reset_link already contains a query, append with & otherwise with ?
        sep = '&' if '?' in reset_link else '?'
        token_url = f"{reset_link.rstrip('/')}{sep}token={token_q}"
    except Exception:
        token_url = reset_link

    token_lifetime = current_app.config.get('PASSWORD_RESET_TOKEN_LIFETIME_HOURS') or 24
    body = (
        "We received a request to reset your password.\n\n"
        f"Click the link below to open the reset page (this will include the token):\n{token_url}\n\n"
        f"Or use the following token directly: {token}\n\n"
        f"This token will expire in approximately {token_lifetime} hours and can only be used once.\n\n"
        f"Alternatively, POST to: {reset_link} with JSON {{\"token\": \"<above token>\", \"new_password\": \"<NewP@ssw0rd>\"}}\n\n"
        "If you did not request this, you can safely ignore this email."
    )

    msg = Message(subject=subject, body=body, recipients=[recipient_email], sender=sender)
    # Log attempt to send email for debugging; do not include secrets
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"Attempting to send password reset email to {recipient_email}")
        mail.send(msg)
        logger.info(f"Password reset email sent to {recipient_email}")
        return True
    except Exception:
        # Log full traceback for operators (without revealing tokens)
        logger.exception(f"Failed to send password reset email to {recipient_email}")
        # Re-raise only in DEBUG to surface issues during development
        try:
            if current_app.config.get('DEBUG'):
                raise
        except Exception:
            # In non-debug, swallow to keep user-facing flow generic
            pass
        return False


def reset_password_with_token(token: str, new_password_hash: str) -> bool:
    """Validate token and update the user's password hash.

    Returns True on success, False if token invalid/expired/used.
    """
    token_hash = _hash_token(token)
    doc = password_resets_repo.find_valid_by_token_hash(token_hash)
    if not doc:
        return False

    # Update the user's password
    database = db_module.get_db()
    res = database.users.update_one(
        {'_id': doc['user_id']},
        {
            '$set': {
                'passwordHash': new_password_hash,
                'updatedAt': datetime.now(timezone.utc)
            }
        }
    )
    if res.modified_count > 0:
        password_resets_repo.mark_used(token_hash)
        return True
    return False


def validate_reset_token(token: str) -> bool:
    """Check whether a reset token is valid (exists, not used, not expired).

    Returns True when token is valid and can be used to reset a password.
    """
    if not token:
        return False
    token_hash = _hash_token(token)
    doc = password_resets_repo.find_valid_by_token_hash(token_hash)
    return bool(doc)

