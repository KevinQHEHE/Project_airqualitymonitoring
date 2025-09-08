"""Stations blueprint for managing air quality monitoring stations."""
from flask import Blueprint, request, jsonify
import logging
from backend.app.repositories import stations_repo

logger = logging.getLogger(__name__)

stations_bp = Blueprint('stations', __name__)


@stations_bp.route('/', methods=['GET'])
def get_stations():
    """Get list of air quality monitoring stations.
    
    Query parameters:
    - page: Page number (default: 1)
    - page_size: Number of items per page (default: 20)
    - city: Filter by city name
    - country: Filter by country code
    
    Returns:
        JSON: List of stations with pagination info
    """
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        city = request.args.get('city')
        country = request.args.get('country')
        
        # Build filter criteria
        filter_criteria = {}
        if city:
            filter_criteria['city'] = city
        if country:
            filter_criteria['country'] = country
            
        # Get stations using repository
        if city:
            stations = stations_repo.find_by_city(city)
        elif filter_criteria:
            stations = stations_repo.find_many(filter_criteria)
        else:
            stations = stations_repo.find_active_stations()
        
        # Convert ObjectId to string for JSON serialization
        for station in stations:
            if '_id' in station:
                station['_id'] = str(station['_id'])
        
        # Simple pagination (for demo - in production, use MongoDB skip/limit)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        # Simple pagination (for demo - in production, use MongoDB skip/limit)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_stations = stations[start_idx:end_idx]
        
        return jsonify({
            "stations": paginated_stations,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": len(stations),
                "pages": (len(stations) + page_size - 1) // page_size
            }
        }), 200
    
    except ValueError:
        return jsonify({"error": "Invalid page or page_size parameter"}), 400
    except Exception as e:
        logger.error(f"Get stations error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@stations_bp.route('/<station_id>', methods=['GET'])
def get_station(station_id):
    """Get details for a specific station.
    
    Args:
        station_id: Station ID (can be numeric ID or station_id string)
        
    Returns:
        JSON: Station details or error message
    """
    try:
        # Try to find by station_id first (string identifier)
        station = stations_repo.find_by_station_id(station_id)
        
        if not station:
            # If not found, try numeric lookup for backwards compatibility
            try:
                # Convert to int and look up by numeric ID if applicable
                numeric_id = int(station_id)
                station = stations_repo.find_one({"id": numeric_id})
            except ValueError:
                pass
        
        if not station:
            return jsonify({"error": "Station not found"}), 404
        
        # Convert ObjectId to string for JSON serialization
        if '_id' in station:
            station['_id'] = str(station['_id'])
            
        return jsonify(station), 200
    
    except Exception as e:
        logger.error(f"Get station error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@stations_bp.route('/', methods=['POST'])
def create_station():
    """Create a new monitoring station.
    
    Expected JSON body:
    {
        "name": "Station Name",
        "city": "City Name",
        "country": "Country Code",
        "latitude": 12.345,
        "longitude": 67.890
    }
    
    Returns:
        JSON: Created station info or error message
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        required_fields = ['name', 'city', 'country', 'latitude', 'longitude']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # TODO: Implement station creation in MongoDB
        return jsonify({
            "message": "Station created successfully",
            "station": data
        }), 201
    
    except Exception as e:
        logger.error(f"Create station error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
