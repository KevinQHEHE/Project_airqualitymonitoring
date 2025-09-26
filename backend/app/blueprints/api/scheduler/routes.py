"""
Scheduler monitoring API routes.

Purpose: Provide API endpoints to monitor background scheduler status.
Key endpoints:
- GET /status: Get scheduler status and job information
- POST /trigger: Manually trigger a station reading job (admin)

Security: Admin authentication required for trigger endpoint
"""
from flask import Blueprint, jsonify, request, current_app
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
        backup_status = None
        try:
            from backup_dtb.scheduler import get_backup_scheduler
            backup_scheduler = get_backup_scheduler()
            if backup_scheduler:
                backup_status = backup_scheduler.get_status()
        except Exception:
            backup_status = None

        response = {
            'status': 'ok',
            'scheduler': status
        }
        if backup_status is not None:
            response['backup_scheduler'] = backup_status
        return jsonify(response)
        
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

@scheduler_bp.route('/trigger/backup', methods=['POST'])
@limiter.limit("3 per minute")
def trigger_backup_run():
    """Manually trigger a database backup run."""
    try:
        from backup_dtb.scheduler import get_backup_scheduler, init_backup_scheduler
    except Exception as exc:  # noqa: BLE001
        return jsonify({
            'status': 'error',
            'message': f'Backup scheduler module unavailable: {exc}'
        }), 500

    payload = request.get_json(silent=True) or {}
    raw_async = payload.get('async', True)
    if isinstance(raw_async, str):
        run_async = raw_async.lower() not in ('false', '0', 'no')
    else:
        run_async = bool(raw_async)

    reason = payload.get('reason') or 'manual_api'

    scheduler = get_backup_scheduler()
    if not scheduler:
        try:
            scheduler = init_backup_scheduler(logger=current_app.logger)
        except Exception as exc:  # noqa: BLE001
            current_app.logger.error('Failed to initialize backup scheduler: %s', exc)
            return jsonify({
                'status': 'error',
                'message': f'Failed to initialize backup scheduler: {exc}'
            }), 500

    if not scheduler:
        return jsonify({
            'status': 'error',
            'message': 'Backup scheduler not available'
        }), 503

    if not scheduler.is_running:
        try:
            scheduler.start()
        except Exception as exc:  # noqa: BLE001
            current_app.logger.error('Failed to start backup scheduler: %s', exc)
            return jsonify({
                'status': 'error',
                'message': f'Failed to start backup scheduler: {exc}'
            }), 500

    started = scheduler.trigger_backup(reason=reason, run_async=run_async)
    if not started:
        return jsonify({
            'status': 'error',
            'message': 'Backup already in progress'
        }), 409

    status = scheduler.get_status()
    response = {
        'status': 'ok',
        'message': 'Backup job started' if run_async else 'Backup job completed',
        'async': run_async,
        'backup_in_progress': scheduler.is_backup_in_progress(),
    }
    if not run_async:
        response['result'] = status.get('last_result', {})
    else:
        response['last_result'] = status.get('last_result', {})

    return jsonify(response), (202 if run_async else 200)

