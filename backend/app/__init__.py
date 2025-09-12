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
    
    # Initialize Flask extensions
    init_extensions(app)
    
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
    import logging
    logging.getLogger(__name__).info("Background catchup disabled - using periodic streaming scheduler instead")
    
    # Initialize station reading scheduler
    try:
        from ingest.streaming import init_scheduler
        
        scheduler = init_scheduler(app)
        if scheduler:
            import logging
            logging.getLogger(__name__).info("Station reading scheduler started successfully")
        else:
            import logging
            logging.getLogger(__name__).warning("Station reading scheduler failed to start")
    except Exception as e:
        # Import errors should not prevent the app from starting; log and continue
        import logging
        logging.getLogger(__name__).warning(f"Station reading scheduler integration not available: {e}")
    
    return app


def register_blueprints(app):
    """Register Flask blueprints with the application.
    
    Args:
        app: Flask application instance
    """
    # Import API blueprints here to avoid circular imports
    # from backend.app.blueprints.api.auth.routes import auth_bp
    from backend.app.blueprints.api.stations.routes import stations_bp
    # from backend.app.blueprints.api.measurements.routes import measurements_bp
    # from backend.app.blueprints.api.aggregates.routes import aggregates_bp
    # from backend.app.blueprints.api.alerts.routes import alerts_bp
    # from backend.app.blueprints.api.forecasts.routes import forecasts_bp
    # from backend.app.blueprints.api.exports.routes import exports_bp
    # from backend.app.blueprints.api.realtime.routes import realtime_bp
    # from backend.app.blueprints.api.scheduler.routes import scheduler_bp
    
    # Import Web blueprint
    from backend.app.blueprints.web.routes import web_bp
    
    # Register API blueprints with URL prefixes
    # app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(stations_bp, url_prefix='/api/stations')
    # app.register_blueprint(measurements_bp, url_prefix='/api/measurements')
    # app.register_blueprint(aggregates_bp, url_prefix='/api/aggregates')
    # app.register_blueprint(alerts_bp, url_prefix='/api/alerts')
    # app.register_blueprint(forecasts_bp, url_prefix='/api/forecasts')
    # app.register_blueprint(exports_bp, url_prefix='/api/exports')
    # app.register_blueprint(realtime_bp, url_prefix='/api/realtime')
    # app.register_blueprint(scheduler_bp, url_prefix='/api/scheduler')
    
    # Register Web blueprint (no prefix for main web routes)
    app.register_blueprint(web_bp)
