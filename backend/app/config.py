"""Configuration settings and environment variables."""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration class with default settings."""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    # JWT settings
    from datetime import timedelta
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    
    # MongoDB settings
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/'
    MONGO_DB = os.environ.get('MONGO_DB') or 'air_quality_monitoring'
    
    # External API settings
    GEOS_CF_DATASET_URL = os.environ.get('GEOS_CF_DATASET_URL') or 'https://gmao.gsfc.nasa.gov/geos_cf/'
    OPENAQ_API_URL = os.environ.get('OPENAQ_API_URL') or 'https://api.openaq.org/v2/'
    
    # Mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL') or 'memory://'
    
    # Cache settings
    CACHE_TYPE = os.environ.get('CACHE_TYPE') or 'simple'
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT') or 300)
    
    # Station reading scheduler settings
    STATION_POLLING_INTERVAL_MINUTES = int(os.environ.get('STATION_POLLING_INTERVAL_MINUTES') or 60)
    STATION_SCRIPT_TIMEOUT_SECONDS = int(os.environ.get('STATION_SCRIPT_TIMEOUT_SECONDS') or 300)
    ENABLE_STATION_SCHEDULER = os.environ.get('ENABLE_STATION_SCHEDULER', 'true').lower() in ['true', '1', 'on', 'yes']

    # Alerts monitor scheduler (in-process APScheduler)
    ALERT_MONITOR_ENABLED = os.environ.get('ALERT_MONITOR_ENABLED', 'true').lower() in ['true', '1', 'on', 'yes']
    ALERT_MONITOR_INTERVAL_MINUTES = int(os.environ.get('ALERT_MONITOR_INTERVAL_MINUTES') or 15)

    # Celery settings (optional) - keep defaults safe for local development
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND')
    # Beat schedule: run favorite station monitor every 15 minutes by default
    CELERY_BEAT_SCHEDULE = {
        'monitor-favorite-stations-every-15-minutes': {
            'task': 'backend.app.tasks.alerts.monitor_favorite_stations',
            'schedule': 15 * 60,
        }
    }

    # Registration behavior: whether to write a top-level `status` field
    # to new user documents. Some deployments prefer to omit this field and
    # treat missing status as 'active'. Set environment variable
    # REGISTER_SET_STATUS_ON_REGISTRATION=true to enable writing the field.
    REGISTER_SET_STATUS_ON_REGISTRATION = os.environ.get('REGISTER_SET_STATUS_ON_REGISTRATION', 'false').lower() in ['true', '1', 'on', 'yes']


class DevelopmentConfig(Config):
    """Development configuration with debug mode enabled."""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration with security settings."""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration with test database."""
    TESTING = True
    MONGO_DB = 'air_quality_monitoring_test'


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
