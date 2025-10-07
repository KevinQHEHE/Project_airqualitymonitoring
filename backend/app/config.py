"""Configuration settings and environment variables.

This module loads values from environment variables (including a .env file)
and provides small helpers to safely parse integers and booleans while
stripping inline comments. This avoids crashes when a .env value contains
an inline comment like:

    STATION_POLLING_INTERVAL_MINUTES=1440 # Default 24 hours

The helpers fall back to defaults and emit warnings when parsing fails.
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

_logger = logging.getLogger(__name__)


def _strip_inline_comment(val: str) -> str:
    """Strip an inline comment from a string and trim whitespace/quotes.

    Example: "1440 # Default 24 hours" -> "1440"
    """
    if val is None:
        return ''
    # Split on first '#' to remove inline comments
    val = val.split('#', 1)[0]
    val = val.strip()
    # Remove surrounding single/double quotes if present
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        val = val[1:-1]
    return val


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    stripped = _strip_inline_comment(raw)
    return stripped if stripped != '' else default


def _get_int_env(name: str, default: int) -> int:
    raw = _get_env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        _logger.warning("Invalid integer for %s: %r, falling back to %s", name, raw, default)
        return default


def _get_bool_env(name: str, default: bool) -> bool:
    raw = _get_env(name)
    if raw is None:
        return default
    return raw.lower() in ['true', '1', 'on', 'yes']


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
    MAIL_PORT = _get_int_env('MAIL_PORT', 587)
    MAIL_USE_TLS = _get_bool_env('MAIL_USE_TLS', True)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')

    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL') or 'memory://'

    # Cache settings
    CACHE_TYPE = os.environ.get('CACHE_TYPE') or 'simple'
    CACHE_DEFAULT_TIMEOUT = _get_int_env('CACHE_DEFAULT_TIMEOUT', 300)

    # Station reading scheduler settings
    STATION_POLLING_INTERVAL_MINUTES = _get_int_env('STATION_POLLING_INTERVAL_MINUTES', 60)
    STATION_SCRIPT_TIMEOUT_SECONDS = _get_int_env('STATION_SCRIPT_TIMEOUT_SECONDS', 300)
    ENABLE_STATION_SCHEDULER = _get_bool_env('ENABLE_STATION_SCHEDULER', True)

    # Alerts monitor scheduler (in-process APScheduler)
    ALERT_MONITOR_ENABLED = _get_bool_env('ALERT_MONITOR_ENABLED', True)
    ALERT_MONITOR_INTERVAL_MINUTES = _get_int_env('ALERT_MONITOR_INTERVAL_MINUTES', 15)

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
