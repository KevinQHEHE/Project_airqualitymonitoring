"""
Simple script to get all Vietnamese air quality stations and export the data.
Clean implementation without unnecessary complexity.
"""

import json
import requests
import time
from typing import List, Dict, Any

class VietnamStationsExporter:
    """Simple class to get and export Vietnamese air quality stations."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.waqi.info"
    
    def get_all_vietnam_stations(self) -> List[Dict[str, Any]]:
        """Get all Vietnamese air quality stations."""
        stations = set()
        
        # Vietnamese search terms
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
        
        print(f"Searching for Vietnamese stations...")
        
        for term in search_terms:
            try:
                url = f"{self.base_url}/search/?token={self.api_key}&keyword={term}"
                response = requests.get(url, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'ok' and 'data' in data:
                        for station in data['data']:
                            if self._is_vietnam_station(station):
                                station_id = station.get('uid') or station.get('idx')
                                if station_id:
                                    stations.add((
                                        station_id,
                                        station.get('station', {}).get('name', ''),
                                        tuple(station.get('station', {}).get('geo', []))
                                    ))
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                print(f"Error searching '{term}': {e}")
                continue
        
        # Convert to list
        stations_list = []
        for station_id, name, geo in stations:
            stations_list.append({
                'id': station_id,
                'name': name,
                'coordinates': list(geo) if geo else [],
                'country': 'Vietnam'
            })
        
        # Sort by name
        stations_list.sort(key=lambda x: x['name'])
        
        print(f"Found {len(stations_list)} Vietnamese stations")
        return stations_list
    
    def _is_vietnam_station(self, station: Dict) -> bool:
        """Check if station is in Vietnam."""
        station_data = station.get('station', {})
        name = station_data.get('name', '').lower()
        geo = station_data.get('geo', [])
        
        # Check name contains Vietnam indicators
        vietnam_indicators = ['vietnam', 'viet nam', 'việt nam']
        if any(indicator in name for indicator in vietnam_indicators):
            return True
        
        # Check coordinates are in Vietnam bounds
        if geo and len(geo) >= 2:
            # Handle both [lat, lng] and [lng, lat] formats
            lat = geo[0] if abs(geo[0]) > abs(geo[1]) else geo[1]
            lng = geo[1] if abs(geo[0]) > abs(geo[1]) else geo[0]
            
            # Vietnam bounds
            if 8.0 <= lat <= 24.0 and 102.0 <= lng <= 110.0:
                return True
        
        return False
    
    def export_to_json(self, stations: List[Dict], filename: str = 'vietnam_stations.json'):
        """Export stations data to JSON file."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'total_stations': len(stations),
                'country': 'Vietnam',
                'exported_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'stations': stations
            }, f, indent=2, ensure_ascii=False)
        
        print(f"Data exported to {filename}")
    
    def export_to_csv(self, stations: List[Dict], filename: str = 'vietnam_stations.csv'):
        """Export stations data to CSV file."""
        import csv
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Name', 'Latitude', 'Longitude', 'Country'])
            
            for station in stations:
                coords = station['coordinates']
                lat = coords[0] if len(coords) > 0 else ''
                lng = coords[1] if len(coords) > 1 else ''
                writer.writerow([
                    station['id'],
                    station['name'],
                    lat,
                    lng,
                    station['country']
                ])
        
        print(f"Data exported to {filename}")

def main():
    """Main function to get and export Vietnamese stations."""
    API_KEY = '588aee591df04f638fe50df2885de4e8275e0959'
    
    exporter = VietnamStationsExporter(API_KEY)
    
    # Get all Vietnamese stations
    stations = exporter.get_all_vietnam_stations()
    
    # Export to both JSON and CSV
    exporter.export_to_json(stations)
    exporter.export_to_csv(stations)
    
    print(f"\n✅ Complete! Found and exported {len(stations)} Vietnamese stations")
    print(f"📄 Files created: vietnam_stations.json, vietnam_stations.csv")

if __name__ == '__main__':
    main()
