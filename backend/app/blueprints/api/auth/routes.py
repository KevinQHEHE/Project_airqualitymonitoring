"""Authentication blueprint: register and login returning JWT tokens."""
from flask import Blueprint, request, jsonify, current_app
import logging
import re
from datetime import datetime, timezone
import bcrypt
from pymongo.errors import DuplicateKeyError
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt,
)

from backend.app.repositories import users_repo
from backend.app import db as db_module
from backend.app.reset_password import (
    create_password_reset_request,
    send_password_reset_email,
    reset_password_with_token,
)
from backend.app.services.email_validator import validate_email_for_registration

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


def _serialize_user(user_doc):
    """Sanitize user document for response."""
    if not user_doc:
        return None
    created = user_doc.get("createdAt")
    if isinstance(created, datetime):
        created_iso = created.isoformat()
    else:
        created_iso = created
    return {
        "id": str(user_doc.get("_id")) if user_doc.get("_id") else None,
        "username": user_doc.get("username"),
        "email": user_doc.get("email"),
        "role": user_doc.get("role", "user"),
        "createdAt": created_iso,
    }


def _validate_email(email: str) -> bool:
    if not isinstance(email, str):
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _validate_password(password: str) -> tuple[bool, list[str]]:
    """Validate password strength.

    Rules:
    - at least 8 characters
    - at least one uppercase letter
    - at least one lowercase letter
    - at least one digit
    - at least one special character
    """
    violations: list[str] = []
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
    return (len(violations) == 0), violations


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user (hashes password)"""
    try:
        data = request.get_json(silent=True) or {}

        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()
        password = data.get('password') or ''

        if not username:
            return jsonify({"error": "username is required"}), 400
        if not email:
            return jsonify({"error": "email is required"}), 400
        if not _validate_email(email):
            return jsonify({"error": "invalid email format"}), 400

        # Email validation service: format validated above, now run deeper checks
        try:
            allowed, validation_result = validate_email_for_registration(email)
        except Exception as e:
            # Fail open: if the validation service encounters an error, allow registration
            logger.warning(f"Email validation service error: {e}")
            allowed = True
            validation_result = None

        # DEV: log validation result for troubleshooting when DEBUG is enabled
        try:
            if current_app.config.get('DEBUG'):
                vr_status = getattr(validation_result, 'status', None) if validation_result else None
                vr_reason = getattr(validation_result, 'reason', None) if validation_result else None
                logger.info(f"[DEV] Email validation for {email}: allowed={allowed}, status={vr_status}, reason={vr_reason}")
        except Exception:
            pass

        if not allowed:
            # Map result to clear error codes
            reason = getattr(validation_result, 'reason', None) if validation_result else None
            if reason == 'disposable_domain':
                return jsonify({"error": "disposable_email", "message": "Disposable email addresses are not allowed"}), 400
            if reason in ('format', 'no_mx', 'api_undeliverable'):
                return jsonify({"error": "invalid_email", "message": "Email address appears invalid"}), 400
            # generic rejection
            return jsonify({"error": "email_rejected", "message": "Email address not allowed"}), 400
        ok, violations = _validate_password(password)
        if not ok:
            return jsonify({
                "error": "weak_password",
                "message": "Password does not meet complexity requirements",
                "requirements": [
                    "at least 8 characters",
                    "at least one uppercase letter",
                    "at least one lowercase letter",
                    "at least one number",
                    "at least one special character"
                ],
                "violations": violations
            }), 400

        existing_email = users_repo.find_by_email(email)
        existing_username = users_repo.find_by_username(username)
        if existing_email or existing_username:
            if existing_email and existing_username:
                return jsonify({
                    "error": "duplicate",
                    "message": "Email and username already exist"
                }), 409
            if existing_email:
                return jsonify({
                    "error": "email_exists",
                    "message": "Email already exists"
                }), 409
            if existing_username:
                return jsonify({
                    "error": "username_exists",
                    "message": "Username already exists"
                }), 409

        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        user_doc = {
            "username": username.lower(),
            "email": email.lower(),
            "passwordHash": pw_hash,
            "role": "user",
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }

        try:
            inserted_id = users_repo.insert_one(user_doc)
        except DuplicateKeyError as e:
            try:
                details = getattr(e, 'details', None) or {}
                key_value = details.get('keyValue') or {}
                if 'email' in key_value:
                    return jsonify({"error": "email_exists", "message": "Email already exists"}), 409
                if 'username' in key_value:
                    return jsonify({"error": "username_exists", "message": "Username already exists"}), 409
            except Exception:
                pass
            return jsonify({"error": "duplicate", "message": "Email or username already exists"}), 409

        user_doc["_id"] = inserted_id

        identity = str(inserted_id)
        claims = {
            "username": user_doc["username"],
            "email": user_doc["email"],
            "role": user_doc["role"],
        }
        access_token = create_access_token(identity=identity, additional_claims=claims)
        refresh_token = create_refresh_token(identity=identity, additional_claims={"role": user_doc["role"]})

        return jsonify({
            "message": "Registration successful",
            "user": _serialize_user(user_doc),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }), 201

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and return JWT access and refresh tokens."""
    try:
        data = request.get_json(silent=True) or {}

        login_field = (data.get('email') or data.get('username') or '').strip()
        password = data.get('password') or ''

        if not login_field or not password:
            return jsonify({"error": "email/username and password are required"}), 400

        user = users_repo.find_by_email(login_field)
        if not user:
            user = users_repo.find_by_username(login_field)
        if not user:
            # Do not reveal details in production; when in DEBUG include a reason for local troubleshooting
            try:
                if current_app.config.get('DEBUG'):
                    logger.info(f"[DEV] Login failed for '{login_field}': user_not_found")
                    return jsonify({"error": "invalid credentials", "debug_reason": "user_not_found"}), 401
            except Exception:
                pass
            return jsonify({"error": "invalid credentials"}), 401

        stored = user.get('passwordHash')
        if not stored or not bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')):
            try:
                if current_app.config.get('DEBUG'):
                    logger.info(f"[DEV] Login failed for '{login_field}': bad_password")
                    return jsonify({"error": "invalid credentials", "debug_reason": "bad_password"}), 401
            except Exception:
                pass
            return jsonify({"error": "invalid credentials"}), 401

        identity = str(user.get('_id') or '')
        claims = {
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("role", "user"),
        }
        access_token = create_access_token(identity=identity, additional_claims=claims)
        refresh_token = create_refresh_token(identity=identity, additional_claims={"role": user.get("role", "user")})

        return jsonify({
            "message": "Login successful",
            "user": _serialize_user(user),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }), 200

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Initiate password reset by sending a reset token via email.

    Always returns 200 to avoid user enumeration.
    """
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip()
        if not email:
            # maintain consistent timing while still returning 200
            return jsonify({"message": "If an account exists for that email, a reset link has been sent."}), 200
        if not _validate_email(email):
            return jsonify({"message": "If an account exists for that email, a reset link has been sent."}), 200

        # If the account exists but was created via an external provider (e.g. Google OAuth),
        # we should avoid sending a password-reset email because the user authenticates
        # externally and does not have a local password. The code keeps the response
        # generic to avoid user enumeration.
        try:
            user = users_repo.find_by_email(email)
        except Exception:
            user = None

        if user and user.get('provider') and user.get('provider') != 'local':
            # Log for operators (do not reveal to caller). Do not send reset email for
            # social/OAuth accounts.
            try:
                logger.info(f"Password reset request for {email} skipped: provider={user.get('provider')}")
            except Exception:
                pass
            return jsonify({"message": "If an account exists for that email, a reset link has been sent."}), 200

        created, token = create_password_reset_request(email, token_ttl_minutes=15)

        # Compose a friendly reset link if we know a base URL
        try:
            base_url = request.host_url.rstrip('/')
            reset_page = f"{base_url}/reset-password"  # hypothetical frontend route
        except Exception:
            reset_page = None

        if created and token:
            # In development, log the token to server logs to aid testing.
            try:
                if current_app.config.get('DEBUG'):
                    logger.info(f"[DEV] Password reset token for {email}: {token}")
            except Exception:
                pass

            send_password_reset_email(email, token=token, reset_link=reset_page)

        # Always respond with success message. If running in DEBUG and token was created,
        # include the token in the response under `dev_token` to make local testing easier.
        resp = {"message": "If an account exists for that email, a reset link has been sent."}
        try:
            if current_app.config.get('DEBUG') and created and token:
                resp['dev_token'] = token
        except Exception:
            # ignore config access errors
            pass
        return jsonify(resp), 200
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        # Still avoid leaking info
        return jsonify({"message": "If an account exists for that email, a reset link has been sent."}), 200


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Validate reset token and update password (hash stored)."""
    try:
        data = request.get_json(silent=True) or {}
        token = (data.get('token') or '').strip()
        new_password = data.get('new_password') or ''

        if not token or not new_password:
            return jsonify({"error": "token and new_password are required"}), 400

        ok, violations = _validate_password(new_password)
        if not ok:
            return jsonify({
                "error": "weak_password",
                "message": "Password does not meet complexity requirements",
                "requirements": [
                    "at least 8 characters",
                    "at least one uppercase letter",
                    "at least one lowercase letter",
                    "at least one number",
                    "at least one special character"
                ],
                "violations": violations
            }), 400

        pw_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        success = reset_password_with_token(token, pw_hash)
        if not success:
            return jsonify({"error": "invalid_or_expired_token"}), 400

        return jsonify({"message": "Password has been reset successfully"}), 200
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/verify-reset-token', methods=['POST'])
def verify_reset_token():
    """Verify that a provided reset token exists and is valid (not expired/used).

    Request JSON: { "token": "<token>" }
    Response: 200 if valid, 400 otherwise with generic message.
    """
    try:
        data = request.get_json(silent=True) or {}
        token = (data.get('token') or '').strip()
        if not token:
            return jsonify({"error": "invalid_token"}), 400

        from backend.app.reset_password import validate_reset_token

        valid = validate_reset_token(token)
        if valid:
            return jsonify({"message": "token_valid"}), 200
        return jsonify({"error": "invalid_or_expired_token"}), 400
    except Exception as e:
        logger.error(f"Verify reset token error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout_access():
    """Logout current user by revoking the presented access token.

    Requires Authorization: Bearer <access_token>
    """
    try:
        jti = get_jwt().get("jti")
        sub = get_jwt().get("sub")
        ttype = get_jwt().get("type", "access")
        database = db_module.get_db()
        database.jwt_blocklist.insert_one({
            "jti": jti,
            "user_id": sub,
            "token_type": ttype,
            "revokedAt": datetime.now(timezone.utc),
        })
        return jsonify({"message": "Logged out (access token revoked)"}), 200
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/logout_refresh', methods=['POST'])
@jwt_required(refresh=True)
def logout_refresh():
    """Revoke the presented refresh token.

    Requires Authorization: Bearer <refresh_token>
    """
    try:
        jti = get_jwt().get("jti")
        sub = get_jwt().get("sub")
        database = db_module.get_db()
        database.jwt_blocklist.insert_one({
            "jti": jti,
            "user_id": sub,
            "token_type": "refresh",
            "revokedAt": datetime.now(timezone.utc),
        })
        return jsonify({"message": "Refresh token revoked"}), 200
    except Exception as e:
        logger.error(f"Logout refresh error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/verify', methods=['GET'])
@jwt_required()
def verify_access_token():
    """Simple endpoint to confirm access token validity.

    Returns 200 with a tiny payload when the provided Bearer token is valid.
    Frontend calls /api/auth/verify to check session before redirecting to dashboard.
    """
    try:
        # We don't reveal sensitive info here; return minimal confirmation and claims if present
        claims = get_jwt() or {}
        return jsonify({"message": "token_valid", "claims": claims}), 200
    except Exception as e:
        logger.info(f"Token verification failed: {e}")
        return jsonify({"error": "NOT FOUND"}), 404
