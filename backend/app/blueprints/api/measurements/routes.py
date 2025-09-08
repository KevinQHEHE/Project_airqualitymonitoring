"""Measurements blueprint for air quality readings data."""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

measurements_bp = Blueprint('measurements', __name__)


@measurements_bp.route('/', methods=['GET'])
def get_measurements():
    """Get air quality measurements.
    
    Query parameters:
    - station_id: Filter by station ID
    - start_time: Start time (ISO format)
    - end_time: End time (ISO format)
    - pollutant: Filter by pollutant type (pm25, pm10, o3, no2, so2, co)
    - page: Page number (default: 1)
    - page_size: Number of items per page (default: 100)
    
    Returns:
        JSON: List of measurements with pagination info
    """
    try:
        station_id = request.args.get('station_id')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        pollutant = request.args.get('pollutant')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 100))
        
        # Validate date formats if provided
        if start_time:
            try:
                datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({"error": "Invalid start_time format. Use ISO format."}), 400
        
        if end_time:
            try:
                datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({"error": "Invalid end_time format. Use ISO format."}), 400
        
        # TODO: Implement measurement retrieval from MongoDB
        return jsonify({
            "measurements": [],
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
        logger.error(f"Get measurements error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@measurements_bp.route('/', methods=['POST'])
def create_measurement():
    """Create a new air quality measurement.
    
    Expected JSON body:
    {
        "station_id": 123,
        "timestamp": "2024-01-01T12:00:00Z",
        "pollutants": {
            "pm25": 25.5,
            "pm10": 35.2,
            "o3": 45.1
        },
        "aqi": 85,
        "temperature": 22.5,
        "humidity": 65.2
    }
    
    Returns:
        JSON: Created measurement info or error message
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        required_fields = ['station_id', 'timestamp', 'pollutants']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Validate timestamp format
        try:
            datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        except ValueError:
            return jsonify({"error": "Invalid timestamp format. Use ISO format."}), 400
        
        # TODO: Implement measurement creation in MongoDB
        return jsonify({
            "message": "Measurement created successfully",
            "measurement": data
        }), 201
    
    except Exception as e:
        logger.error(f"Create measurement error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@measurements_bp.route('/latest', methods=['GET'])
def get_latest_measurements():
    """Get latest measurements for all or specific stations.
    
    Query parameters:
    - station_id: Filter by station ID (optional)
    
    Returns:
        JSON: Latest measurements
    """
    try:
        station_id = request.args.get('station_id')
        
        # TODO: Implement latest measurements retrieval from MongoDB
        return jsonify({
            "latest_measurements": []
        }), 200
    
    except Exception as e:
        logger.error(f"Get latest measurements error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
