"""
Vietnam Air Quality Stations Data Fetcher

This module fetches station metadata from WAQI API using station URLs
and exports the data in MongoDB-compatible format.
"""

import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import argparse
from urllib.parse import urlparse, unquote, parse_qs

try:
    import requests
except ImportError:
    print("requests library not found. Install with: pip install requests")
    exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("python-dotenv library not found. Install with: pip install python-dotenv")
    exit(1)

# Load environment variables
load_dotenv()

# Configure logging with proper Unicode handling

# Create console handler with UTF-8 encoding
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Create file handler with UTF-8 encoding
file_handler = logging.FileHandler('station_fetch.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Configure root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Set console encoding to handle Vietnamese characters
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
logger = logging.getLogger(__name__)


class WAQIStationFetcher:
    """Fetches station data from WAQI API and formats for MongoDB storage."""
    
    def __init__(self):
        self.api_key = os.getenv('AQICN_API_KEY')
        self.api_url = os.getenv('AQICN_API_URL', 'https://api.waqi.info/')
        self.timeout = int(os.getenv('AQICN_TIMEOUT', '30'))
        self.rate_limit = int(os.getenv('AQICN_RATE_LIMIT', '1000'))
        
        if not self.api_key:
            raise ValueError("AQICN_API_KEY not found in environment variables")
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AirQualityMonitoring/1.0'
        })
        
        # Ensure data_results directory exists
        self.output_dir = Path(__file__).parent / 'data_results'
        self.output_dir.mkdir(exist_ok=True)
        
        logger.info(f"Initialized WAQI fetcher with API URL: {self.api_url}")

    def extract_station_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract station identifier from WAQI URL.
        Handles both /city/ and /station/ URL patterns.
        
        Args:
            url: WAQI station URL
            
        Returns:
            Station identifier or None if not extractable
        """
        try:
            # Parse URL path and decode URL-encoded characters
            parsed = urlparse(url)
            path = unquote(parsed.path or '')

            # Common feed pattern: /feed/@<id>/ or /feed/<id>/
            m = re.search(r'/feed/@?([^/]+)/?', path)
            if m:
                return m.group(1).lstrip('@')

            # Fallback: split path parts and handle /city/ and /station/
            path_parts = [p for p in path.split('/') if p]

            # Handle /city/ URLs
            if 'city' in path_parts:
                city_index = path_parts.index('city')
                location_parts = path_parts[city_index + 1:]
                station_id = '/'.join(location_parts)
                # Normalize: remove any leading '@' if present
                return station_id.lstrip('@')

            # Handle /station/ URLs
            if 'station' in path_parts:
                station_index = path_parts.index('station')
                if station_index + 1 < len(path_parts):
                    # For station URLs, use the part after 'station'
                    station_id = path_parts[station_index + 1]
                    # Normalize: strip leading '@' and any trailing slashes
                    return station_id.lstrip('@').strip('/')
            
            logger.warning(f"URL pattern not recognized: {url}")
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract station ID from URL {url}: {e}")
            return None

    def fetch_station_data(self, station_id: str, token: Optional[str] = None) -> Optional[Dict]:
        """
        Fetch station data from WAQI API.
        
        Args:
            station_id: Station identifier
            
        Returns:
            Station data or None if fetch failed
        """
        try:
            # Normalize station id and construct API URL for station feed
            sid = str(station_id).lstrip('@').strip()
            api_url = f"{self.api_url.rstrip('/')}/feed/@{sid}/"
            # allow per-request token override (from CSV), otherwise use configured API key
            token_to_use = token if token else self.api_key
            params = {'token': token_to_use}
            
            logger.debug(f"Fetching data for station: {station_id}")
            logger.debug(f"API URL: {api_url}")
            
            response = self.session.get(
                api_url,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'ok':
                logger.warning(f"API returned non-ok status for {station_id}: {data.get('status')}")
                return None
                
            return data.get('data')
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for station {station_id}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode failed for station {station_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching station {station_id}: {e}")
            return None

    def format_station_data(self, raw_data: Dict, original_url: str) -> Optional[Dict]:
        """
        Format raw WAQI data to MongoDB schema format.
        
        Args:
            raw_data: Raw data from WAQI API
            original_url: Original station URL from CSV
            
        Returns:
            Formatted station document or None if formatting failed
        """
        try:
            # Extract required fields
            station_idx = raw_data.get('idx')
            city_data = raw_data.get('city', {})
            time_data = raw_data.get('time', {})
            attributions = raw_data.get('attributions', [])
            
            if not station_idx or not city_data:
                logger.warning(f"Missing required fields in station data: {raw_data}")
                return None
            
            # Extract coordinates
            geo_data = city_data.get('geo')
            if not geo_data or len(geo_data) != 2:
                logger.warning(f"Invalid geo data for station {station_idx}: {geo_data}")
                return None
                
            longitude, latitude = geo_data
            
            # Format according to MongoDB schema
            formatted_data = {
                "_id": station_idx,
                "city": {
                    "name": city_data.get('name', ''),
                    "url": original_url,  # Use original URL from CSV
                    "geo": {
                        "type": "Point",
                        "coordinates": [float(longitude), float(latitude)]
                    }
                }
            }

            # Include verbose location/address if provided by the API
            if city_data.get('location'):
                # Keep original API string (often full address) under city.location
                formatted_data["city"]["location"] = city_data.get('location')
            
            # Add timezone if available
            if time_data.get('tz'):
                formatted_data["time"] = {
                    "tz": time_data['tz']
                }
            
            # Format attributions
            if attributions:
                formatted_attributions = []
                for attr in attributions:
                    formatted_attr = {}
                    if attr.get('name'):
                        formatted_attr['name'] = attr['name']
                    if attr.get('url'):
                        formatted_attr['url'] = attr['url']
                    if attr.get('logo'):
                        formatted_attr['logo'] = attr['logo']
                    
                    if formatted_attr:
                        formatted_attributions.append(formatted_attr)
                
                if formatted_attributions:
                    formatted_data["attributions"] = formatted_attributions
            
            return formatted_data
            
        except Exception as e:
            logger.error(f"Error formatting station data: {e}")
            return None

    def read_station_urls(self, csv_file_path: str) -> List[Dict[str, Optional[str]]]:
        """
        Read station URLs from CSV file.
        
        Args:
            csv_file_path: Path to CSV file
            
        Returns:
            List of station URLs
        """
        urls: List[Dict[str, Optional[str]]] = []

        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    url = row.get('URL', '').strip()
                    if not url:
                        continue

                    # accept both api.waqi.info and aqicn.org feed URLs
                    parsed = urlparse(url)
                    path_ok = '/feed/' in parsed.path or 'feed' in parsed.path
                    host_ok = parsed.netloc.endswith('waqi.info') or 'aqicn.org' in parsed.netloc
                    if not (path_ok or host_ok):
                        # try lenient check: URL contains '/feed/' somewhere
                        if '/feed/' not in url:
                            continue

                    # extract token from query if present (token=...), empty string means use env
                    qs = parse_qs(parsed.query)
                    token_list = qs.get('token') or []
                    token_val = None
                    if token_list:
                        # pick first token if non-empty, otherwise leave as None to fallback to env
                        tok = token_list[0].strip()
                        if tok:
                            token_val = tok

                    urls.append({'url': url, 'token': token_val})
                        
            logger.info(f"Read {len(urls)} station URLs from {csv_file_path}")
            return urls
            
        except Exception as e:
            logger.error(f"Error reading CSV file {csv_file_path}: {e}")
            return []

    def fetch_all_stations(self, csv_file_path: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch all station data from URLs in CSV file.
        
        Args:
            csv_file_path: Path to CSV file with station URLs
            
        Returns:
            List of formatted station documents
        """
        urls = self.read_station_urls(csv_file_path)
        stations = []

        logger.info(f"Starting to fetch data for {len(urls)} stations")

        for i, item in enumerate(urls, 1):
            url = item.get('url')
            token = item.get('token')
            logger.info(f"Processing station {i}/{len(urls)}: {url}")

            # Extract station ID
            station_id = self.extract_station_id_from_url(url)
            if not station_id:
                logger.warning(f"Could not extract station ID from URL: {url}")
                continue
            
            # Fetch station data (allow per-URL token override)
            raw_data = self.fetch_station_data(station_id, token=token)
            if not raw_data:
                logger.warning(f"Failed to fetch data for station: {station_id}")
                continue
            
            # Format station data
            formatted_data = self.format_station_data(raw_data, url)
            if formatted_data:
                stations.append(formatted_data)
                # Safe logging for Unicode characters
                try:
                    station_name = formatted_data['city']['name']
                    logger.info(f"Successfully processed station {formatted_data['_id']}: {station_name}")
                except UnicodeEncodeError:
                    # Fallback for encoding issues
                    station_name_safe = formatted_data['city']['name'].encode('ascii', errors='replace').decode('ascii')
                    logger.info(f"Successfully processed station {formatted_data['_id']}: {station_name_safe}")
            else:
                logger.warning(f"Failed to format data for station: {station_id}")
            
            # Rate limiting - be more conservative
            if i < len(urls):
                sleep_time = max(1.0, 60 / self.rate_limit)  # At least 1 second between requests
                logger.debug(f"Sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)

            # Respect optional processing limit (number of URLs to attempt)
            if limit and i >= limit:
                logger.info(f"Reached processing limit of {limit} URLs")
                break
        
        logger.info(f"Successfully fetched {len(stations)} out of {len(urls)} stations")
        return stations

    def export_to_json(self, stations: List[Dict], filename: str = None) -> str:
        """
        Export station data to JSON file.
        
        Args:
            stations: List of station documents
            filename: Output filename (optional)
            
        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"vietnam_stations_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        try:
            # Create structured JSON with metadata (compatible with import script)
            export_data = {
                "metadata": {
                    "collection": "waqi_stations",
                    "source": "WAQI API",
                    "export_time": datetime.now().isoformat(),
                    "total_stations": len(stations),
                    "country": "Vietnam"
                },
                "data": stations
            }
            
            with open(output_path, 'w', encoding='utf-8') as file:
                json.dump(export_data, file, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(stations)} stations to {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            raise


def main():
    """Main function to fetch and export Vietnam station data."""
    try:
        parser = argparse.ArgumentParser(description="Fetch Vietnam WAQI stations from CSV of URLs and export JSON")
        parser.add_argument("-c", "--csv", dest="csv", help="Path to CSV file with station URLs (default: ingest/data_results/stations.csv)")
        parser.add_argument("-o", "--out", dest="out", help="Output JSON filename (optional). If omitted, a timestamped filename will be used.")
        parser.add_argument("-l", "--limit", dest="limit", type=int, help="Optional limit on number of URLs to process (for testing)")
        args = parser.parse_args()

        fetcher = WAQIStationFetcher()

        # Path to CSV file (default)
        default_csv = Path(__file__).parent / 'data_results' / 'stations.csv'
        csv_file_path = Path(args.csv) if args.csv else default_csv

        if not csv_file_path.exists():
            logger.error(f"CSV file not found: {csv_file_path}")
            return
        # Fetch all station data (respect optional limit)
        stations = fetcher.fetch_all_stations(
            str(csv_file_path),
            limit=args.limit if args.limit and args.limit > 0 else None,
        )
        
        if not stations:
            logger.warning("No station data was successfully fetched")
            return

        # Export to JSON (allow overriding filename)
        output_path = fetcher.export_to_json(stations, filename=args.out) if args.out else fetcher.export_to_json(stations)

        logger.info(f"Process completed successfully. Output file: {output_path}")
        logger.info(f"Total stations processed: {len(stations)}")

        # Print summary
        print(f"\n=== FETCH SUMMARY ===")
        print(f"Total stations fetched: {len(stations)}")
        print(f"Output file: {output_path}")
        print(f"Log file: station_fetch.log")

    except Exception as e:
        logger.error(f"Fatal error in main process: {e}")
        raise


if __name__ == "__main__":
    main()