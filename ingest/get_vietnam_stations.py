"""
Vietnam Air Quality Stations Fetcher.
Retrieves all active air quality monitoring stations in Vietnam from AQICN API
and exports them in MongoDB collection format with deduplication and validation.
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
import requests
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aqicn_client import AqicnClient, AqicnClientError


class VietnamStationsFetcher:
    """
    Fetches and processes all active air quality monitoring stations in Vietnam.
    Handles deduplication, validation, and export to JSON format.
    """
    
    def __init__(self, api_key: str, output_dir: str = "data_results"):
        """
        Initialize the Vietnam stations fetcher.
        
        Args:
            api_key: AQICN API key
            output_dir: Directory to save output files
        """
        self.api_key = api_key
        # Use absolute path relative to the script location
        script_dir = Path(__file__).parent
        self.output_dir = script_dir / output_dir
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize client
        self.client = AqicnClient(
            api_key=api_key,
            rate_limit=1000,
            timeout=30,
            max_retries=3
        )
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Vietnam provinces and cities for comprehensive search
        self.vietnam_search_terms = [
            'vietnam', 'viet nam', 'hanoi', 'ho chi minh', 'saigon',
            'da nang', 'hai phong', 'can tho', 'bien hoa', 'hue',
            'nha trang', 'buon ma thuot', 'quy nhon', 'vung tau',
            'thai nguyen', 'phan thiet', 'thai binh', 'ha long',
            'nam dinh', 'cam ranh', 'vinh', 'my tho', 'rach gia',
            'long xuyen', 'ha tinh', 'dong hoi', 'pleiku', 'dong ha',
            'tam ky', 'tuy hoa', 'bac lieu', 'ca mau', 'chau doc',
            'ha giang', 'cao bang', 'lang son', 'lao cai', 'dien bien',
            'son la', 'lai chau', 'yen bai', 'tuyen quang', 'ha giang',
            'bac kan', 'thai nguyen', 'lang son', 'quang ninh', 'bac giang',
            'phu tho', 'vinh phuc', 'bac ninh', 'hai duong', 'hung yen',
            'thai binh', 'ha nam', 'nam dinh', 'ninh binh', 'thanh hoa',
            'nghe an', 'ha tinh', 'quang binh', 'quang tri', 'thua thien hue',
            'da nang', 'quang nam', 'quang ngai', 'binh dinh', 'phu yen',
            'khanh hoa', 'ninh thuan', 'binh thuan', 'kon tum', 'gia lai',
            'dak lak', 'dak nong', 'lam dong', 'binh phuoc', 'tay ninh',
            'binh duong', 'dong nai', 'ba ria vung tau', 'ho chi minh',
            'long an', 'tien giang', 'ben tre', 'tra vinh', 'vinh long',
            'dong thap', 'an giang', 'kien giang', 'can tho', 'hau giang',
            'soc trang', 'bac lieu', 'ca mau'
        ]
        
    def fetch_all_vietnam_stations(self) -> List[Dict[str, Any]]:
        """
        Fetch all active air quality stations in Vietnam.
        
        Returns:
            List of station dictionaries with comprehensive data
        """
        self.logger.info("Starting comprehensive Vietnam stations search")
        
        # Use set to track unique stations by ID and coordinates
        unique_stations: Dict[int, Dict] = {}
        coordinate_map: Dict[Tuple[float, float], int] = {}
        
        # Search using multiple terms
        for term in self.vietnam_search_terms:
            try:
                self.logger.info(f"Searching with term: {term}")
                
                # Search for stations
                search_data = self.client._make_request("search/", {"keyword": term})
                
                if 'data' in search_data and search_data['data']:
                    for station in search_data['data']:
                        station_id = station.get('uid') or station.get('idx')
                        if not station_id:
                            continue
                            
                        # Check if this is a Vietnam station
                        if not self._is_vietnam_station(station):
                            continue
                            
                        # Get detailed station info
                        try:
                            detailed_station = self._fetch_station_details(station_id)
                            if detailed_station and self._is_active_station(detailed_station):
                                # Check for duplicates by coordinates
                                coords = self._extract_coordinates(detailed_station)
                                if coords:
                                    coord_key = (round(coords[0], 6), round(coords[1], 6))
                                    
                                    # Skip if we already have this location
                                    if coord_key in coordinate_map:
                                        existing_id = coordinate_map[coord_key]
                                        self.logger.debug(f"Duplicate location {coord_key}: station {station_id} vs {existing_id}")
                                        continue
                                    
                                    # Store the station
                                    unique_stations[station_id] = detailed_station
                                    coordinate_map[coord_key] = station_id
                                    self.logger.info(f"Added station {station_id}: {detailed_station.get('city', {}).get('name', 'Unknown')}")
                        
                        except Exception as e:
                            self.logger.warning(f"Error fetching details for station {station_id}: {e}")
                            continue
                
                # Small delay between searches
                time.sleep(0.2)
                
            except Exception as e:
                self.logger.warning(f"Error searching with term '{term}': {e}")
                continue
        
        stations_list = list(unique_stations.values())
        self.logger.info(f"Found {len(stations_list)} unique active stations in Vietnam")
        
        return stations_list
    
    def _is_vietnam_station(self, station: Dict) -> bool:
        """
        Check if a station is located in Vietnam with strict filtering.
        
        Args:
            station: Station data from search results
            
        Returns:
            True if station is confirmed to be in Vietnam
        """
        # Check country field if available
        country = station.get('country', '').lower()
        if 'vietnam' in country or 'viet nam' in country:
            return True
        
        # Check station name and URL
        station_data = station.get('station', {})
        name = station_data.get('name', '').lower()
        url = station_data.get('url', '').lower()
        
        # Strong exclusion patterns for foreign stations
        foreign_patterns = [
            'china', 'chinese', '中国', '省', '市', '县', '区', '厅', '局',
            'hainan', 'guangxi', 'yunnan', 'thailand', 'laos', 'cambodia',
            'changjiang', '昌江', '海南', '国土环境', '资源', '循环经济',
            'guangdong', 'guangzhou', 'shenzhen', 'beijing', 'shanghai',
            'macau', 'hong kong', 'taiwan', 'singapore', 'malaysia'
        ]
        
        # Check for exclusion patterns
        for pattern in foreign_patterns:
            if pattern in name or pattern in url:
                return False
        
        # Vietnam positive indicators (city names and variations)
        vietnam_indicators = [
            'vietnam', 'viet-nam', 'hanoi', 'ho-chi-minh', 'saigon', 'da-nang',
            'hai-phong', 'can-tho', 'bien-hoa', 'vung-tau', 'nha-trang',
            'hue', 'vinh', 'quy-nhon', 'pleiku', 'buon-ma-thuot', 'my-tho',
            'long-xuyen', 'rach-gia', 'phan-thiet', 'dong-ha', 'lang-son',
            'ha-giang', 'cao-bang', 'lao-cai', 'dien-bien', 'son-la',
            'nam-dinh', 'thai-nguyen', 'tuyen-quang', 'yen-bai', 'ha-nam',
            'ninh-binh', 'thanh-hoa', 'nghe-an', 'ha-tinh', 'quang-binh',
            'quang-tri', 'quang-nam', 'quang-ngai', 'binh-dinh', 'phu-yen',
            'khanh-hoa', 'ninh-thuan', 'binh-thuan', 'kon-tum', 'gia-lai',
            'dak-lak', 'dak-nong', 'lam-dong', 'binh-phuoc', 'tay-ninh',
            'binh-duong', 'dong-nai', 'ba-ria', 'long-an', 'tien-giang',
            'ben-tre', 'tra-vinh', 'vinh-long', 'dong-thap', 'an-giang',
            'kien-giang', 'bac-lieu', 'ca-mau'
        ]
        
        # Check for Vietnam indicators
        has_vietnam_indicator = False
        for indicator in vietnam_indicators:
            if indicator in name or indicator in url:
                has_vietnam_indicator = True
                break
        
        # Check coordinates (Vietnam bounds: 8.2°-23.4°N, 102.1°-109.5°E)
        coords = station_data.get('geo', [])
        coords_in_vietnam = False
        
        if len(coords) >= 2:
            try:
                lat, lon = float(coords[0]), float(coords[1])
                # Stricter Vietnam bounds
                if 8.2 <= lat <= 23.4 and 102.1 <= lon <= 109.5:
                    coords_in_vietnam = True
                    
                    # Additional check for border areas that might be foreign
                    # Exclude far northern areas that might be China
                    if lat > 22.5 and (lon < 103.0 or lon > 108.0):
                        coords_in_vietnam = False
                    
                    # Exclude far western areas that might be Laos
                    if lon < 103.0 and lat > 20.0:
                        coords_in_vietnam = False
                        
            except (ValueError, TypeError):
                coords_in_vietnam = False
        
        # Only accept if both positive indicators and coordinates match
        # Or if there's a strong Vietnam indicator
        if has_vietnam_indicator and coords_in_vietnam:
            return True
        elif has_vietnam_indicator and not coords_in_vietnam:
            # Vietnam indicator but coords don't match - be cautious
            return False
        elif coords_in_vietnam and not has_vietnam_indicator:
            # Coords match but no clear indicator - be cautious for border areas
            return False
        
        return False
    
    def _fetch_station_details(self, station_id: int) -> Optional[Dict]:
        """
        Fetch detailed information for a specific station.
        
        Args:
            station_id: Station ID
            
        Returns:
            Detailed station data or None if unavailable
        """
        try:
            data = self.client._make_request(f"feed/@{station_id}/")
            
            if 'data' not in data:
                return None
            
            station_data = data['data']
            
            # Transform to MongoDB collection format
            result = {
                '_id': station_id,
                'city': {
                    'name': station_data.get('city', {}).get('name', ''),
                    'url': station_data.get('city', {}).get('url', ''),
                    'geo': {
                        'type': 'Point',
                        'coordinates': station_data.get('city', {}).get('geo', [])
                    }
                }
            }
            
            # Add timezone if available
            if 'time' in station_data and 'tz' in station_data['time']:
                result['time'] = {
                    'tz': station_data['time']['tz']
                }
            
            # Add attributions if available
            if 'attributions' in station_data and station_data['attributions']:
                result['attributions'] = []
                for attr in station_data['attributions']:
                    attribution = {}
                    if 'name' in attr:
                        attribution['name'] = attr['name']
                    if 'url' in attr:
                        attribution['url'] = attr['url']
                    if 'logo' in attr:
                        attribution['logo'] = attr['logo']
                    if attribution:
                        result['attributions'].append(attribution)
            
            return result
            
        except Exception as e:
            self.logger.warning(f"Error fetching station {station_id}: {e}")
            return None
    
    def _is_active_station(self, station: Dict) -> bool:
        """
        Check if a station is currently active.
        
        Args:
            station: Station data
            
        Returns:
            True if station appears to be active
        """
        # Basic validation
        if not station or '_id' not in station:
            return False
        
        city = station.get('city', {})
        if not city.get('name') or not city.get('url'):
            return False
        
        # Check coordinates
        geo = city.get('geo', {})
        coords = geo.get('coordinates', [])
        if not coords or len(coords) < 2:
            return False
        
        # Coordinates should be valid
        try:
            lat, lon = float(coords[0]), float(coords[1])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return False
        except (ValueError, TypeError):
            return False
        
        return True
    
    def _extract_coordinates(self, station: Dict) -> Optional[Tuple[float, float]]:
        """
        Extract coordinates from station data.
        
        Args:
            station: Station data
            
        Returns:
            Tuple of (latitude, longitude) or None
        """
        try:
            coords = station.get('city', {}).get('geo', {}).get('coordinates', [])
            if len(coords) >= 2:
                return (float(coords[0]), float(coords[1]))
        except (ValueError, TypeError):
            pass
        return None
    
    def validate_stations(self, stations: List[Dict]) -> List[Dict]:
        """
        Validate and clean station data.
        
        Args:
            stations: List of station dictionaries
            
        Returns:
            List of validated stations
        """
        valid_stations = []
        
        for station in stations:
            if self._validate_station_schema(station):
                valid_stations.append(station)
            else:
                self.logger.warning(f"Invalid station schema: {station.get('_id', 'unknown')}")
        
        return valid_stations
    
    def _validate_station_schema(self, station: Dict) -> bool:
        """
        Validate station against MongoDB schema.
        
        Args:
            station: Station dictionary
            
        Returns:
            True if valid
        """
        # Check required fields
        if '_id' not in station or not isinstance(station['_id'], int):
            return False
        
        city = station.get('city', {})
        if not isinstance(city, dict):
            return False
        
        # Check required city fields
        if not city.get('name') or not isinstance(city['name'], str):
            return False
        
        if not city.get('url') or not isinstance(city['url'], str):
            return False
        
        # Check geo structure
        geo = city.get('geo', {})
        if not isinstance(geo, dict):
            return False
        
        if geo.get('type') != 'Point':
            return False
        
        coords = geo.get('coordinates', [])
        if not isinstance(coords, list) or len(coords) != 2:
            return False
        
        try:
            lat, lon = float(coords[0]), float(coords[1])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return False
        except (ValueError, TypeError):
            return False
        
        return True
    
    def export_to_json(self, stations: List[Dict], filename: str = None) -> str:
        """
        Export stations to JSON file.
        
        Args:
            stations: List of station dictionaries
            filename: Output filename (optional)
            
        Returns:
            Path to exported file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vietnam_stations_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        # Prepare data for export
        export_data = {
            'metadata': {
                'collection': 'waqi_stations',
                'fetched_at': datetime.utcnow().isoformat() + 'Z',
                'total_stations': len(stations),
                'country': 'Vietnam',
                'description': 'Active air quality monitoring stations in Vietnam'
            },
            'data': stations
        }
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Exported {len(stations)} stations to {output_path}")
        self.logger.info(f"File size: {output_path.stat().st_size} bytes")
        return str(output_path)
    
    def run(self) -> str:
        """
        Run the complete process to fetch and export Vietnam stations.
        
        Returns:
            Path to exported JSON file
        """
        self.logger.info("Starting Vietnam stations collection process")
        
        # Fetch all stations
        stations = self.fetch_all_vietnam_stations()
        
        # Validate stations
        valid_stations = self.validate_stations(stations)
        
        if len(valid_stations) != len(stations):
            self.logger.warning(f"Filtered out {len(stations) - len(valid_stations)} invalid stations")
        
        if not valid_stations:
            raise ValueError("No valid stations found")
        
        # Export to JSON
        output_path = self.export_to_json(valid_stations)
        
        self.logger.info(f"Process completed successfully. {len(valid_stations)} stations exported to {output_path}")
        return output_path


def main():
    """Main execution function."""
    # Load API key from environment
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('AQICN_API_KEY')
    if not api_key:
        raise ValueError("AQICN_API_KEY not found in environment variables")
    
    # Create fetcher and run
    fetcher = VietnamStationsFetcher(api_key)
    
    try:
        output_path = fetcher.run()
        print(f"Successfully exported Vietnam stations to: {output_path}")
        
        # Print summary statistics
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        stations = data['data']
        print(f"\nSummary:")
        print(f"Total stations: {len(stations)}")
        
        # Group by provinces/cities
        cities = {}
        for station in stations:
            city_name = station['city']['name']
            if city_name not in cities:
                cities[city_name] = 0
            cities[city_name] += 1
        
        print(f"Unique cities: {len(cities)}")
        print("\nTop 10 cities by station count:")
        for city, count in sorted(cities.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {city}: {count} stations")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
