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
    # --- Auto-configure EMAIL_VALIDATION from environment (safe, no secrets committed) ---
    # If an Abstract API key is present in the environment, populate a minimal
    # EMAIL_VALIDATION dict so services can call the provider without requiring
    # additional manual config. Keys remain in environment; we don't write them
    # to disk or commit them.
    import os
    abstract_key = os.environ.get('ABSTRACT_API_KEY')
    if abstract_key and not app.config.get('EMAIL_VALIDATION'):
        app.config['EMAIL_VALIDATION'] = {
            'provider': 'abstract',
            'api_key': abstract_key,
            'url': os.environ.get('EMAIL_VALIDATION_URL') or 'https://emailvalidation.abstractapi.com/v1/'
        }
        # Quick validation of the provider key to avoid noisy runtime failures.
        # Make a lightweight call to the provider; if it returns 401 (invalid key)
        # disable EMAIL_VALIDATION so the app falls back to MX-only checks and fail-open behavior.
        try:
            import requests
            cfg = app.config['EMAIL_VALIDATION']
            test_url = cfg.get('url')
            api_key = cfg.get('api_key')
            if test_url and api_key:
                try:
                    resp = requests.get(test_url, params={'api_key': api_key, 'email': 'verify@example.com'}, timeout=3)
                    if resp.status_code == 401:
                        # Invalid API key — disable provider use and log clear message
                        app.logger.error('Email validation provider returned 401 (invalid API key). Disabling external provider checks. Please verify ABSTRACT_API_KEY in your environment.')
                        app.config.pop('EMAIL_VALIDATION', None)
                        # Ensure fail-open is enabled to avoid blocking registrations
                        app.config['EMAIL_VALIDATION_FAIL_OPEN'] = True
                except requests.RequestException as e:
                    # Network issues — leave provider configured but warn
                    app.logger.warning(f'Could not validate email provider at startup: {e} (will attempt at runtime)')
        except Exception:
            # If requests not available or other error, do not block startup
            pass
    
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
    from backend.app.blueprints.api.admin.routes import admin_bp
    # from backend.app.blueprints.api.measurements.routes import measurements_bp
    # from backend.app.blueprints.api.aggregates.routes import aggregates_bp
    # from backend.app.blueprints.api.alerts.routes import alerts_bp
    # from backend.app.blueprints.api.forecasts.routes import forecasts_bp
    # from backend.app.blueprints.api.exports.routes import exports_bp
    # from backend.app.blueprints.api.realtime.routes import realtime_bp
    from backend.app.blueprints.api.scheduler.routes import scheduler_bp
    from backend.app.blueprints.api.admin.users import admin_users_bp
    
    # Import Web blueprint
    from backend.app.blueprints.web.routes import web_bp
    
    # Register API blueprints with URL prefixes
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(stations_bp, url_prefix='/api/stations')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    # Register blueprint with underscore variant
    app.register_blueprint(air_quality_bp, url_prefix='/api/air_quality')
    # Register forecast blueprint
    app.register_blueprint(forecasts_bp, url_prefix='/api/forecast')
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
    # app.register_blueprint(measurements_bp, url_prefix='/api/measurements')
    # app.register_blueprint(aggregates_bp, url_prefix='/api/aggregates')
    # app.register_blueprint(alerts_bp, url_prefix='/api/alerts')
    # app.register_blueprint(forecasts_bp, url_prefix='/api/forecasts')
    # app.register_blueprint(exports_bp, url_prefix='/api/exports')
    # app.register_blueprint(realtime_bp, url_prefix='/api/realtime')
    app.register_blueprint(admin_users_bp, url_prefix='/api/admin/users')
    app.register_blueprint(scheduler_bp, url_prefix='/api/scheduler')
    
    # Register Web blueprint (no prefix for main web routes)
    app.register_blueprint(web_bp)
