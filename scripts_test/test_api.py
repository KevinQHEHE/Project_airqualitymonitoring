"""Simple API test to verify database integration."""

import sys
from pathlib import Path

# Add project root to path (go up one level from scripts_test)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app import create_app
from backend.app.config import config

def test_api():
    """Test the Flask API with database integration."""
    app = create_app(config['development'])
    
    with app.test_client() as client:
        # Test health endpoint
        response = client.get('/api/health')
        print(f"Health endpoint status: {response.status_code}")
        print(f"Response: {response.get_json()}")
        
        return response.status_code == 200

if __name__ == '__main__':
    success = test_api()
    print(f"\nAPI test {'PASSED' if success else 'FAILED'}")
    sys.exit(0 if success else 1)
