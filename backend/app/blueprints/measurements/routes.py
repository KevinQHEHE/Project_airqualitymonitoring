"""Measurement data queries and CSV import functionality."""
from flask import Blueprint

measurements_bp = Blueprint('measurements', __name__)

@measurements_bp.route('/', methods=['GET'])
def get_measurements():
    """Get air quality measurements."""
    return {"message": "Get measurements endpoint - to be implemented"}
