"""
Test script for AQICN client functionality.
Tests all main methods against the real AQICN API.
"""

import logging
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

from ingest.aqicn_client import create_client_from_env, AqicnClientError


def test_aqicn_client():
    """Test AQICN client functionality."""
    # Enable logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    try:
        # Create client from environment
        logger.info("Creating AQICN client from environment variables")
        client = create_client_from_env()
        
        # Test 1: List Vietnamese stations
        logger.info("Test 1: Fetching Vietnamese stations")
        stations = client.list_stations("VN")
        logger.info(f"✅ Found {len(stations)} Vietnamese stations")
        
        if stations:
            # Show first few stations
            logger.info("Sample stations:")
            for station in stations[:3]:
                logger.info(f"  ID: {station['id']}, Name: {station['name']}")
        
        # Test 2: Fetch hourly data for a sample station
        if stations:
            sample_station_id = stations[0]['id']
            logger.info(f"Test 2: Fetching hourly data for station {sample_station_id}")
            
            hourly_data = client.fetch_hourly(sample_station_id)
            logger.info(f"✅ Retrieved hourly data for {hourly_data['station_name']}")
            logger.info(f"  Current AQI: {hourly_data['current_aqi']}")
            logger.info(f"  Coordinates: {hourly_data['coordinates']}")
            logger.info(f"  Timezone: {hourly_data['timezone']}")
            
            # Show current pollutants
            if hourly_data['current_iaqi']:
                logger.info("  Current pollutants:")
                for pollutant, data in hourly_data['current_iaqi'].items():
                    logger.info(f"    {pollutant.upper()}: {data.get('v', 'N/A')}")
        
        # Test 3: Fetch daily forecast
        if stations:
            logger.info(f"Test 3: Fetching forecast for station {sample_station_id}")
            
            forecast = client.fetch_forecast(sample_station_id)
            logger.info(f"✅ Retrieved forecast for {forecast['station_name']}")
            logger.info(f"  Forecast days: {len(forecast['daily_forecasts'])}")
            
            # Show forecast summary
            if forecast['daily_forecasts']:
                first_day = forecast['daily_forecasts'][0]
                logger.info(f"  First forecast day: {first_day['day']}")
                logger.info(f"  Pollutants: {list(first_day['pollutants'].keys())}")
        
        # Test 4: Get station info
        if stations:
            logger.info(f"Test 4: Getting station info for {sample_station_id}")
            
            station_info = client.get_station_info(sample_station_id)
            logger.info(f"✅ Retrieved station info")
            logger.info(f"  Name: {station_info['name']}")
            logger.info(f"  URL: {station_info['url']}")
            logger.info(f"  Dominant pollutant: {station_info['dominentpol']}")
            logger.info(f"  Last update: {station_info['last_update']}")
        
        logger.info("\n🎉 All tests passed successfully!")
        return True
        
    except AqicnClientError as e:
        logger.error(f"❌ AQICN client error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False


def test_error_handling():
    """Test error handling scenarios."""
    logger = logging.getLogger(__name__)
    
    try:
        client = create_client_from_env()
        
        # Test with invalid station ID
        logger.info("Test: Error handling with invalid station ID")
        try:
            client.fetch_hourly(999999)  # Invalid station ID
            logger.warning("Expected error but got success")
        except AqicnClientError as e:
            logger.info(f"✅ Properly handled error: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error in error handling test: {e}")
        return False


if __name__ == "__main__":
    print("AQICN Client Test Suite")
    print("=" * 50)
    
    # Run main functionality tests
    success1 = test_aqicn_client()
    
    # Run error handling tests
    print("\nError Handling Tests")
    print("-" * 30)
    success2 = test_error_handling()
    
    # Summary
    print("\nTest Summary")
    print("-" * 20)
    if success1 and success2:
        print("✅ All tests completed successfully")
        print("✅ AQICN client is working correctly")
    else:
        print("❌ Some tests failed")
        print("❌ Check the logs above for details")
