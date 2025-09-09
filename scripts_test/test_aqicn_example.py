"""
Example usage of AQICN client for Vietnam air quality data.
Demonstrates all main functionality with Vietnamese stations.
"""

import sys
import os
import json

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

from ingest import AqicnClient


def main():
    """Example usage of AQICN client."""
    
    # Create client
    client = AqicnClient(api_key=os.environ.get('AQICN_API_KEY'))
    
    print("AQICN Client Usage Example")
    print("=" * 50)
    
    # 1. Get all Vietnamese stations
    print("1. Fetching Vietnamese air quality stations...")
    stations = client.list_stations("VN")
    print(f"   Found {len(stations)} Vietnamese stations")
    
    # Show major city stations
    major_cities = {
        "Hanoi": 1583,
        "Ho Chi Minh City": 8767, 
        "Da Nang": 1584,
        "Hai Phong": 13672,
        "Can Tho": 13687
    }
    
    print("\n2. Current air quality in major Vietnamese cities:")
    print("-" * 60)
    
    for city, station_id in major_cities.items():
        try:
            # Get current data
            data = client.fetch_hourly(station_id)
            aqi = data['current_aqi']
            
            # Handle string AQI values
            if isinstance(aqi, str):
                try:
                    aqi = int(aqi)
                except (ValueError, TypeError):
                    aqi = 0
            
            # Determine AQI level
            if aqi <= 50:
                level = "Good"
            elif aqi <= 100:
                level = "Moderate"
            elif aqi <= 150:
                level = "Unhealthy for Sensitive Groups"
            elif aqi <= 200:
                level = "Unhealthy"
            elif aqi <= 300:
                level = "Very Unhealthy"
            else:
                level = "Hazardous"
            
            print(f"   {city:20} | AQI: {aqi:3} | {level}")
            
            # Show top pollutants
            if data['current_iaqi']:
                pollutants = []
                for pol, val in data['current_iaqi'].items():
                    if pol.upper() in ['PM25', 'PM10', 'O3', 'NO2', 'SO2', 'CO']:
                        pollutants.append(f"{pol.upper()}:{val.get('v', 'N/A')}")
                if pollutants:
                    print(f"   {'':20} | {' | '.join(pollutants[:3])}")
            
        except Exception as e:
            print(f"   {city:20} | Error: {e}")
    
    # 3. Get forecast for Hanoi
    print("\n3. 7-day forecast for Hanoi:")
    print("-" * 40)
    
    try:
        forecast = client.fetch_forecast(1583)
        
        for day_data in forecast['daily_forecasts'][:7]:  # Show 7 days
            day = day_data['day']
            pollutants = day_data['pollutants']
            
            # Get PM2.5 forecast if available
            pm25_info = ""
            if 'pm25' in pollutants:
                pm25 = pollutants['pm25']
                pm25_info = f"PM2.5: {pm25.get('avg', 'N/A')} (range: {pm25.get('min', 'N/A')}-{pm25.get('max', 'N/A')})"
            
            print(f"   {day}: {pm25_info}")
            
    except Exception as e:
        print(f"   Error getting forecast: {e}")
    
    # 4. Export sample data to JSON
    print("\n4. Exporting sample data...")
    
    sample_data = {
        'export_time': '2025-09-09',
        'total_vn_stations': len(stations),
        'major_cities': [],
        'sample_stations': stations[:5]  # First 5 stations
    }
    
    # Add major cities data
    for city, station_id in list(major_cities.items())[:3]:  # First 3 cities
        try:
            data = client.fetch_hourly(station_id)
            sample_data['major_cities'].append({
                'city': city,
                'station_id': station_id,
                'station_name': data['station_name'],
                'aqi': data['current_aqi'],
                'coordinates': data['coordinates'],
                'timezone': data['timezone']
            })
        except:
            continue
    
    # Save to file
    with open('vietnam_air_quality_sample.json', 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, indent=2, ensure_ascii=False)
    
    print("   Sample data exported to: vietnam_air_quality_sample.json")
    print("\n✅ Example completed successfully!")


if __name__ == "__main__":
    main()
