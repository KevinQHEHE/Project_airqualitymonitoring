"""Test database connection and functionality.

This script tests the MongoDB connection using the db.py module
and verifies that the configuration is working properly.
"""

import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from backend.app.config import config
from backend.app import db


def test_db_connection():
    """Test database connection and basic operations."""
    print("Testing MongoDB connection...")
    
    # Create Flask app with development config
    app = Flask(__name__)
    app.config.from_object(config['development'])
    
    # Initialize database
    with app.app_context():
        try:
            # Initialize db module
            db.init_app(app)
            print("OK - Database module initialized successfully")
            
            # Test basic connection
            client = db.get_mongo_client()
            print("OK - MongoDB client created successfully")
            
            # Get database instance
            database = db.get_db()
            print(f"OK - Connected to database: {database.name}")
            
            # Test health check
            health = db.health_check()
            print(f"OK - Database health check: {health['status']}")
            if health['status'] == 'healthy':
                print(f"  - Server version: {health.get('server_version', 'unknown')}")
                print(f"  - Collections: {health.get('collections', 0)}")
            
            # Test collection stats
            stats = db.get_collection_stats()
            print(f"OK - Collection statistics retrieved: {len(stats)} collections")
            for name, count in stats.items():
                print(f"  - {name}: {count} documents")
            
            # Test index creation
            index_result = db.ensure_indexes()
            if index_result:
                print("OK - Database indexes created/verified successfully")
            else:
                print("WARNING - Some issues with index creation")
                
        except Exception as e:
            print(f"ERROR - Database connection failed: {e}")
            return False
    
    print("\nDatabase connection test completed successfully!")
    return True


if __name__ == '__main__':
    # Check if .env file exists
    env_file = Path(__file__).parent.parent / '.env'
    if not env_file.exists():
        print("WARNING - .env file not found. Using default configuration.")
        print(f"  Please copy .env.sample to .env and configure your MongoDB URI.")
        print(f"  Expected location: {env_file}")
    
    # Run the test
    success = test_db_connection()
    sys.exit(0 if success else 1)
