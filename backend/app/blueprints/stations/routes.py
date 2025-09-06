"""Station management CRUD operations."""
from flask import Blueprint

stations_bp = Blueprint('stations', __name__)

@stations_bp.route('/', methods=['GET'])
def get_stations():
    """Get all monitoring stations."""
    return {"message": "Get stations endpoint - to be implemented"}

@stations_bp.route('/', methods=['POST'])
def create_station():
    """Create new monitoring station."""
    return {"message": "Create station endpoint - to be implemented"}
