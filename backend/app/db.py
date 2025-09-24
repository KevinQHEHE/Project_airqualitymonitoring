"""Database connection and utility functions for MongoDB.

This module provides a centralized MongoDB client with connection management,
error handling, and common database operations for the Air Quality Monitoring system.
"""

from __future__ import annotations

import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from flask import current_app, g

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

def get_mongo_client() -> MongoClient:
    """Get or create MongoDB client instance.
    
    Returns:
        MongoClient: Configured MongoDB client instance
        
    Raises:
        DatabaseError: If connection cannot be established
    """
    if 'mongo_client' not in g:
        try:
            mongo_uri = current_app.config['MONGO_URI']
            g.mongo_client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=10000,         # 10 second connection timeout
                socketTimeoutMS=20000,          # 20 second socket timeout
                maxPoolSize=50,                 # Maximum connection pool size
                retryWrites=True
            )
            
            # Test the connection
            g.mongo_client.admin.command('ping')
            logger.info("MongoDB connection established successfully")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise DatabaseError(f"Database connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            raise DatabaseError(f"Unexpected database error: {e}")
    
    return g.mongo_client


def get_db():
    """Get database instance for the current application.
    
    Returns:
        Database: MongoDB database instance
        
    Raises:
        DatabaseError: If database connection fails
    """
    client = get_mongo_client()
    db_name = current_app.config['MONGO_DB']
    return client[db_name]


def close_db(error: Optional[Exception] = None) -> None:
    """Close database connection if it exists.
    
    Args:
        error: Optional exception that caused the close (for logging)
    """
    mongo_client = g.pop('mongo_client', None)
    
    if mongo_client is not None:
        try:
            mongo_client.close()
            if error:
                logger.warning(f"Database connection closed due to error: {error}")
            else:
                logger.debug("Database connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")


def init_app(app) -> None:
    """Initialize database connection with Flask app.
    
    Args:
        app: Flask application instance
    """
    # Register teardown handler to close connections
    app.teardown_appcontext(close_db)
    
    # Test initial connection during app startup
    with app.app_context():
        try:
            client = get_mongo_client()
            db = get_db()
            
            # Verify we can list collections (basic connectivity test)
            collections = db.list_collection_names()
            logger.info(f"Database initialization successful. Found {len(collections)} collections.")
            
        except DatabaseError as e:
            logger.error(f"Database initialization failed: {e}")
            # Don't raise here - allow app to start even if DB is temporarily unavailable
        except Exception as e:
            logger.error(f"Unexpected error during database initialization: {e}")


def health_check() -> dict:
    """Perform database health check.
    
    Returns:
        dict: Health check results with status and details
    """
    try:
        client = get_mongo_client()
        db = get_db()
        
        # Ping the database
        client.admin.command('ping')
        
        # Get server info
        server_info = client.server_info()
        
        # Count collections
        collection_count = len(db.list_collection_names())
        
        return {
            'status': 'healthy',
            'database': current_app.config['MONGO_DB'],
            'server_version': server_info.get('version', 'unknown'),
            'collections': collection_count,
            'message': 'Database connection is operational'
        }
        
    except DatabaseError as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'message': 'Database connection failed'
        }
    except Exception as e:
        logger.error(f"Health check failed with unexpected error: {e}")
        return {
            'status': 'unhealthy',
            'error': f"Unexpected error: {str(e)}",
            'message': 'Database health check failed'
        }


# Common database operations utilities

def ensure_indexes() -> bool:
    """Ensure all required indexes are created.
    
    Returns:
        bool: True if all indexes were created/verified successfully
    """
    try:
        db = get_db()

        # Station readings indexes
        readings_collection = db.waqi_station_readings
        readings_collection.create_index([('station_id', 1), ('ts', -1)])
        readings_collection.create_index([('ts', -1)])
        readings_collection.create_index([('location', '2dsphere')])

        # Stations indexes
        stations_collection = db.waqi_stations
        # station_id should be unique when present; skip documents where station_id is null
        try:
            stations_collection.create_index([('station_id', 1)], unique=True, partialFilterExpression={"station_id": {"$exists": True, "$ne": None}})
        except Exception:
            # Fallback for Mongo versions that don't support partialFilterExpression
            try:
                stations_collection.create_index([('station_id', 1)], unique=True)
            except Exception:
                # Ignore to avoid startup failure (index may already exist or conflict)
                pass
        stations_collection.create_index([('location', '2dsphere')])
        stations_collection.create_index([('city', 1)])
        
        # Forecasts indexes
        forecasts_collection = db.waqi_daily_forecasts
        forecasts_collection.create_index([('station_id', 1), ('forecast_date', -1)])
        forecasts_collection.create_index([('forecast_date', -1)])
        
        # Users indexes
        users_collection = db.users
        users_collection.create_index([('email', 1)], unique=True)
        users_collection.create_index([('username', 1)], unique=True)

        # Password reset tokens indexes (TTL on expiresAt)
        resets_collection = db.password_resets
        # Token hash lookup
        resets_collection.create_index([('tokenHash', 1)])
        # TTL index: documents expire at expiresAt
        try:
            resets_collection.create_index('expiresAt', expireAfterSeconds=0)
        except Exception:
            # If TTL index options conflict, ignore silently to avoid startup failure
            pass

        # Email validation cache TTL index (expiresAt) to support caching for 24 hours
        try:
            email_cache = db.email_validation_cache
            email_cache.create_index('email', unique=True)
            email_cache.create_index('expiresAt', expireAfterSeconds=0)
        except Exception:
            # Ignore index errors to avoid blocking startup
            pass
        # API response cache TTL index (used by nearest endpoint cache)
        try:
            api_cache = db.api_response_cache
            api_cache.create_index('expiresAt', expireAfterSeconds=0)
        except Exception:
            pass
        
        # Alert subscriptions indexes: efficient lookups by user, station, status and threshold
        try:
            subs = db.alert_subscriptions
            subs.create_index([('user_id', 1)])
            subs.create_index([('station_id', 1)])
            subs.create_index([('station_id', 1), ('alert_threshold', 1), ('status', 1)])
            subs.create_index([('user_id', 1), ('status', 1)])
        except Exception:
            logger.debug('Could not create indexes for alert_subscriptions')

        # Notification logs: indexing for auditing and TTL retention
        try:
            logs = db.notification_logs
            logs.create_index([('subscription_id', 1)])
            logs.create_index([('user_id', 1)])
            logs.create_index([('station_id', 1)])
            logs.create_index([('sentAt', 1)])
            # ttl: keep logs for 90 days
            try:
                logs.create_index('sentAt', expireAfterSeconds=90 * 24 * 60 * 60)
            except Exception:
                # ignore conflicts with existing TTL settings
                pass
        except Exception:
            logger.debug('Could not create indexes for notification_logs')
        
        logger.info("Database indexes created/verified successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")
        return False


def get_collection_stats() -> dict:
    """Get statistics for all collections in the database.
    
    Returns:
        dict: Collection names and document counts
    """
    try:
        db = get_db()
        stats = {}
        
        for collection_name in db.list_collection_names():
            collection = db[collection_name]
            stats[collection_name] = collection.estimated_document_count()
            
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        return {}
