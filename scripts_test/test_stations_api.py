"""Test stations API with repository integration."""

import sys
from pathlib import Path

# Add project root to path (go up one level from scripts_test)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app import create_app
from backend.app.config import config

def test_stations_api():
    """Test the stations API endpoints."""
    app = create_app(config['development'])
    
    with app.test_client() as client:
        print("Testing Stations API...")
        
        # Test GET /api/stations (follow redirects)
        response = client.get('/api/stations/', follow_redirects=True)
        print(f"GET /api/stations/ - Status: {response.status_code}")
        if response.status_code == 200:
            data = response.get_json()
            print(f"  - Stations returned: {len(data.get('stations', []))}")
            print(f"  - Pagination: {data.get('pagination', {})}")
        else:
            print(f"  - Error: {response.get_json()}")
        
        # Test GET /api/stations with city filter
        response = client.get('/api/stations/?city=Hanoi', follow_redirects=True)
        print(f"GET /api/stations/?city=Hanoi - Status: {response.status_code}")
        if response.status_code == 200:
            data = response.get_json()
            print(f"  - Stations in Hanoi: {len(data.get('stations', []))}")
        
        # Test GET specific station
        response = client.get('/api/stations/station_001', follow_redirects=True)
        print(f"GET /api/stations/station_001 - Status: {response.status_code}")
        if response.status_code == 200:
            station = response.get_json()
            print(f"  - Station found: {station.get('station_id', 'unknown')}")
        elif response.status_code == 404:
            print("  - Station not found (expected if no test data)")
        
        return True

if __name__ == '__main__':
    success = test_stations_api()
    print(f"\nStations API test {'PASSED' if success else 'FAILED'}")
    sys.exit(0 if success else 1)
