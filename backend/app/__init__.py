"""Flask application factory and initialization."""
from flask import Flask, jsonify
from app.config import Config
from app.extensions import init_extensions


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
        """Health check endpoint."""
        return jsonify({"status": "ok"})
    
    # Register blueprints
    register_blueprints(app)
    
    return app


def register_blueprints(app):
    """Register Flask blueprints with the application.
    
    Args:
        app: Flask application instance
    """
    # Import blueprints here to avoid circular imports
    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.stations.routes import stations_bp
    from app.blueprints.measurements.routes import measurements_bp
    from app.blueprints.aggregates.routes import aggregates_bp
    from app.blueprints.alerts.routes import alerts_bp
    from app.blueprints.forecasts.routes import forecasts_bp
    from app.blueprints.exports.routes import exports_bp
    from app.blueprints.dashboard.routes import dashboard_bp
    
    # Register blueprints with URL prefixes
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(stations_bp, url_prefix='/api/stations')
    app.register_blueprint(measurements_bp, url_prefix='/api/measurements')
    app.register_blueprint(aggregates_bp, url_prefix='/api/aggregates')
    app.register_blueprint(alerts_bp, url_prefix='/api/alerts')
    app.register_blueprint(forecasts_bp, url_prefix='/api/forecasts')
    app.register_blueprint(exports_bp, url_prefix='/api/exports')
    app.register_blueprint(dashboard_bp, url_prefix='/')
