"""
MongoDB Connection Test Utility

Quick test script to verify MongoDB connection using environment variables.
Usage: python scripts/test_connection.py
"""

import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv


def test_mongo_connection():
    """Test MongoDB connection and return status."""
    
    # Load environment variables
    load_dotenv()
    
    mongo_uri = os.environ.get('MONGO_URI')
    mongo_db = os.environ.get('MONGO_DB')
    
    # Validate environment variables
    if not mongo_uri or not mongo_db:
        print("ERROR: Missing required environment variables")
        print("Required: MONGO_URI, MONGO_DB")
        print("Check your .env file configuration")
        return False
    
    # Display connection info (hide sensitive parts)
    print(f"Database: {mongo_db}")
    if mongo_uri.startswith('mongodb+srv://'):
        # Hide credentials for Atlas connections
        uri_parts = mongo_uri.split('@')
        if len(uri_parts) > 1:
            print(f"URI: mongodb+srv://***@{uri_parts[1]}")
        else:
            print(f"URI: {mongo_uri[:30]}...")
    else:
        print(f"URI: {mongo_uri}")
    
    try:
        print("\nTesting connection...")
        
        # Create client with timeout
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        
        # Ping to test connection
        client.admin.command('ping')
        
        # Get database info
        db = client[mongo_db]
        collections = db.list_collection_names()
        
        # Success output
        print("SUCCESS: MongoDB connection established")
        print(f"Collections found: {len(collections)}")
        if collections:
            print(f"Collection names: {', '.join(collections)}")
        else:
            print("No collections in database yet")
        
        client.close()
        return True
        
    except Exception as error:
        print(f"FAILED: {str(error)}")
        print("Check your MongoDB credentials and network connection")
        return False


def main():
    """Main function."""
    print("MongoDB Connection Test")
    print("-" * 40)
    
    success = test_mongo_connection()
    
    print("-" * 40)
    if success:
        print("Status: READY")
        sys.exit(0)
    else:
        print("Status: NOT READY")
        sys.exit(1)


if __name__ == "__main__":
    main()
