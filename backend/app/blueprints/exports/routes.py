"""CSV and PDF report export functionality."""
from flask import Blueprint

exports_bp = Blueprint('exports', __name__)

@exports_bp.route('/csv', methods=['GET'])
def export_csv():
    """Export data as CSV."""
    return {"message": "Export CSV endpoint - to be implemented"}
