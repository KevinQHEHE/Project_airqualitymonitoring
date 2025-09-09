# AQICN Client Documentation

## Overview

The `AqicnClient` is a Python client for the AQICN (Air Quality Index China) Data Platform API. It provides methods to fetch air quality stations, hourly readings, and daily forecasts with built-in rate limiting, error handling, and retry mechanisms.

## Features

- **Station Discovery**: Find all monitoring stations for a country (especially Vietnam)
- **Hourly Data**: Fetch current and time-series air quality measurements
- **Daily Forecasts**: Get multi-day air quality predictions by pollutant
- **Rate Limiting**: Automatic rate limiting to respect API quotas
- **Error Handling**: Comprehensive error handling with custom exceptions
- **Retry Logic**: Built-in retry mechanism for failed requests
- **Logging**: Detailed logging for debugging and monitoring

## Quick Start

### Environment Setup

Configure the following environment variables in your `.env` file:

```bash
AQICN_API_KEY=your_api_key_here
AQICN_API_URL=https://api.waqi.info
AQICN_RATE_LIMIT=1000
AQICN_TIMEOUT=30
```

### Basic Usage

```python
from ingest.aqicn_client import create_client_from_env, AqicnClient

# Create client from environment variables
client = create_client_from_env()

# Or create client manually
client = AqicnClient(
    api_key="your_api_key",
    rate_limit=1000,
    timeout=30
)
```

## API Methods

### 1. List Stations

Fetch all air quality monitoring stations for a country:

```python
# Get all Vietnamese stations
stations = client.list_stations(country="VN")

print(f"Found {len(stations)} stations")
for station in stations[:3]:  # Show first 3
    print(f"ID: {station['id']}, Name: {station['name']}")
    print(f"Coordinates: {station['coordinates']}")
```

**Response Format:**
```python
[
    {
        "id": 12975,
        "name": "Bắc Ninh/Binh Dinh, Vietnam",
        "coordinates": [21.0353984, 106.1025755],
        "country": "VN"
    },
    # ... more stations
]
```

### 2. Fetch Hourly Data

Get current air quality data and available time-series for a station:

```python
# Fetch data for Hanoi station (ID: 1583)
hourly_data = client.fetch_hourly(station_idx=1583)

print(f"Station: {hourly_data['station_name']}")
print(f"Current AQI: {hourly_data['current_aqi']}")
print(f"Coordinates: {hourly_data['coordinates']}")
print(f"Timezone: {hourly_data['timezone']}")

# Current pollutant levels
for pollutant, data in hourly_data['current_iaqi'].items():
    print(f"{pollutant.upper()}: {data.get('v', 'N/A')}")
```

**Response Format:**
```python
{
    "station_idx": 1583,
    "station_name": "Hanoi, Vietnam",
    "coordinates": [21.0491, 105.8831],
    "timezone": "+07:00",
    "current_time": "2024-12-07T15:00:00+07:00",
    "current_aqi": 71,
    "current_iaqi": {
        "pm25": {"v": 25},
        "pm10": {"v": 45},
        "o3": {"v": 12}
    },
    "time_series": [...]
}
```

### 3. Fetch Daily Forecast

Get multi-day air quality forecasts by pollutant:

```python
# Get forecast for Da Nang station (ID: 1584)
forecast = client.fetch_forecast(station_idx=1584)

print(f"Station: {forecast['station_name']}")
print(f"Forecast days: {len(forecast['daily_forecasts'])}")

for day_forecast in forecast['daily_forecasts']:
    print(f"\nDate: {day_forecast['day']}")
    for pollutant, values in day_forecast['pollutants'].items():
        print(f"  {pollutant}: avg={values['avg']}, min={values['min']}, max={values['max']}")
```

**Response Format:**
```python
{
    "station_idx": 1584,
    "station_name": "Da Nang, Vietnam",
    "coordinates": [16.074, 108.217],
    "fetched_at": "2024-12-07T15:00:00Z",
    "daily_forecasts": [
        {
            "day": "2024-12-08",
            "pollutants": {
                "pm25": {"avg": 15, "min": 8, "max": 25},
                "pm10": {"avg": 28, "min": 15, "max": 45},
                "o3": {"avg": 35, "min": 20, "max": 55}
            }
        }
    ]
}
```

### 4. Get Station Info

Get detailed metadata for a specific station:

```python
# Get station information
station_info = client.get_station_info(station_idx=1583)

print(f"Station ID: {station_info['idx']}")
print(f"Name: {station_info['name']}")
print(f"URL: {station_info['url']}")
print(f"Dominant Pollutant: {station_info['dominentpol']}")
print(f"Last Update: {station_info['last_update']}")
```

## Error Handling

The client provides specific exception types for different error conditions:

```python
from ingest.aqicn_client import (
    AqicnClientError,
    AqicnRateLimitError, 
    AqicnApiError
)

try:
    stations = client.list_stations("VN")
except AqicnRateLimitError as e:
    print(f"Rate limit exceeded: {e}")
    # Wait and retry
except AqicnApiError as e:
    print(f"API error: {e}")
    # Handle API-specific error
except AqicnClientError as e:
    print(f"Client error: {e}")
    # Handle general client error
```

## Rate Limiting

The client automatically manages rate limiting:

- Tracks request times over the last hour
- Waits when rate limit is approached
- Handles 429 (Too Many Requests) responses
- Configurable rate limit (default: 1000 requests/hour)

## Logging

Enable logging to monitor client behavior:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Use client - will show detailed logs
client = create_client_from_env()
stations = client.list_stations("VN")
```

## Configuration Options

### AqicnClient Parameters

- `api_key` (str): AQICN API key (required)
- `base_url` (str): API base URL (default: "https://api.waqi.info")
- `rate_limit` (int): Max requests per hour (default: 1000)
- `timeout` (int): Request timeout in seconds (default: 30)
- `max_retries` (int): Maximum retry attempts (default: 3)
- `backoff_factor` (float): Retry backoff factor (default: 1.0)

### Environment Variables

- `AQICN_API_KEY`: API key (required)
- `AQICN_API_URL`: Base URL (optional)
- `AQICN_RATE_LIMIT`: Rate limit (optional)
- `AQICN_TIMEOUT`: Timeout seconds (optional)

## Integration Example

Complete example for Vietnam stations:

```python
import logging
from ingest.aqicn_client import create_client_from_env

# Enable logging
logging.basicConfig(level=logging.INFO)

# Create client
client = create_client_from_env()

# Get all Vietnamese stations
print("Fetching Vietnamese stations...")
stations = client.list_stations("VN")
print(f"Found {len(stations)} stations")

# Get data for major cities
major_cities = {
    "Hanoi": 1583,
    "Ho Chi Minh City": 8767,
    "Da Nang": 1584
}

for city, station_id in major_cities.items():
    try:
        # Get current data
        hourly_data = client.fetch_hourly(station_id)
        forecast = client.fetch_forecast(station_id)
        
        print(f"\n{city}:")
        print(f"  Current AQI: {hourly_data['current_aqi']}")
        print(f"  Forecast days: {len(forecast['daily_forecasts'])}")
        
    except Exception as e:
        print(f"Error fetching data for {city}: {e}")
```

## Testing with Real API

The client has been tested with the real AQICN API. Key test scenarios:

1. **Vietnamese Stations**: Successfully retrieves 60+ stations
2. **Hourly Data**: Returns current AQI and pollutant levels  
3. **Daily Forecasts**: Provides multi-day predictions by pollutant
4. **Rate Limiting**: Handles 429 responses with automatic retry
5. **Error Handling**: Properly manages API errors and timeouts

## Best Practices

1. **Use Environment Variables**: Store API keys securely
2. **Enable Logging**: Monitor API usage and errors
3. **Handle Exceptions**: Implement proper error handling
4. **Cache Results**: Store station lists to reduce API calls
5. **Respect Rate Limits**: Don't exceed your API quota
6. **Validate Data**: Check for null/missing values in responses

## API Limitations

- Rate limited to 1000 requests per hour by default
- Historical data availability varies by station
- Some stations may have limited pollutant measurements
- Forecast accuracy depends on station data quality
- Geographic coverage is best in major urban areas
