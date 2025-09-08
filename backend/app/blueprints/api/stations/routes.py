"""Stations blueprint for managing air quality monitoring stations."""
from flask import Blueprint, request, jsonify
import logging

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
        
        # TODO: Implement station retrieval from MongoDB
        # For now, return placeholder data
        return jsonify({
            "stations": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": 0,
                "pages": 0
            }
        }), 200
    
    except ValueError:
        return jsonify({"error": "Invalid page or page_size parameter"}), 400
    except Exception as e:
        logger.error(f"Get stations error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@stations_bp.route('/<int:station_id>', methods=['GET'])
def get_station(station_id):
    """Get details for a specific station.
    
    Args:
        station_id: Station ID
        
    Returns:
        JSON: Station details or error message
    """
    try:
        # TODO: Implement station retrieval by ID from MongoDB
        return jsonify({
            "station_id": station_id,
            "message": "Station not found"
        }), 404
    
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
