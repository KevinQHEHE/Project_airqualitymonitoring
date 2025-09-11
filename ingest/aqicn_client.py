"""
AQICN Data Platform API client for fetching air quality data.
Handles stations list, hourly readings, and daily forecasts with proper error handling and rate limiting.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AqicnClientError(Exception):
    """Base exception for AQICN client errors."""
    pass


class AqicnRateLimitError(AqicnClientError):
    """Exception raised when API rate limit is exceeded."""
    pass


class AqicnApiError(AqicnClientError):
    """Exception raised when API returns an error response."""
    pass


class AqicnClient:
    """
    Client for AQICN Data Platform API.
    
    Provides methods to fetch stations, hourly readings, and forecasts
    with built-in rate limiting, retries, and error handling.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.waqi.info",
        rate_limit: int = 1000,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.0
    ):
        """
        Initialize AQICN client.
        
        Args:
            api_key: AQICN API key
            base_url: Base URL for AQICN API
            rate_limit: Max requests per hour
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            backoff_factor: Backoff factor for retries
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.rate_limit = rate_limit
        self.timeout = timeout
        
        # Request tracking for rate limiting
        self._request_times: List[float] = []
        self._min_interval = 3600.0 / rate_limit if rate_limit > 0 else 0
        
        # Setup session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],  # Updated parameter name
            backoff_factor=backoff_factor
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def _wait_for_rate_limit(self) -> None:
        """Implement rate limiting by waiting if necessary."""
        if not self._min_interval:
            return
            
        current_time = time.time()
        
        # Remove old requests (older than 1 hour)
        cutoff_time = current_time - 3600
        self._request_times = [t for t in self._request_times if t > cutoff_time]
        
        # Check if we need to wait
        if len(self._request_times) >= self.rate_limit:
            sleep_time = self._request_times[0] + 3600 - current_time
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached. Waiting {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
        
        # Add current request time
        self._request_times.append(current_time)
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make HTTP request to AQICN API with error handling.
        
        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters
            
        Returns:
            API response as dictionary
            
        Raises:
            AqicnRateLimitError: When rate limit is exceeded
            AqicnApiError: When API returns error
            AqicnClientError: For other client errors
        """
        self._wait_for_rate_limit()
        
        # Prepare request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_params = {"token": self.api_key}
        if params:
            request_params.update(params)
        
        try:
            self.logger.debug(f"Making request to {url} with params: {request_params}")
            
            response = self.session.get(
                url,
                params=request_params,
                timeout=self.timeout
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                self.logger.warning(f"Rate limited. Waiting {retry_after} seconds")
                time.sleep(retry_after)
                raise AqicnRateLimitError(f"Rate limit exceeded. Retry after {retry_after} seconds")
            
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            # Check API-level errors
            if data.get('status') != 'ok':
                error_msg = data.get('data', 'Unknown API error')
                self.logger.error(f"API error: {error_msg}")
                raise AqicnApiError(f"API error: {error_msg}")
            
            self.logger.debug(f"Request successful. Response keys: {list(data.keys())}")
            return data
            
        except requests.exceptions.Timeout:
            raise AqicnClientError(f"Request timeout after {self.timeout} seconds")
        except requests.exceptions.ConnectionError as e:
            raise AqicnClientError(f"Connection error: {e}")
        except requests.exceptions.HTTPError as e:
            raise AqicnClientError(f"HTTP error: {e}")
        except json.JSONDecodeError as e:
            raise AqicnClientError(f"Invalid JSON response: {e}")
    
    def list_stations(self, country: str = "VN") -> List[Dict[str, Any]]:
        """
        Fetch all air quality stations for a country.
        
        Args:
            country: Country code (default: "VN" for Vietnam)
            
        Returns:
            List of station dictionaries with id, name, coordinates, country
            
        Raises:
            AqicnClientError: On API or client errors
        """
        self.logger.info(f"Fetching stations for country: {country}")
        
        stations = set()
        
        # Define search terms based on country
        if country.upper() == "VN":
            search_terms = [
                'hanoi', 'ho chi minh', 'saigon', 'da nang', 'hai phong', 'can tho',
                'hue', 'nha trang', 'vung tau', 'bien hoa', 'my tho', 'rach gia',
                'ca mau', 'long xuyen', 'chau doc', 'tay ninh', 'dong thap',
                'an giang', 'kien giang', 'soc trang', 'bac lieu', 'vinh long',
                'tra vinh', 'ben tre', 'tien giang', 'long an', 'dong nai',
                'ba ria', 'binh duong', 'binh phuoc', 'binh thuan', 'ninh thuan',
                'lam dong', 'dak lak', 'dak nong', 'gia lai', 'kon tum',
                'ha giang', 'cao bang', 'bac kan', 'tuyen quang', 'lao cai',
                'dien bien', 'lai chau', 'son la', 'yen bai', 'hoa binh',
                'thai nguyen', 'lang son', 'quang ninh', 'bac giang', 'phu tho',
                'vinh phuc', 'bac ninh', 'hai duong', 'hung yen', 'thai binh',
                'ha nam', 'nam dinh', 'ninh binh', 'thanh hoa', 'nghe an',
                'ha tinh', 'quang binh', 'quang tri', 'quang nam', 'quang ngai',
                'binh dinh', 'phu yen', 'khanh hoa', 'vietnam'
            ]
        else:
            # For other countries, use the country name
            search_terms = [country.lower()]
        
        total_found = 0
        
        for term in search_terms:
            try:
                data = self._make_request("search/", {"keyword": term})
                
                if 'data' in data:
                    for station in data['data']:
                        if self._is_target_country_station(station, country):
                            station_id = station.get('uid') or station.get('idx')
                            if station_id:
                                station_data = station.get('station', {})
                                stations.add((
                                    station_id,
                                    station_data.get('name', ''),
                                    tuple(station_data.get('geo', []))
                                ))
                                total_found += 1
                
                # Small delay between searches
                time.sleep(0.1)
                
            except AqicnClientError as e:
                self.logger.warning(f"Error searching '{term}': {e}")
                continue
        
        # Convert to list format
        stations_list = []
        for station_id, name, geo in stations:
            stations_list.append({
                'id': station_id,
                'name': name,
                'coordinates': list(geo) if geo else [],
                'country': country.upper()
            })
        
        # Sort by name
        stations_list.sort(key=lambda x: x['name'])
        
        self.logger.info(f"Found {len(stations_list)} unique stations for {country}")
        return stations_list
    
    def _is_target_country_station(self, station: Dict, country: str) -> bool:
        """
        Check if station belongs to target country.
        
        Args:
            station: Station data from API
            country: Target country code
            
        Returns:
            True if station is in target country
        """
        station_data = station.get('station', {})
        name = station_data.get('name', '').lower()
        geo = station_data.get('geo', [])
        
        country_lower = country.lower()
        
        # Vietnam-specific logic
        if country_lower == "vn":
            vietnam_indicators = ['vietnam', 'viet nam', 'việt nam']
            if any(indicator in name for indicator in vietnam_indicators):
                return True
            
            # Check coordinates are in Vietnam bounds
            if geo and len(geo) >= 2:
                # Handle both [lat, lng] and [lng, lat] formats
                lat = geo[0] if abs(geo[0]) > abs(geo[1]) else geo[1]
                lng = geo[1] if abs(geo[0]) > abs(geo[1]) else geo[0]
                
                # Vietnam geographic bounds
                if 8.0 <= lat <= 24.0 and 102.0 <= lng <= 110.0:
                    return True
        
        # Generic country check
        return country_lower in name
    
    def fetch_hourly(
        self,
        station_idx: Union[int, str],
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None
    ) -> Dict[str, Any]:
        """
        Fetch hourly air quality data for a station.
        
        Args:
            station_idx: Station ID or index
            start_date: Start date (YYYY-MM-DD format or datetime)
            end_date: End date (YYYY-MM-DD format or datetime)
            
        Returns:
            Dictionary containing time-series air quality data
            
        Raises:
            AqicnClientError: On API or client errors
        """
        self.logger.info(f"Fetching hourly data for station {station_idx}")
        
        # Get current station data
        data = self._make_request(f"feed/@{station_idx}/")
        
        if 'data' not in data:
            raise AqicnApiError(f"No data found for station {station_idx}")
        
        station_data = data['data']
        
        # Extract time series data
        result = {
            'station_idx': station_idx,
            'station_name': station_data.get('city', {}).get('name', ''),
            'coordinates': station_data.get('city', {}).get('geo', []),
            'timezone': station_data.get('time', {}).get('tz', ''),
            'current_time': station_data.get('time', {}).get('s', ''),
            'current_aqi': station_data.get('aqi', None),
            'current_iaqi': station_data.get('iaqi', {}),
            'attributions': station_data.get('attributions', []),
            'forecast': station_data.get('forecast', {}),
            'time_series': []
        }
        
        # If historical data is available in forecast.daily
        if 'forecast' in station_data and 'daily' in station_data['forecast']:
            daily_forecast = station_data['forecast']['daily']
            for pollutant, values in daily_forecast.items():
                if isinstance(values, list):
                    for i, value in enumerate(values):
                        if isinstance(value, dict) and 'day' in value:
                            result['time_series'].append({
                                'date': value['day'],
                                'pollutant': pollutant,
                                'avg': value.get('avg'),
                                'min': value.get('min'),
                                'max': value.get('max')
                            })
        
        self.logger.info(f"Retrieved data for station {station_idx}")
        return result
    
    def fetch_forecast(self, station_idx: Union[int, str]) -> Dict[str, Any]:
        """
        Fetch daily air quality forecast for a station.
        
        Args:
            station_idx: Station ID or index
            
        Returns:
            Dictionary containing forecast data with pollutants by day
            
        Raises:
            AqicnClientError: On API or client errors
        """
        self.logger.info(f"Fetching forecast for station {station_idx}")
        
        data = self._make_request(f"feed/@{station_idx}/")
        
        if 'data' not in data:
            raise AqicnApiError(f"No data found for station {station_idx}")
        
        station_data = data['data']
        forecast_data = station_data.get('forecast', {})
        
        result = {
            'station_idx': station_idx,
            'station_name': station_data.get('city', {}).get('name', ''),
            'coordinates': station_data.get('city', {}).get('geo', []),
            'fetched_at': datetime.utcnow().isoformat() + 'Z',
            'daily_forecasts': []
        }
        
        # Process daily forecasts
        if 'daily' in forecast_data:
            daily_data = forecast_data['daily']
            
            # Get all unique days from any pollutant
            all_days = set()
            for pollutant_data in daily_data.values():
                if isinstance(pollutant_data, list):
                    for entry in pollutant_data:
                        if isinstance(entry, dict) and 'day' in entry:
                            all_days.add(entry['day'])
            
            # Organize by day
            for day in sorted(all_days):
                day_forecast = {
                    'day': day,
                    'pollutants': {}
                }
                
                # Collect all pollutants for this day
                for pollutant, pollutant_data in daily_data.items():
                    if isinstance(pollutant_data, list):
                        for entry in pollutant_data:
                            if isinstance(entry, dict) and entry.get('day') == day:
                                day_forecast['pollutants'][pollutant] = {
                                    'avg': entry.get('avg'),
                                    'min': entry.get('min'),
                                    'max': entry.get('max')
                                }
                                break
                
                if day_forecast['pollutants']:
                    result['daily_forecasts'].append(day_forecast)
        
        self.logger.info(f"Retrieved forecast for station {station_idx} with {len(result['daily_forecasts'])} days")
        return result
    
    def get_station_info(self, station_idx: Union[int, str]) -> Dict[str, Any]:
        """
        Get detailed information for a specific station.
        
        Args:
            station_idx: Station ID or index
            
        Returns:
            Dictionary containing station metadata
            
        Raises:
            AqicnClientError: On API or client errors
        """
        self.logger.info(f"Fetching station info for {station_idx}")
        
        data = self._make_request(f"feed/@{station_idx}/")
        
        if 'data' not in data:
            raise AqicnApiError(f"No data found for station {station_idx}")
        
        station_data = data['data']
        
        return {
            'idx': station_data.get('idx'),
            'name': station_data.get('city', {}).get('name', ''),
            'url': station_data.get('city', {}).get('url', ''),
            'coordinates': station_data.get('city', {}).get('geo', []),
            'timezone': station_data.get('time', {}).get('tz', ''),
            'attributions': station_data.get('attributions', []),
            'dominentpol': station_data.get('dominentpol', ''),
            'current_aqi': station_data.get('aqi', None),
            'last_update': station_data.get('time', {}).get('s', '')
        }

    def get_current_data(self, station_idx: Union[int, str]) -> Dict[str, Any]:
        """
        Get current real-time air quality data for a specific station.
        
        Args:
            station_idx: Station ID or index
            
        Returns:
            Dictionary containing current air quality data (not forecast)
            
        Raises:
            AqicnClientError: On API or client errors
        """
        self.logger.info(f"Fetching current data for station {station_idx}")
        
        data = self._make_request(f"feed/@{station_idx}/")
        
        if 'data' not in data:
            raise AqicnApiError(f"No data found for station {station_idx}")
        
        station_data = data['data']
        
        # Extract current real-time data only (not forecast)
        return {
            'aqi': station_data.get('aqi', None),
            'idx': station_data.get('idx'),
            'time': station_data.get('time', {}),
            'iaqi': station_data.get('iaqi', {}),
            'dominentpol': station_data.get('dominentpol', ''),
            'city': station_data.get('city', {}),
            'attributions': station_data.get('attributions', [])
        }


def create_client_from_env() -> AqicnClient:
    """
    Create AQICN client from environment variables.
    
    Returns:
        Configured AqicnClient instance
        
    Raises:
        AqicnClientError: If required environment variables are missing
    """
    import os
    
    api_key = os.getenv('AQICN_API_KEY')
    if not api_key:
        raise AqicnClientError("AQICN_API_KEY environment variable is required")
    
    base_url = os.getenv('AQICN_API_URL', 'https://api.waqi.info')
    rate_limit = int(os.getenv('AQICN_RATE_LIMIT', '1000'))
    timeout = int(os.getenv('AQICN_TIMEOUT', '30'))
    
    return AqicnClient(
        api_key=api_key,
        base_url=base_url,
        rate_limit=rate_limit,
        timeout=timeout
    )
