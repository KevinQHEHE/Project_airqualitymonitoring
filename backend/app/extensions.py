"""Flask extensions initialization (PyMongo, Mail, Limiter, Login, JWT, Cache).

Includes JWT blocklist checking for logout token revocation.
"""
import os
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from . import db
from flask_jwt_extended import JWTManager

# Initialize Flask extensions
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    headers_enabled=True,
)
login_manager = LoginManager()
jwt = JWTManager()


def init_extensions(app):
    """Initialize Flask extensions with app context.
    
    Args:
        app: Flask application instance
    """
    # Initialize extensions
    mail.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Add user_loader function (required by Flask-Login)
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login."""
        # TODO: Implement user loading from MongoDB
        # For now, return None (no user authentication)
        return None
    
    # Initialize MongoDB connection using db module
    db.init_app(app)

    # JWT: check if token is in blocklist (revoked)
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        try:
            database = db.get_db()
            jti = jwt_payload.get("jti")
            if not jti:
                return False
            doc = database.jwt_blocklist.find_one({"jti": jti})
            return doc is not None
        except Exception:
            # Fail-safe: if we cannot check, do not block
            return False

    # Optional: custom response for revoked tokens
    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        from flask import jsonify
        return jsonify({"error": "token has been revoked"}), 401
    
    # Initialize and start the data ingestion scheduler
    try:
        # Avoid double-starting background schedulers when the Flask
        # development reloader spawns a parent and child process. The
        # reloader parent should not start background threads — only the
        # served child process (WERKZEUG_RUN_MAIN == 'true') should.
        should_start_scheduler = True
        # If app.debug is True and we are running under the reloader, only
        # start in the child process where WERKZEUG_RUN_MAIN is 'true'.
        if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            should_start_scheduler = False

        if should_start_scheduler:
            print("=== FLASK: Initializing data ingestion scheduler ===")
            from ingest.streaming import DataIngestionScheduler
            scheduler = DataIngestionScheduler(app)
            success = scheduler.start()
            if success:
                print("=== FLASK: Data ingestion scheduler started successfully ===")
                app.logger.info("Data ingestion scheduler started successfully")
            else:
                print("=== FLASK: Failed to start data ingestion scheduler ===")
                app.logger.error("Failed to start data ingestion scheduler")
        else:
            app.logger.debug("Skipping data ingestion scheduler startup in reloader parent process")
    except Exception as e:
        print(f"=== FLASK: Error initializing data ingestion scheduler: {e} ===")
        app.logger.error(f"Error initializing data ingestion scheduler: {e}")

    # Initialize backup scheduler for MongoDB backups
    try:
        from backup_dtb.scheduler import init_backup_scheduler
        backup_scheduler = init_backup_scheduler(logger=app.logger)
        if backup_scheduler:
            app.extensions["backup_scheduler"] = backup_scheduler
            app.logger.info(
                "Backup scheduler started (interval=%.2fh, retention=%.4fd)",
                backup_scheduler.interval_seconds / 3600.0,
                backup_scheduler.retention_days,
            )
    except Exception as e:
        app.logger.error("Error initializing backup scheduler: %s", e)

