"""Simple forecasting using Moving Average and Linear Regression."""
from flask import Blueprint

forecasts_bp = Blueprint('forecasts', __name__)

@forecasts_bp.route('/', methods=['GET'])
def get_forecasts():
    """Get air quality forecasts."""
    return {"message": "Get forecasts endpoint - to be implemented"}
