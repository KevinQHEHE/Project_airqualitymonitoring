"""Background tasks for monitoring favorite stations and sending alerts.

Runs as a Celery task (scheduled from beat). Implements rate limiting and
graceful error handling when reading data or sending emails.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from flask import current_app, render_template
from flask_mail import Message
from bson import ObjectId

from backend.app.repositories import users_repo, readings_repo, stations_repo
from backend.app.extensions import mail
from backend.app import db as db_module
# alert_history is deprecated for monitoring flows; we now record delivery
# events in `notification_logs` exclusively. The helper _log_notification_entry
# is used below.

logger = logging.getLogger(__name__)


def _get_users_with_notifications() -> List[Dict[str, Any]]:
    """Return users who have notification preferences enabled and have favorites OR active subscriptions."""
    # Simple query: users where notifications.enabled == true AND have favorites OR subscriptions
    db = db_module.get_db()
    
    # Get users with favorite stations (legacy)
    cursor_favorites = db.users.find({
        'preferences.notifications.enabled': True,
        'preferences.favoriteStations': {'$exists': True, '$ne': []},
        '$or': [
            {'status': 'active'},
            {'status': {'$exists': False}}
        ]
    })
    users_with_favorites = list(cursor_favorites)
    
    # Get users with active subscriptions (new)
    subscriptions = list(db.alert_subscriptions.find({'status': 'active'}))
    user_ids_with_subs = list(set(sub['user_id'] for sub in subscriptions))
    
    if user_ids_with_subs:
        cursor_subscriptions = db.users.find({
            '_id': {'$in': user_ids_with_subs},
            '$or': [
                {'status': 'active'},
                {'status': {'$exists': False}}
            ]
        })
        users_with_subscriptions = list(cursor_subscriptions)
    else:
        users_with_subscriptions = []
    
    # Combine and deduplicate by _id
    all_users = {}
    for user in users_with_favorites + users_with_subscriptions:
        all_users[str(user['_id'])] = user
        
    return list(all_users.values())


def _latest_aqi_for_station(station_id: any) -> Optional[int]:
    try:
        # Try numeric lookup first when possible (readings may store station_id as int)
        query_ids = []
        try:
            query_ids.append(int(station_id))
        except Exception:
            pass
        # Always include string form as fallback
        query_ids.append(str(station_id))

        # Try each form until we find readings
        for sid in query_ids:
            readings = readings_repo.find_latest_by_station(sid, limit=1)
            if readings:
                return readings[0].get('aqi')
        return None
    except Exception as exc:
        logger.exception('Failed to load latest reading for station %s: %s', station_id, exc)
        return None


def _sent_recently(user_id: ObjectId, station_id: any, days: int = 1) -> bool:
    db = db_module.get_db()
    window = datetime.now(timezone.utc) - timedelta(days=days)
    # Normalize station_id to int when possible to match newer schema
    q_station = None
    try:
        q_station = int(station_id)
    except Exception:
        q_station = str(station_id)

    # Use notification_logs as the single source of truth for delivery history.
    # Map 'sent' -> notification_logs.status 'delivered'
    count = db.notification_logs.count_documents({
        'user_id': user_id,
        'station_id': q_station,
        'sentAt': {'$gte': window},
        'status': 'delivered'
    })
    return count > 0


def _send_alert_email(user: Dict[str, Any], station: Dict[str, Any], aqi: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Send an alert email.

    Returns a tuple: (sent: bool, message_id: Optional[str], response: Optional[Dict]).
    The `response` is provider-specific metadata when available. This function
    never raises; it logs exceptions and returns a failure tuple on error.
    """
    recipient = user.get('email')
    if not recipient:
        return False, None, {'error': 'no_recipient'}
    try:
        subject = f"Air quality alert: {station.get('city', {}).get('name') or station.get('station_id')} - AQI {aqi}"
        body_html = render_template('email/location_alert.html', user=user, station=station, aqi=aqi)
        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or 'no-reply@example.com'
        msg = Message(subject=subject, html=body_html, recipients=[recipient], sender=sender)
        mail.send(msg)

        # Best-effort: try to extract a message id or provider hint from the
        # Message object. Flask-Mail doesn't guarantee provider metadata, so
        # fall back to None when unavailable.
        message_id = None
        try:
            message_id = getattr(msg, 'message_id', None) or getattr(msg, 'msg_id', None)
            if not message_id:
                extra = getattr(msg, 'extra_headers', None) or {}
                message_id = extra.get('Message-ID') or extra.get('Message-Id')
        except Exception:
            message_id = None

        # Return a minimal provider response for auditing. If a real mail
        # provider client is used later (SES, SendGrid, etc.), replace this
        # with provider response data.
        response = {'provider': 'smtp'}
        return True, message_id, response
    except Exception:
        logger.exception('Failed to send alert email to %s for station %s', recipient, station.get('station_id'))
        return False, None, {'error': 'send_exception'}


def _log_notification_entry(*, subscription_id: Optional[Any], user_id: Any, station_id: any, status: str, details: Optional[Dict[str, Any]] = None, message_id: Optional[str] = None, attempts: int = 1) -> None:
    """Write a delivery log to `notification_logs` collection.

    Maps internal monitor `status` values to the validator enum values.
    This function should never raise; it logs exceptions.
    """
    # Map internal status -> validator status
    mapping = {
        'sent': 'delivered',
        'failed': 'failed',
        'skipped': 'deferred',
    }
    mapped_status = mapping.get(status, 'failed')
    now = datetime.now(timezone.utc)
    db = db_module.get_db()
    # Normalize station_id to int when possible to match collection validator
    try:
        stored_station_id = int(station_id)
    except Exception:
        stored_station_id = station_id

    doc = {
        'subscription_id': subscription_id if subscription_id is not None else None,
        'user_id': user_id,
        'station_id': stored_station_id,
        'sentAt': now,
        'status': mapped_status,
        'attempts': int(attempts),
        'response': details or {},
        'message_id': message_id or None,
    }
    try:
        db.notification_logs.insert_one(doc)
    except Exception:
        logger.exception('Failed to insert notification_logs entry for user %s station %s', user_id, station_id)


def monitor_favorite_stations():
    """Main monitoring loop. Intended to be called by a scheduled Celery task.

    Behavior:
    - For each user with notifications enabled, iterate favorite stations
    - Compare latest AQI to user's threshold (preferences.notifications.threshold or 100)
    - Enforce rate limiting: 1 alert per station per day per user
    - Send email and record alert_history
    - Handle API/database errors gracefully and continue
    """
    users = _get_users_with_notifications()
    logger.debug('monitor_favorite_stations: found %d users with notifications', len(users))
    if not users:
        logger.debug('No users with notifications enabled found')
        return

    db = db_module.get_db()
    for user in users:
        try:
            logger.debug('Processing user: email=%s id=%s', user.get('email'), user.get('_id'))
            user_id = user.get('_id')
            
            # Get user's active subscriptions
            subscriptions = list(db.alert_subscriptions.find({
                'user_id': user_id,
                'status': 'active'
            }))
            
            # Process subscriptions first (new system)
            for sub in subscriptions:
                station_id = sub['station_id']
                threshold = sub.get('alert_threshold', 100)
                subscription_id = sub['_id']
                
                logger.debug('Checking subscription %s for user %s: station=%s threshold=%s', 
                            subscription_id, user.get('email'), station_id, threshold)
                
                current_aqi = _latest_aqi_for_station(station_id)
                logger.debug('Latest AQI for station %s = %s', station_id, current_aqi)
                
                if current_aqi is None:
                    logger.debug('No latest reading for station %s — recording skipped (no_data)', station_id)
                    try:
                        _log_notification_entry(subscription_id=subscription_id, user_id=user_id, 
                                               station_id=station_id, status='skipped', 
                                               details={'reason': 'no_data', 'aqi': -1}, attempts=0)
                    except Exception:
                        logger.exception('Failed to log notification_logs entry for no_data for user %s station %s', user_id, station_id)
                    continue
                    
                if current_aqi >= threshold:
                    logger.debug('Station %s AQI %s >= threshold %s for subscription %s — evaluating rate limit', 
                                station_id, current_aqi, threshold, subscription_id)
                    
                    if _sent_recently(user_id, station_id, days=1):
                        logger.debug('Rate limited: user %s already sent alert for station %s in last 24h', user.get('email'), station_id)
                        try:
                            _log_notification_entry(subscription_id=subscription_id, user_id=user_id, 
                                                   station_id=station_id, status='skipped', 
                                                   details={'reason': 'rate_limited', 'aqi': current_aqi}, attempts=0)
                        except Exception:
                            logger.exception('Failed to log notification_logs entry for rate_limited for user %s station %s', user_id, station_id)
                        continue
                        
                    # Get station info for email
                    station = stations_repo.find_by_station_id(station_id)
                    if not station:
                        station = {'station_id': station_id, 'name': f'Station {station_id}'}
                    
                    logger.debug('Sending alert email to %s for station %s (AQI=%s)', user.get('email'), station_id, current_aqi)
                    sent, message_id, response = _send_alert_email(user, station, current_aqi)
                    status = 'sent' if sent else 'failed'
                    logger.debug('Email send result for user %s station %s: %s (message_id=%s)', user.get('email'), station_id, status, message_id)
                    
                    try:
                        _log_notification_entry(subscription_id=subscription_id, user_id=user_id, 
                                               station_id=station_id, status=status, 
                                               details={**(response or {}), 'aqi': current_aqi}, 
                                               message_id=message_id, attempts=1)
                    except Exception:
                        logger.exception('Failed to log notification_logs entry for user %s station %s', user_id, station_id)
                        
                else:
                    logger.debug('Station %s AQI %s below threshold %s for subscription %s — no action', 
                                station_id, current_aqi, threshold, subscription_id)
            
            # Process legacy favorite stations (if no subscriptions or as fallback)
            if not subscriptions:
                prefs = user.get('preferences') or {}
                notif = prefs.get('notifications') or {}
                threshold = int(notif.get('threshold', 100))
                favorite_ids = prefs.get('favoriteStations') or []
                
                logger.debug('User %s preferences: threshold=%s favorites=%s', user.get('email'), threshold, favorite_ids)
                if not favorite_ids:
                    logger.debug('User %s has no favorite stations or subscriptions, skipping', user.get('email'))
                    continue

                stations = stations_repo.find_by_station_ids(favorite_ids)
                if not stations:
                    logger.debug('No station documents resolved for favorites %s for user %s', favorite_ids, user.get('email'))
                    continue
                logger.debug('Resolved %d stations for user %s', len(stations), user.get('email'))

                
                # Process legacy favorites stations
                for station in stations:
                    station_id = station.get('station_id') or str(station.get('_id'))
                    logger.debug('Checking legacy favorite station %s for user %s', station_id, user.get('email'))
                    
                    current_aqi = _latest_aqi_for_station(station_id)
                    logger.debug('Latest AQI for station %s = %s', station_id, current_aqi)
                    
                    if current_aqi is None:
                        logger.debug('No latest reading for station %s — recording skipped (no_data)', station_id)
                        try:
                            _log_notification_entry(subscription_id=None, user_id=user.get('_id'), 
                                                   station_id=station_id, status='skipped', 
                                                   details={'reason': 'no_data', 'aqi': -1}, attempts=0)
                        except Exception:
                            logger.exception('Failed to log notification_logs entry for no_data for user %s station %s', user.get('_id'), station_id)
                        continue

                    if current_aqi >= threshold:
                        logger.debug('Station %s AQI %s >= threshold %s for user %s — evaluating rate limit', 
                                    station_id, current_aqi, threshold, user.get('email'))
                        
                        if _sent_recently(user.get('_id'), station_id, days=1):
                            logger.debug('Rate limited: user %s already sent alert for station %s in last 24h', user.get('email'), station_id)
                            try:
                                _log_notification_entry(subscription_id=None, user_id=user.get('_id'), 
                                                       station_id=station_id, status='skipped', 
                                                       details={'reason': 'rate_limited', 'aqi': current_aqi}, attempts=0)
                            except Exception:
                                logger.exception('Failed to log notification_logs entry for rate_limited for user %s station %s', user.get('_id'), station_id)
                            continue

                        logger.debug('Sending alert email to %s for station %s (AQI=%s)', user.get('email'), station_id, current_aqi)
                        sent, message_id, response = _send_alert_email(user, station, current_aqi)
                        status = 'sent' if sent else 'failed'
                        logger.debug('Email send result for user %s station %s: %s (message_id=%s)', user.get('email'), station_id, status, message_id)
                        
                        try:
                            _log_notification_entry(subscription_id=None, user_id=user.get('_id'), 
                                                   station_id=station_id, status=status, 
                                                   details={**(response or {}), 'aqi': current_aqi}, 
                                                   message_id=message_id, attempts=1)
                        except Exception:
                            logger.exception('Failed to log notification_logs entry for user %s station %s', user.get('_id'), station_id)
                    else:
                        logger.debug('Station %s AQI %s below threshold %s for user %s — no action', 
                                    station_id, current_aqi, threshold, user.get('email'))

        except Exception:
            logger.exception('Error processing notifications for user %s', user.get('_id'))
