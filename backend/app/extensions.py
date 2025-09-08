"""Flask extensions initialization (PyMongo, Mail, Limiter, Login, Cache)."""
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from pymongo import MongoClient

# Initialize Flask extensions
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
login_manager = LoginManager()

# MongoDB client (will be initialized in init_extensions)
mongo_client = None
db = None


def init_extensions(app):
    """Initialize Flask extensions with app context.
    
    Args:
        app: Flask application instance
    """
    global mongo_client, db
    
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
    
    # Initialize MongoDB connection
    mongo_client = MongoClient(app.config['MONGO_URI'])
    db = mongo_client[app.config['MONGO_DB']]
    
    # Store database reference in app context
    app.db = db
