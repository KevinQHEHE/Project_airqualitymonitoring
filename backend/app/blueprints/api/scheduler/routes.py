"""
Scheduler monitoring API routes.

Purpose: Provide API endpoints to monitor background scheduler status.
Key endpoints:
- GET /status: Get scheduler status and job information
- POST /trigger: Manually trigger a station reading job (admin)

Security: Admin authentication required for trigger endpoint
"""
from flask import Blueprint, jsonify, request
from backend.app.extensions import limiter

scheduler_bp = Blueprint('scheduler', __name__)


@scheduler_bp.route('/status', methods=['GET'])
@limiter.limit("10 per minute")
def get_scheduler_status():
    """
    Get station reading scheduler status.
    
    Returns:
        JSON response with scheduler status and job information
    """
    try:
        from ingest.streaming import get_scheduler
        
        scheduler = get_scheduler()
        if not scheduler:
            return jsonify({
                'status': 'not_initialized',
                'message': 'Station reading scheduler not initialized'
            }), 503
        
        status = scheduler.get_status()
        return jsonify({
            'status': 'ok',
            'scheduler': status
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to get scheduler status: {str(e)}'
        }), 500


@scheduler_bp.route('/trigger', methods=['POST'])
@limiter.limit("3 per minute")
def trigger_station_reading():
    """
    Manually trigger a station reading job.
    
    Note: This is intended for admin use and testing.
    In production, consider adding authentication.
    
    Returns:
        JSON response indicating trigger status
    """
    try:
        from ingest.streaming import get_scheduler
        
        scheduler = get_scheduler()
        if not scheduler:
            return jsonify({
                'status': 'error',
                'message': 'Station reading scheduler not initialized'
            }), 503
        
        if not scheduler.is_running:
            return jsonify({
                'status': 'error',
                'message': 'Scheduler is not running'
            }), 503
        
        # Add immediate job
        from datetime import datetime, timezone
        scheduler.scheduler.add_job(
            func=scheduler._run_station_reading_script,
            trigger='date',
            run_date=datetime.now(timezone.utc),
            id=f'manual_trigger_{datetime.now().timestamp()}',
            name='Manual Station Reading Trigger',
            replace_existing=False
        )
        
        return jsonify({
            'status': 'ok',
            'message': 'Station reading job triggered successfully'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to trigger station reading: {str(e)}'
        }), 500


@scheduler_bp.route('/trigger/forecast', methods=['POST'])
@limiter.limit("3 per minute")
def trigger_forecast_ingestion():
    """
    Manually trigger a forecast ingestion job.
    
    Note: This is intended for admin use and testing.
    In production, consider adding authentication.
    
    Returns:
        JSON response indicating trigger status
    """
    try:
        from ingest.streaming import get_scheduler
        
        scheduler = get_scheduler()
        if not scheduler:
            return jsonify({
                'status': 'error',
                'message': 'Scheduler not initialized'
            }), 503
        
        if not scheduler.is_running:
            return jsonify({
                'status': 'error',
                'message': 'Scheduler is not running'
            }), 503
        
        # Add immediate forecast job
        from datetime import datetime, timezone
        scheduler.scheduler.add_job(
            func=scheduler._run_forecast_ingestion_script,
            trigger='date',
            run_date=datetime.now(timezone.utc),
            id=f'manual_forecast_trigger_{datetime.now().timestamp()}',
            name='Manual Forecast Ingestion Trigger',
            replace_existing=False
        )
        
        return jsonify({
            'status': 'ok',
            'message': 'Forecast ingestion job triggered successfully'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to trigger forecast ingestion: {str(e)}'
        }), 500
