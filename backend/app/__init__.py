"""Flask application factory and initialization."""
from flask import Flask, jsonify
from backend.app.config import Config
from backend.app.extensions import init_extensions
from backend.app import db


def create_app(config_class=Config):
    """Create and configure the Flask application.
    
    Args:
        config_class: Configuration class to use
        
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Email validation must be configured explicitly via `app.config['EMAIL_VALIDATION']`.
    # We intentionally do not auto-populate or validate provider keys from environment
    # variables at startup to avoid outbound network calls and noisy logs.
    
    # Initialize Flask extensions
    init_extensions(app)
    
    # Ensure required database indexes (including unique email/username)
    try:
        # Ensure indexes requires app context for current_app access
        with app.app_context():
            db.ensure_indexes()
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Could not ensure DB indexes at startup')
    
    # Register health check endpoint 
    @app.route('/api/health')
    def health_check():
        """Health check endpoint with database connectivity."""
        # Basic app health
        response = {
            "status": "ok",
            "service": "air-quality-monitoring-api"
        }
        
        # Database health check
        try:
            db_health = db.health_check()
            response["database"] = db_health
        except Exception as e:
            response["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            response["status"] = "degraded"
        
        return jsonify(response)
    
    # Register blueprints
    register_blueprints(app)
    
    # Add CORS headers for development
    @app.after_request
    def after_request(response):
        """Add CORS headers to all responses for development."""
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    # Note: Background catchup disabled in favor of periodic streaming scheduler
    # The streaming scheduler uses get_station_reading.py for real-time data with deduplication
    # and get_forecast_data.py for daily forecast ingestion
    import logging
    logging.getLogger(__name__).info("Background catchup disabled - using periodic streaming and forecast schedulers instead")
    
    # Data ingestion scheduler is initialized in extensions.py to avoid duplicate initialization
    
    return app


def register_blueprints(app):
    """Register Flask blueprints with the application.
    
    Args:
        app: Flask application instance
    """
    # Import API blueprints here to avoid circular imports
    from backend.app.blueprints.api.auth.routes import auth_bp
    from backend.app.blueprints.api.stations.routes import stations_bp
    from backend.app.blueprints.api.air_quality.routes import air_quality_bp
    from backend.app.blueprints.api.forecasts.routes import forecasts_bp
    from backend.app.blueprints.api.alerts.routes import alerts_bp
    from backend.app.blueprints.api.subscriptions.routes import subscriptions_bp
    from backend.app.blueprints.api.admin.routes import admin_users_bp
    # from backend.app.blueprints.api.measurements.routes import measurements_bp
    # from backend.app.blueprints.api.aggregates.routes import aggregates_bp
    # from backend.app.blueprints.api.exports.routes import exports_bp
    # from backend.app.blueprints.api.realtime.routes import realtime_bp
    from backend.app.blueprints.api.scheduler.routes import scheduler_bp
    
    # Import Web blueprint
    from backend.app.blueprints.web.routes import web_bp
    
    # Register API blueprints with URL prefixes
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(stations_bp, url_prefix='/api/stations')
    # Register blueprint with underscore variant
    app.register_blueprint(air_quality_bp, url_prefix='/api/air_quality')
    # Register forecast blueprint
    app.register_blueprint(forecasts_bp, url_prefix='/api/forecast')
    # Register alerts blueprint
    app.register_blueprint(alerts_bp, url_prefix='/api/alerts')
    # Register subscriptions blueprint
    app.register_blueprint(subscriptions_bp)
    # Register admin users blueprint (admin-only endpoints)
    app.register_blueprint(admin_users_bp, url_prefix='/api/admin/users')
    app.register_blueprint(scheduler_bp, url_prefix='/api/scheduler')
    
    # Provide a hyphenated alias for a small set of routes (avoid registering blueprint twice)
    try:
        # Import view function and create a lightweight alias route to avoid blueprint name collision
        from backend.app.blueprints.api.air_quality.routes import get_latest_measurements

        # Add URL rule for hyphen variant to point to the same view function
        app.add_url_rule('/api/air-quality/latest', endpoint='air_quality_latest_hyphen', view_func=get_latest_measurements, methods=['GET'])
    except Exception:
        # If import fails, do not prevent app startup; hyphen alias is optional
        import logging
        logging.getLogger(__name__).debug('Could not add hyphen alias for air_quality routes')
    # Also add a short alias for /api/aq/history per API contract
    try:
        from backend.app.blueprints.api.air_quality.routes import get_history
        app.add_url_rule('/api/aq/history', endpoint='aq_history', view_func=get_history, methods=['GET'])
    except Exception:
        import logging
        logging.getLogger(__name__).debug('Could not add alias /api/aq/history for air quality history route')
    
    # Register Web blueprint (no prefix for main web routes)
    app.register_blueprint(web_bp)
