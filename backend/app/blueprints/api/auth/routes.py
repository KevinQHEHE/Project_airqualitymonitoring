"""Authentication blueprint: register and login returning JWT tokens."""
from flask import Blueprint, request, jsonify, current_app, redirect
import logging
import re
from datetime import datetime, timezone
import bcrypt
from pymongo.errors import DuplicateKeyError, PyMongoError
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt,
)

from flask import make_response


from backend.app.repositories import users_repo
from backend.app import db as db_module
import threading
from backend.app.services.auth.reset_password import (
    create_password_reset_request,
    send_password_reset_email,
    reset_password_with_token,
)
from backend.app.services.auth.email_validator import validate_email_for_registration
from backend.app.services.auth.registration_validator import validate_registration_email
from backend.app.extensions import limiter
from bson import ObjectId

# Optional: use zxcvbn if installed for a better password strength score
try:
    from zxcvbn import zxcvbn  # type: ignore
except Exception:
    zxcvbn = None

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
@limiter.limit("5 per hour")
def register():
    """Register a new user (hashes password)

    Enhanced validations:
    - structured error responses per-field
    - email validation via registration_validator
    - password strength scoring with zxcvbn (optional)
    - terms-of-service acceptance required
    """
    try:
        data = request.get_json(silent=True) or {}

        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()
        password = data.get('password') or ''
        accept_tos = data.get('accept_tos') or False

        errors: dict = {}

        if not username:
            errors['username'] = 'username is required'
        if not email:
            errors['email'] = 'email is required'
        elif not _validate_email(email):
            errors['email'] = 'invalid email format'
        if not accept_tos:
            errors['accept_tos'] = 'You must accept the Terms of Service to continue'

        # If any quick validation failed, return structured errors
        if errors:
            return jsonify({"error": "validation_failed", "errors": errors}), 400

        # Email validation service: format validated above, now run deeper checks
        try:
            allowed, validation_result = validate_registration_email(email)
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
            # Map result to clear error codes and return a consistent errors mapping
            reason = getattr(validation_result, 'reason', None) if validation_result else None
            if reason == 'disposable_domain':
                body = {
                    "error": "validation_failed",
                    "errors": {"email": "Disposable email addresses are not allowed"}
                }
                try:
                    if current_app.config.get('DEBUG') and validation_result:
                        body['debug'] = {'email_validation': validation_result.__dict__}
                except Exception:
                    pass
                return jsonify(body), 400
            if reason in ('format', 'no_mx', 'api_undeliverable'):
                body = {
                    "error": "validation_failed",
                    "errors": {"email": "Email address appears invalid"}
                }
                try:
                    if current_app.config.get('DEBUG') and validation_result:
                        body['debug'] = {'email_validation': validation_result.__dict__}
                except Exception:
                    pass
                return jsonify(body), 400
            # generic rejection
            body = {
                "error": "validation_failed",
                "errors": {"email": "Email address not allowed"}
            }
            try:
                if current_app.config.get('DEBUG') and validation_result:
                    body['debug'] = {'email_validation': validation_result.__dict__}
            except Exception:
                pass
            return jsonify(body), 400
        # Password checks: complexity + optional zxcvbn score
        ok, violations = _validate_password(password)
        pw_score = None
        pw_feedback = None
        try:
            if zxcvbn and password:
                res = zxcvbn(password, user_inputs=[username, email])
                pw_score = int(res.get('score', 0))
                pw_feedback = res.get('feedback') or None
        except Exception:
            pw_score = None
            pw_feedback = None

        if not ok or (pw_score is not None and pw_score < 2):
            # Return a consistent validation_failed envelope with password details
            password_msg = "Password does not meet complexity or strength requirements"
            errors_obj = {"password": password_msg}
            resp = {
                "error": "validation_failed",
                "errors": errors_obj,
                "details": {
                    "requirements": [
                        "at least 8 characters",
                        "at least one uppercase letter",
                        "at least one lowercase letter",
                        "at least one number",
                        "at least one special character"
                    ],
                    "violations": violations,
                }
            }
            if pw_score is not None:
                resp['details']['zxcvbn_score'] = pw_score
                if pw_feedback:
                    resp['details']['zxcvbn_feedback'] = pw_feedback
            try:
                if current_app.config.get('DEBUG'):
                    # attach raw zxcvbn output when available
                    resp.setdefault('debug', {})
                    if pw_score is not None:
                        resp['debug']['zxcvbn_score'] = pw_score
                        if pw_feedback:
                            resp['debug']['zxcvbn_feedback'] = pw_feedback
            except Exception:
                pass
            return jsonify(resp), 400
        existing_email = users_repo.find_by_email(email)
        existing_username = users_repo.find_by_username(username)
        if existing_email or existing_username:
            # Return uniform conflict payload with per-field messages
            errors_obj = {}
            if existing_email:
                errors_obj['email'] = 'Email already exists'
            if existing_username:
                errors_obj['username'] = 'Username already exists'
            return jsonify({"error": "conflict", "errors": errors_obj}), 409

        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        user_doc = {
            "username": username.lower(),
            "email": email.lower(),
            "passwordHash": pw_hash,
            # Do not write a top-level `email_verified` field because the
            # MongoDB users collection enforces a strict schema. Store
            # verification status under `preferences` instead when needed.
            # NOTE: Email verification emails are currently disabled by
            # configuration above. Do not write verification flags here to
            # avoid introducing fields that older code may not expect.
            "role": "user",
            # Optionally write a top-level status field on registration when
            # configuration requests it. This is disabled by default to
            # preserve compatibility with deployments that manage status
            # through admin APIs or expect the field to be absent.
            **({"status": "active"} if current_app.config.get('REGISTER_SET_STATUS_ON_REGISTRATION') else {}),
            # NOTE: Do not write a top-level `status` field here to avoid
            # MongoDB document validation failures on deployments that use a
            # stricter users collection schema. Login checks default to
            # "active" when the field is absent, so omitting it here is
            # safe and keeps the registration flow compatible.
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }

        try:
            inserted_id = users_repo.insert_one(user_doc)
        except DuplicateKeyError as e:
            try:
                details = getattr(e, 'details', None) or {}
                key_value = details.get('keyValue') or {}
                errors_obj = {}
                if 'email' in key_value:
                    errors_obj['email'] = 'Email already exists'
                if 'username' in key_value:
                    errors_obj['username'] = 'Username already exists'
                if errors_obj:
                    return jsonify({"error": "conflict", "errors": errors_obj}), 409
            except Exception:
                pass
            return jsonify({"error": "conflict", "errors": {"_": "Email or username already exists"}}), 409

        user_doc["_id"] = inserted_id

        identity = str(inserted_id)
        claims = {
            "username": user_doc["username"],
            "email": user_doc["email"],
            "role": user_doc["role"],
        }
        access_token = create_access_token(identity=identity, additional_claims=claims)
        refresh_token = create_refresh_token(identity=identity, additional_claims={"role": user_doc["role"]})

        # Email verification flow disabled per request: do not create or send
        # verification emails when a user registers or logs in. Keep flags for
        # compatibility in the response.
        created = False
        sent = False

        resp_body = {
            "message": "Registration successful",
            "user": _serialize_user(user_doc),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "next_steps": ["geolocation_prompt"],
            "email_verification": {
                "created": bool(created),
                "sent": bool(sent),
                "note": "Please verify your email address to unlock full account features"
            }
        }

        return jsonify(resp_body), 201

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

        if user.get("status", "active") != "active":
            return jsonify({"error": "account_inactive"}), 403

        stored = user.get('passwordHash')
        if not stored or not bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')):
            try:
                if current_app.config.get('DEBUG'):
                    logger.info(f"[DEV] Login failed for '{login_field}': bad_password")
                    return jsonify({"error": "invalid credentials", "debug_reason": "bad_password"}), 401
            except Exception:
                pass
            return jsonify({"error": "invalid credentials"}), 401

        # Email verification enforcement removed: do not block login based on
        # any email verification flags. This simplifies UX for now and avoids
        # 403 responses when accounts lack verification fields.

        identity = str(user.get('_id') or '')
        claims = {
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("role", "user"),
        }
        access_token = create_access_token(identity=identity, additional_claims=claims)
        refresh_token = create_refresh_token(identity=identity, additional_claims={"role": user.get("role", "user")})

        # Trigger a background check for alerts for this user so they receive
        # any immediate notifications after login. Run in a daemon thread so it
        # won't block the HTTP response.
        try:
            def _fire_user_monitor(u):
                try:
                    # Import locally to avoid circular imports at module import time
                    from backend.app.tasks.alerts import monitor_user_notifications
                    # Ensure a Flask application context is active so render_template
                    # and current_app inside the monitor work correctly.
                    from flask import current_app as _current_app
                    app_obj = _current_app._get_current_object()
                    with app_obj.app_context():
                        monitor_user_notifications(u)
                except Exception:
                    logging.getLogger(__name__).exception('Failed to run monitor_user_notifications for user %s', u.get('_id'))

            t = threading.Thread(target=_fire_user_monitor, args=(user,), daemon=True)
            t.start()
        except Exception:
            logging.getLogger(__name__).exception('Failed to spawn user alert monitor thread')

        return jsonify({
            "message": "Login successful",
            "user": _serialize_user(user),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }), 200

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500



@auth_bp.route('/check-username', methods=['GET'])
@limiter.limit("10 per minute")
def check_username():
    """Check username availability. Query param: ?username=foo"""
    try:
        username = (request.args.get('username') or '').strip()
        if not username:
            return jsonify({"error": "username is required"}), 400
        user = users_repo.find_by_username(username)
        return jsonify({"available": user is None}), 200
    except Exception as e:
        logger.error(f"Check username error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/check-email', methods=['GET'])
@limiter.limit("10 per minute")
def check_email():
    """Check email availability and (optionally) deliverability.

    Query param: ?email=foo@example.com
    Response: { available: bool, checked: bool, reason?: str }
    """
    try:
        email = (request.args.get('email') or '').strip()
        if not email:
            return jsonify({"error": "email is required"}), 400
        if not _validate_email(email):
            return jsonify({"error": "invalid_format", "message": "invalid email format"}), 400

        # Check existing account
        try:
            user = users_repo.find_by_email(email)
        except Exception:
            user = None
        if user:
            return jsonify({"available": False, "checked": True, "reason": "exists"}), 200

        # Deeper deliverability check via registration validator. Fail-open on errors.
        try:
            allowed, validation_result = validate_registration_email(email)
        except Exception as e:
            logger.debug(f"Email validation provider error on check-email: {e}")
            # If provider error, return checked=False (caller should treat as unknown)
            body = {"available": True, "checked": False}
            try:
                if current_app.config.get('DEBUG'):
                    body['debug'] = {'error': str(e)}
            except Exception:
                pass
            return jsonify(body), 200

        if not allowed:
            reason = getattr(validation_result, 'reason', None) if validation_result else None
            body = {"available": False, "checked": True, "reason": reason}
            try:
                if current_app.config.get('DEBUG') and validation_result:
                    # include full validation result for local debugging only
                    body['debug'] = {'email_validation': validation_result.__dict__}
            except Exception:
                pass
            return jsonify(body), 200

        return jsonify({"available": True, "checked": True}), 200
    except Exception as e:
        logger.error(f"Check email error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/check-email-debug', methods=['GET'])
@limiter.limit("5 per minute")
def check_email_debug():
    """Dev-only endpoint: return the raw email validation payload.

    Only available when the Flask app is running in DEBUG mode. Use this to
    inspect the full ValidationResult returned by the registration validator
    without changing cached values or global settings.
    Query param: ?email=foo@example.com
    """
    try:
        # Only allow in debug to avoid leaking provider/internal details in prod
        if not current_app.config.get('DEBUG'):
            return jsonify({"error": "not_found"}), 404

        email = (request.args.get('email') or '').strip()
        if not email:
            return jsonify({"error": "email is required"}), 400
        if not _validate_email(email):
            return jsonify({"error": "invalid_format", "message": "invalid email format"}), 400

        # Check existing account
        try:
            user = users_repo.find_by_email(email)
        except Exception:
            user = None
        if user:
            return jsonify({"available": False, "checked": True, "reason": "exists", "debug": {"note": "user exists"}}), 200

        try:
            allowed, validation_result = validate_registration_email(email)
        except Exception as e:
            body = {"available": True, "checked": False, "debug": {"error": str(e)}}
            return jsonify(body), 200

        body = {"available": bool(allowed), "checked": True}
        try:
            if validation_result is not None:
                # ValidationResult is an object with attributes; expose its dict for debug only
                body['debug'] = {'email_validation': validation_result.__dict__}
                reason = getattr(validation_result, 'reason', None)
                if reason:
                    body['reason'] = reason
        except Exception:
            # ignore debug serialization errors
            pass

        return jsonify(body), 200
    except Exception as e:
        logger.error(f"Check email debug error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Flask-Limiter will raise a 429; return JSON rather than HTML
@auth_bp.errorhandler(429)
def ratelimit_handler(e):
    # flask_limiter may attach description or headers
    try:
        retry_after = e.description if hasattr(e, 'description') else None
    except Exception:
        retry_after = None
    body = {"error": "rate_limited", "message": "Too many requests, please try again later."}
    if retry_after:
        body['retry_after'] = str(retry_after)
    resp = make_response(jsonify(body), 429)
    return resp



@auth_bp.route('/password-strength', methods=['POST'])
@limiter.limit("20 per minute")
def password_strength():
    """Return a password strength score and feedback for client-side meter.

    Request JSON: {"password": "...", "username": "...", "email": "..."}
    Response: {"score": 0-4, "feedback": {...}, "violations": [...]} or error.
    """
    try:
        data = request.get_json(silent=True) or {}
        password = data.get('password') or ''
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()

        if not password:
            return jsonify({"error": "password is required"}), 400

        # Basic complexity violations
        ok, violations = _validate_password(password)

        result = {
            "violations": violations,
        }

        # zxcvbn gives a score 0-4; return when available
        try:
            if zxcvbn:
                res = zxcvbn(password, user_inputs=[username, email])
                result['score'] = int(res.get('score', 0))
                result['feedback'] = res.get('feedback') or {}
            else:
                # Fallback simple metric: map length+complexity to score
                score = 0
                if len(password) >= 8:
                    score += 1
                if len(password) >= 12:
                    score += 1
                if re.search(r"[A-Z]", password):
                    score += 1
                if re.search(r"\d", password) and re.search(r"[^\w\s]", password):
                    score += 1
                # cap at 4
                result['score'] = min(score, 4)
                result['feedback'] = {"warning": "Install zxcvbn for richer feedback", "suggestions": []}
        except Exception as e:
            logger.debug(f"Password scoring failed: {e}")
            result['score'] = None
            result['feedback'] = {"warning": "scoring_failed"}

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Password strength error: {e}")
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
        # Prevent users from reusing their current password when resetting
        try:
            from backend.app.services.auth.reset_password import check_password_reuse
            if check_password_reuse(token, new_password):
                return jsonify({"error": "password_reuse", "message": "New password cannot be the same as the current password"}), 400
        except Exception:
            # If check fails for any reason, allow reset to continue (do not block)
            pass

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

        from backend.app.services.auth.reset_password import validate_reset_token

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
