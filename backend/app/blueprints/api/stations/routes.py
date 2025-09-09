"""Stations blueprint for managing air quality monitoring stations."""
from flask import Blueprint, request, jsonify
import logging
from backend.app.repositories import stations_repo

logger = logging.getLogger(__name__)

stations_bp = Blueprint('stations', __name__)


@stations_bp.route('/', methods=['GET'])
def get_stations():
    """Get list of air quality monitoring stations with pagination.
    
    Query parameters:
    - limit: Number of items per page (default: 20, max: 100)
    - offset: Number of items to skip (default: 0)
    - city: Filter by city name
    - country: Filter by country code
    
    Returns:
        JSON: List of stations with pagination info
    """
    try:
        # Parse and validate pagination parameters
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))
        
        # Validate limit bounds
        if limit <= 0:
            return jsonify({"error": "limit must be greater than 0"}), 400
        if limit > 100:
            return jsonify({"error": "limit cannot exceed 100"}), 400
        if offset < 0:
            return jsonify({"error": "offset must be non-negative"}), 400
            
        # Parse filter parameters
        city = request.args.get('city')
        country = request.args.get('country')
        
        # Build filter criteria
        filter_criteria = {}
        if city:
            filter_criteria['city.name'] = {"$regex": city, "$options": "i"}
        if country:
            filter_criteria['country'] = country.upper()
            
        # Get stations with pagination from repository
        stations, total_count = stations_repo.find_with_pagination(
            filter_dict=filter_criteria,
            limit=limit,
            offset=offset
        )
        
        # Convert ObjectId to string for JSON serialization
        for station in stations:
            if '_id' in station:
                station['_id'] = str(station['_id'])
        
        # Calculate pagination metadata
        total_pages = (total_count + limit - 1) // limit
        current_page = (offset // limit) + 1
        
        return jsonify({
            "stations": stations,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total_count,
                "pages": total_pages,
                "current_page": current_page,
                "has_next": offset + limit < total_count,
                "has_prev": offset > 0
            }
        }), 200
        
    except ValueError as e:
        return jsonify({"error": f"Invalid parameter: {str(e)}"}), 400
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
