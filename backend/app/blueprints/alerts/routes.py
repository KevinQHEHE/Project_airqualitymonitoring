"""Alert subscription and management endpoints."""
from flask import Blueprint

alerts_bp = Blueprint('alerts', __name__)

@alerts_bp.route('/', methods=['GET'])
def get_alerts():
    """Get user alerts."""
    return {"message": "Get alerts endpoint - to be implemented"}
