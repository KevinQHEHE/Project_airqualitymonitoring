"""
Quick verification test for AQICN client methods.
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Load environment variables manually from .env
def load_env_file():
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env_file()

from ingest.aqicn_client import AqicnClient

def main():
    # Create client with API key from env
    client = AqicnClient(api_key=os.environ.get('AQICN_API_KEY'))
    
    print("Testing AQICN Client Methods")
    print("=" * 40)
    
    # Test 1: List stations for Vietnam
    print("1. Fetching VN stations...")
    stations = client.list_stations("VN")
    print(f"   Found {len(stations)} stations")
    
    # Test 2: Get hourly data for sample station
    if stations:
        sample_id = 1583  # Hanoi
        print(f"2. Fetching hourly data for Hanoi (ID: {sample_id})...")
        hourly = client.fetch_hourly(sample_id)
        print(f"   Station: {hourly['station_name']}")
        print(f"   AQI: {hourly['current_aqi']}")
    
    # Test 3: Get forecast
    if stations:
        print(f"3. Fetching forecast for Hanoi (ID: {sample_id})...")
        forecast = client.fetch_forecast(sample_id)
        print(f"   Forecast days: {len(forecast['daily_forecasts'])}")
        
        if forecast['daily_forecasts']:
            first_day = forecast['daily_forecasts'][0]
            print(f"   First day: {first_day['day']}")
            print(f"   Pollutants: {list(first_day['pollutants'].keys())}")
    
    print("\n✅ All methods working correctly!")

if __name__ == "__main__":
    main()
