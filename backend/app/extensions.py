"""Flask extensions initialization (PyMongo, Mail, Limiter, Login, Cache)."""
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from . import db

# Initialize Flask extensions
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
login_manager = LoginManager()


def init_extensions(app):
    """Initialize Flask extensions with app context.
    
    Args:
        app: Flask application instance
    """
    # Initialize extensions
    mail.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    
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
    
    # Initialize and start the data ingestion scheduler
    try:
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
    except Exception as e:
        print(f"=== FLASK: Error initializing data ingestion scheduler: {e} ===")
        app.logger.error(f"Error initializing data ingestion scheduler: {e}")
