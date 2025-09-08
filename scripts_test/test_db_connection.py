#!/usr/bin/env python3
"""
MongoDB Connection Test Script

Tests database connectivity with proper error handling and diagnostics.
Validates user permissions and basic operations.

Usage:
    python scripts/test_db_connection.py
    python scripts/test_db_connection.py --user aqm_readonly
    python scripts/test_db_connection.py --verbose
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timezone
from typing import Optional

# Add backend path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    from pymongo import MongoClient
    from pymongo.errors import (
        ConnectionFailure, 
        OperationFailure, 
        ServerSelectionTimeoutError,
        ConfigurationError
    )
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing required packages: {e}")
    print("Install with: pip install -r requirements.txt")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseConnectionTester:
    """Comprehensive MongoDB connection testing utility."""
    
    def __init__(self, mongo_uri: str, database_name: str, verbose: bool = False):
        """Initialize connection tester.
        
        Args:
            mongo_uri: MongoDB connection string
            database_name: Target database name
            verbose: Enable detailed logging
        """
        self.mongo_uri = mongo_uri
        self.database_name = database_name
        self.verbose = verbose
        self.client: Optional[MongoClient] = None
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
    
    def test_connection(self) -> bool:
        """Test basic MongoDB connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            print("Testing MongoDB connection...")
            
            # Create client with reasonable timeouts
            self.client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000
            )
            
            # Trigger connection
            server_info = self.client.server_info()
            
            print("Connected to MongoDB successfully!")
            if self.verbose:
                print(f"   Server version: {server_info.get('version', 'Unknown')}")
                print(f"   Connection URI: {self._mask_uri(self.mongo_uri)}")
            
            return True
            
        except ServerSelectionTimeoutError:
            print("Connection timeout - check network access and URI")
            return False
        except ConfigurationError as e:
            print(f"Configuration error: {e}")
            return False
        except ConnectionFailure as e:
            print(f"Connection failed: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False
    
    def test_authentication(self) -> bool:
        """Test database authentication and access.
        
        Returns:
            True if authentication successful, False otherwise
        """
        if not self.client:
            return False
            
        try:
            print("Testing database authentication...")
            
            db = self.client[self.database_name]
            
            # Test authentication by listing collections
            collections = db.list_collection_names()
            
            print("Authentication successful!")
            if self.verbose:
                print(f"   Database: {self.database_name}")
                print(f"   Collections found: {len(collections)}")
                if collections:
                    print(f"   Collection names: {', '.join(collections[:5])}")
            
            return True
            
        except OperationFailure as e:
            if "not authorized" in str(e).lower():
                print("Authentication failed - check username/password")
            else:
                print(f"Database operation failed: {e}")
            return False
        except Exception as e:
            print(f"Authentication test failed: {e}")
            return False
    
    def test_permissions(self) -> bool:
        """Test user permissions for basic operations.
        
        Returns:
            True if permissions adequate, False otherwise
        """
        if not self.client:
            return False
            
        try:
            print("Testing user permissions...")
            
            db = self.client[self.database_name]
            test_collection = db['connection_test']
            
            # Test write permission
            test_doc = {
                'test_timestamp': datetime.now(timezone.utc),
                'test_type': 'connection_test',
                'test_id': 'temp_test_document'
            }
            
            try:
                # Try insert
                result = test_collection.insert_one(test_doc)
                write_permission = True
                
                # Try read
                found_doc = test_collection.find_one({'_id': result.inserted_id})
                read_permission = found_doc is not None
                
                # Cleanup test document
                test_collection.delete_one({'_id': result.inserted_id})
                
            except OperationFailure:
                # Try read-only operation
                write_permission = False
                list(test_collection.find().limit(1))
                read_permission = True
            
            print("Permissions verified!")
            if self.verbose:
                print(f"   Read permission: {'YES' if read_permission else 'NO'}")
                print(f"   Write permission: {'YES' if write_permission else 'NO'}")
            
            return read_permission
            
        except OperationFailure as e:
            print(f"Permission test failed: {e}")
            return False
        except Exception as e:
            print(f"Permission test error: {e}")
            return False
    
    def test_collections_access(self) -> bool:
        """Test access to application collections.
        
        Returns:
            True if collections accessible, False otherwise
        """
        if not self.client:
            return False
            
        try:
            print("Testing collection access...")
            
            db = self.client[self.database_name]
            
            # Get actual existing collections
            actual_collections = set(db.list_collection_names())
            
            expected_collections = [
                'waqi_stations',
                'waqi_station_readings', 
                'waqi_daily_forecasts',
                'users'
            ]
            
            accessible_collections = []
            for collection_name in expected_collections:
                if collection_name in actual_collections:
                    try:
                        collection = db[collection_name]
                        # Try to get collection stats (requires read permission)
                        collection.estimated_document_count()
                        accessible_collections.append(collection_name)
                    except OperationFailure:
                        if self.verbose:
                            print(f"   WARNING: No access to existing collection {collection_name}")
                else:
                    if self.verbose:
                        print(f"   WARNING: Collection {collection_name} does not exist")
            
            # Check if we have the minimum required collections
            if len(accessible_collections) == len(expected_collections):
                print("Collection access verified!")
                if self.verbose:
                    print(f"   All expected collections accessible: {len(accessible_collections)}/{len(expected_collections)}")
                    for col in accessible_collections:
                        print(f"   - {col}")
            else:
                print("Collection access incomplete!")
                if self.verbose:
                    print(f"   Accessible collections: {len(accessible_collections)}/{len(expected_collections)}")
                    if accessible_collections:
                        print("   Found collections:")
                        for col in accessible_collections:
                            print(f"     - {col}")
                    
                    missing_collections = set(expected_collections) - set(accessible_collections)
                    if missing_collections:
                        print("   Missing collections:")
                        for col in sorted(missing_collections):
                            print(f"     - {col}")
                        print("   To create missing collections, run: python scripts/init_collections.py")
            
            # Return True only if we have all expected collections
            return len(accessible_collections) == len(expected_collections)
            
        except Exception as e:
            print(f"Collection access test failed: {e}")
            return False
    
    def run_full_test(self) -> bool:
        """Run comprehensive connection test suite.
        
        Returns:
            True if all tests pass, False otherwise
        """
        print("MongoDB Connection Test Suite")
        print("=" * 40)
        
        tests = [
            ("Connection", self.test_connection),
            ("Authentication", self.test_authentication), 
            ("Permissions", self.test_permissions),
            ("Collections", self.test_collections_access)
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append(result)
                if not result:
                    print(f"WARNING: {test_name} test failed")
            except Exception as e:
                print(f"ERROR: {test_name} test error: {e}")
                results.append(False)
            print()
        
        # Summary
        passed = sum(results)
        total = len(results)
        
        print("Test Summary")
        print("-" * 20)
        print(f"Tests passed: {passed}/{total}")
        
        if passed == total:
            print("All tests passed! Database connection is ready.")
            return True
        else:
            print("Some tests failed. Check configuration and permissions.")
            return False
    
    def close(self):
        """Close database connection."""
        if self.client:
            self.client.close()
    
    def _mask_uri(self, uri: str) -> str:
        """Mask password in URI for safe logging.
        
        Args:
            uri: MongoDB connection URI
            
        Returns:
            URI with masked password
        """
        try:
            if '://' in uri and '@' in uri:
                scheme, rest = uri.split('://', 1)
                if '@' in rest:
                    auth, host = rest.split('@', 1)
                    if ':' in auth:
                        user, _ = auth.split(':', 1)
                        return f"{scheme}://{user}:***@{host}"
            return uri
        except Exception:
            return "***masked***"


def main():
    """Main function to run connection tests."""
    parser = argparse.ArgumentParser(description='Test MongoDB connection and permissions')
    parser.add_argument('--user', help='Test with specific user credentials')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--uri', help='Override MongoDB URI from environment')
    parser.add_argument('--database', help='Override database name from environment')
    
    args = parser.parse_args()
    
    # Get configuration
    mongo_uri = args.uri or os.environ.get('MONGO_URI')
    database_name = args.database or os.environ.get('MONGO_DB', 'air_quality_db')
    
    if not mongo_uri:
        print("MongoDB URI not found!")
        print("Set MONGO_URI environment variable or use --uri parameter")
        print("Example: MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/")
        sys.exit(1)
    
    # Override user in URI if specified
    if args.user:
        # This is a simplified example - in practice, you'd need the user's password
        print(f"WARNING: Testing with user '{args.user}' requires manual URI configuration")
    
    # Run tests
    tester = DatabaseConnectionTester(mongo_uri, database_name, args.verbose)
    
    try:
        success = tester.run_full_test()
        sys.exit(0 if success else 1)
    finally:
        tester.close()


if __name__ == '__main__':
    main()
