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
    """Return users who have notification preferences enabled and have favorites."""
    # Simple query: users where preferences.notifications.enabled == true
    db = db_module.get_db()
    # Accept users who have notifications enabled and favorites. Some user
    # documents (older records) may not have an explicit `status` field, so
    # include those as well.
    cursor = db.users.find({
        'preferences.notifications.enabled': True,
        'preferences.favoriteStations': {'$exists': True, '$ne': []},
        '$or': [
            {'status': 'active'},
            {'status': {'$exists': False}}
        ]
    })
    return list(cursor)


def _latest_aqi_for_station(station_id: str) -> Optional[int]:
    try:
        readings = readings_repo.find_latest_by_station(station_id, limit=1)
        if not readings:
            return None
        return readings[0].get('aqi')
    except Exception as exc:
        logger.exception('Failed to load latest reading for station %s: %s', station_id, exc)
        return None


def _sent_recently(user_id: ObjectId, station_id: str, days: int = 1) -> bool:
    db = db_module.get_db()
    window = datetime.now(timezone.utc) - timedelta(days=days)
    # Use notification_logs as the single source of truth for delivery history.
    # Map 'sent' -> notification_logs.status 'delivered'
    count = db.notification_logs.count_documents({
        'user_id': user_id,
        'station_id': station_id,
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


def _log_notification_entry(*, subscription_id: Optional[Any], user_id: Any, station_id: str, status: str, details: Optional[Dict[str, Any]] = None, message_id: Optional[str] = None, attempts: int = 1) -> None:
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
    doc = {
        'subscription_id': subscription_id if subscription_id is not None else None,
        'user_id': user_id,
        'station_id': str(station_id),
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
            prefs = user.get('preferences') or {}
            notif = prefs.get('notifications') or {}
            threshold = int(notif.get('threshold', 100))
            favorite_ids = prefs.get('favoriteStations') or []
            logger.debug('User %s preferences: threshold=%s favorites=%s', user.get('email'), threshold, favorite_ids)
            if not favorite_ids:
                logger.debug('User %s has no favorite stations, skipping', user.get('email'))
                continue

            # Resolve stations as documents. Use repository helper which accepts
            # a mix of numeric _id and station_id strings (more robust than direct _id query).
            stations = stations_repo.find_by_station_ids(favorite_ids)
            if not stations:
                logger.debug('No station documents resolved for favorites %s for user %s', favorite_ids, user.get('email'))
                continue
            logger.debug('Resolved %d stations for user %s', len(stations), user.get('email'))

            for station in stations:
                station_id = station.get('station_id') or str(station.get('_id'))
                logger.debug('Checking station %s for user %s', station_id, user.get('email'))
                # Try to resolve an existing subscription for this user/station
                try:
                    sub_doc = None
                    try:
                        sub_doc = db.alert_subscriptions.find_one({'user_id': user.get('_id'), 'station_id': station_id, 'status': 'active'})
                    except Exception:
                        # Some test harnesses or older DBs may not have the collection; handle gracefully
                        logger.debug('alert_subscriptions lookup failed or missing for user %s station %s', user.get('_id'), station_id)
                        sub_doc = None
                    subscription_id = sub_doc.get('_id') if sub_doc else None
                except Exception:
                    logger.exception('Failed to lookup subscription for user %s station %s', user.get('_id'), station_id)
                    subscription_id = None
                current_aqi = _latest_aqi_for_station(station_id)
                logger.debug('Latest AQI for station %s = %s', station_id, current_aqi)
                if current_aqi is None:
                    # missing data: skip but record for monitoring
                    logger.debug('No latest reading for station %s — recording skipped (no_data)', station_id)
                    # Record as a notification_logs entry (include aqi in details)
                    try:
                        _log_notification_entry(subscription_id=subscription_id, user_id=user.get('_id'), station_id=station_id, status='skipped', details={'reason': 'no_data', 'aqi': -1}, attempts=0)
                    except Exception:
                        logger.exception('Failed to log notification_logs entry for no_data for user %s station %s', user.get('_id'), station_id)
                    continue

                if current_aqi >= threshold:
                    logger.debug('Station %s AQI %s >= threshold %s for user %s — evaluating rate limit', station_id, current_aqi, threshold, user.get('email'))
                    # enforce rate limit
                    if _sent_recently(user.get('_id'), station_id, days=1):
                        logger.debug('Rate limited: user %s already sent alert for station %s in last 24h', user.get('email'), station_id)
                        # Rate limited: write a notification_logs entry with rate_limited reason
                        try:
                            _log_notification_entry(subscription_id=subscription_id, user_id=user.get('_id'), station_id=station_id, status='skipped', details={'reason': 'rate_limited', 'aqi': current_aqi}, attempts=0)
                        except Exception:
                            logger.exception('Failed to log notification_logs entry for rate_limited for user %s station %s', user.get('_id'), station_id)
                        continue

                    logger.debug('Sending alert email to %s for station %s (AQI=%s)', user.get('email'), station_id, current_aqi)
                    sent, message_id, response = _send_alert_email(user, station, current_aqi)
                    status = 'sent' if sent else 'failed'
                    logger.debug('Email send result for user %s station %s: %s (message_id=%s)', user.get('email'), station_id, status, message_id)
                    # Write delivery log into notification_logs (include aqi)
                    try:
                        _log_notification_entry(subscription_id=subscription_id, user_id=user.get('_id'), station_id=station_id, status=status, details={**(response or {}), 'aqi': current_aqi}, message_id=message_id, attempts=1)
                    except Exception:
                        logger.exception('Failed to log notification_logs entry for user %s station %s', user.get('_id'), station_id)
                else:
                    logger.debug('Station %s AQI %s below threshold %s for user %s — no action', station_id, current_aqi, threshold, user.get('email'))

        except Exception:
            logger.exception('Error processing notifications for user %s', user.get('_id'))
