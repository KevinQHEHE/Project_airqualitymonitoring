"""Background tasks for monitoring user alert subscriptions and sending alerts.

Runs as a Celery task (scheduled from beat). Implements rate limiting and
graceful error handling when reading data or sending emails. This module
no longer uses the legacy `preferences.favoriteStations` flow and instead
relies solely on the `alert_subscriptions` collection for user alerts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from flask import current_app, render_template
from flask_mail import Message
from bson import ObjectId
import json
import os
from pathlib import Path

from backend.app.repositories import users_repo, readings_repo, stations_repo
from backend.app.extensions import mail
from backend.app import db as db_module

logger = logging.getLogger(__name__)


def _to_int_or_none(val) -> Optional[int]:
    """Safely convert common AQI/threshold representations to int.

    Handles ints, floats, numeric strings, and nested dicts like {'v': ...}.
    Returns None when conversion is not possible.
    """
    if val is None:
        return None
    try:
        # nested object (e.g. {'v': 12})
        if isinstance(val, dict):
            # try common keys
            for k in ('v', 'value', 'aqi'):
                if k in val:
                    return _to_int_or_none(val.get(k))
            return None
        if isinstance(val, (int,)):
            return int(val)
        if isinstance(val, float):
            return int(val)
        if isinstance(val, str):
            s = val.strip()
            if s == '':
                return None
            try:
                return int(s)
            except Exception:
                try:
                    return int(float(s))
                except Exception:
                    return None
        # last resort
        return int(val)
    except Exception:
        return None


def _get_users_with_notifications() -> List[Dict[str, Any]]:
    """
    Return users who have active alert subscriptions.
    """
    db = db_module.get_db()

    # Load active subscriptions and collect user ids
    subscriptions = list(db.alert_subscriptions.find({'status': 'active'}))
    if not subscriptions:
        return []

    user_ids_with_subs = list({sub['user_id'] for sub in subscriptions})

    # Load users for those ids (keep same status filtering as before)
    cursor = db.users.find({
        '_id': {'$in': user_ids_with_subs},
        '$or': [
            {'status': 'active'},
            {'status': {'$exists': False}}
        ]
    })
    return list(cursor)


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
                aqi_raw = readings[0].get('aqi')
                aqi_val = _to_int_or_none(aqi_raw)
                if aqi_val is None:
                    logger.debug('Latest AQI for station %s could not be parsed to int: %r', station_id, aqi_raw)
                return aqi_val
        return None
    except Exception as exc:
        logger.exception('Failed to load latest reading for station %s: %s', station_id, exc)
        return None


def _sent_recently(user_id: ObjectId, station_id: any, days: int = 1) -> bool:
    """Return True if the user has reached the send limit for this station.

    New behavior:
    - The send window is configured via `ALERT_RATE_WINDOW_HOURS` (env) in hours
      and defaults to 24 hours. For backward compatibility the `days` parameter
      is accepted but overridden by the env var if present.
    - Maximum sends allowed in the window is configured via
      `ALERT_MAX_SENDS_PER_STATION` (env) and defaults to 5.
    """
    db = db_module.get_db()

    # Window: prefer env var ALERT_RATE_WINDOW_HOURS (hours); fall back to days
    try:
        window_hours = int(os.environ.get('ALERT_RATE_WINDOW_HOURS', None))
    except Exception:
        window_hours = None

    if window_hours is None:
        # fall back to provided days parameter
        window = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        window = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # Normalize station_id to int when possible to match newer schema
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

    # Configurable max sends per window (default 2)
    try:
        max_sends = int(os.environ.get('ALERT_MAX_SENDS_PER_STATION', '2'))
    except Exception:
        max_sends = 2

    return count >= max_sends


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
        # Prefer an explicit station name, then the city name, then station id
        station_label = station.get('name') or station.get('city', {}).get('name') or station.get('station_id')
        subject = f"Air quality alert: {station_label} - AQI {aqi}"

        body_html = render_template('email/location_alert.html', user=user, station=station, aqi=aqi)
        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or 'no-reply@example.com'
        msg = Message(subject=subject, html=body_html, recipients=[recipient], sender=sender)
        mail.send(msg)

        # Log success so server logs show that an email was attempted/sent
        try:
            logger.info('Alert email sent to %s for station %s', recipient, station.get('station_id'))
        except Exception:
            pass

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
    except Exception as e:
        # Log exception message explicitly for easier debugging of SMTP issues
        logger.exception('Failed to send alert email to %s for station %s: %s', recipient, station.get('station_id'), str(e))
        return False, None, {'error': 'send_exception', 'reason': str(e)}


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
        # Buffer the notification log to a local JSONL file so it can be replayed
        try:
            # Determine a safe pending file path inside repo data_results directory
            repo_root = Path(__file__).resolve().parents[3]
            pending_dir = repo_root / 'data_results'
            pending_dir.mkdir(parents=True, exist_ok=True)
            pending_path = pending_dir / 'pending_notification_logs.jsonl'

            # Ensure serializable
            safe_doc = {}
            for k, v in doc.items():
                try:
                    # ObjectId -> str, datetimes -> isoformat
                    if isinstance(v, ObjectId):
                        safe_doc[k] = str(v)
                    elif hasattr(v, 'isoformat'):
                        safe_doc[k] = v.isoformat()
                    else:
                        json.dumps(v)  # test serializable
                        safe_doc[k] = v
                except Exception:
                    safe_doc[k] = str(v)

            with pending_path.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(safe_doc, ensure_ascii=False) + '\n')

            logger.info('Buffered notification_logs entry to %s', str(pending_path))
        except Exception:
            logger.exception('Failed to buffer notification_logs entry to local file')


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
                # Normalize threshold to int in case it gets stored as string
                try:
                    threshold = int(sub.get('alert_threshold', 100))
                except Exception:
                    threshold = 100
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
                    
                if current_aqi is not None and current_aqi >= threshold:
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
                        
                    # Get station info for email: prefer integer matching, fall back to string id
                    station = None
                    try:
                        station = stations_repo.find_by_station_id(int(station_id))
                    except Exception:
                        station = None
                    if not station:
                        try:
                            station = stations_repo.find_by_station_id(str(station_id))
                        except Exception:
                            station = None
                    if not station:
                        station = {'station_id': station_id, 'name': f'Station {station_id}'}

                    # If the subscription carries a client-provided nickname, prefer it
                    try:
                        nickname = sub.get('metadata', {}).get('nickname')
                    except Exception:
                        nickname = None
                    if nickname:
                        try:
                            station['name'] = nickname
                        except Exception:
                            station = {**station, 'name': nickname}
                    
                    logger.debug('Sending alert email to %s for station %s (AQI=%s)', user.get('email'), station_id, current_aqi)
                    sent, message_id, response = _send_alert_email(user, station, current_aqi)
                    status = 'sent' if sent else 'failed'
                    logger.debug('Email send result for user %s station %s: %s (message_id=%s)', user.get('email'), station_id, status, message_id)
                    
                    try:
                        _log_notification_entry(subscription_id=subscription_id, user_id=user_id, 
                                               station_id=station_id, status=status, 
                                               details={**(response or {}), 'aqi': current_aqi}, 
                                               message_id=message_id, attempts=1)
                        # If sent, update subscription.last_triggered to avoid duplicate sends
                        if sent:
                            try:
                                db.alert_subscriptions.update_one({'_id': subscription_id}, {'$set': {'last_triggered': datetime.now(timezone.utc)}})
                            except Exception:
                                logger.exception('Failed to update subscription.last_triggered for subscription %s', subscription_id)
                    except Exception:
                        logger.exception('Failed to log notification_logs entry for user %s station %s', user_id, station_id)
                        
                else:
                    logger.debug('Station %s AQI %s below threshold %s for subscription %s — no action', 
                                station_id, current_aqi, threshold, subscription_id)
            
            
            if not subscriptions:
                logger.debug('User %s has no active alert_subscriptions; skipping', user.get('email'))
                continue

        except Exception:
            logger.exception('Error processing notifications for user %s', user.get('_id'))


def monitor_user_notifications(user: Dict[str, Any]) -> None:
    """Run the alert checks for a single user.

    This performs the same checks as the scheduled monitor but only for the
    provided user document. It is safe to call from a background thread
    (won't raise) and will log exceptions.
    """
    try:
        if not user:
            return
        logger.debug('monitor_user_notifications: processing user %s', user.get('email'))
        db = db_module.get_db()
        user_id = user.get('_id')

        # Check active subscriptions first (new system)
        subscriptions = list(db.alert_subscriptions.find({'user_id': user_id, 'status': 'active'}))
        for sub in subscriptions:
            station_id = sub['station_id']
            threshold = sub.get('alert_threshold', 100)
            subscription_id = sub['_id']

            current_aqi = _latest_aqi_for_station(station_id)
            if current_aqi is None:
                try:
                    _log_notification_entry(subscription_id=subscription_id, user_id=user_id,
                                            station_id=station_id, status='skipped',
                                            details={'reason': 'no_data', 'aqi': -1}, attempts=0)
                except Exception:
                    logger.exception('Failed to log no_data for user %s station %s', user_id, station_id)
                continue

            if current_aqi is not None and current_aqi >= threshold:
                if _sent_recently(user_id, station_id, days=1):
                    try:
                        _log_notification_entry(subscription_id=subscription_id, user_id=user_id,
                                                station_id=station_id, status='skipped',
                                                details={'reason': 'rate_limited', 'aqi': current_aqi}, attempts=0)
                    except Exception:
                        logger.exception('Failed to log rate_limited for user %s station %s', user_id, station_id)
                    continue

                station = None
                try:
                    station = stations_repo.find_by_station_id(int(station_id))
                except Exception:
                    station = None
                if not station:
                    try:
                        station = stations_repo.find_by_station_id(str(station_id))
                    except Exception:
                        station = None
                if not station:
                    station = {'station_id': station_id, 'name': f'Station {station_id}'}

                # Prefer subscription metadata.nickname when present
                try:
                    nickname = sub.get('metadata', {}).get('nickname')
                except Exception:
                    nickname = None
                if nickname:
                    try:
                        station['name'] = nickname
                    except Exception:
                        station = {**station, 'name': nickname}

                sent, message_id, response = _send_alert_email(user, station, current_aqi)
                status = 'sent' if sent else 'failed'
                try:
                    _log_notification_entry(subscription_id=subscription_id, user_id=user_id,
                                            station_id=station_id, status=status,
                                            details={**(response or {}), 'aqi': current_aqi},
                                            message_id=message_id, attempts=1)
                    if sent:
                        try:
                            db.alert_subscriptions.update_one({'_id': subscription_id}, {'$set': {'last_triggered': datetime.now(timezone.utc)}})
                        except Exception:
                            logger.exception('Failed to update subscription.last_triggered for subscription %s', subscription_id)
                except Exception:
                    logger.exception('Failed to log notification for user %s station %s', user_id, station_id)

        if not subscriptions:
            logger.debug('monitor_user_notifications: user %s has no active subscriptions; nothing to do', user.get('email'))
            return
    except Exception:
        logger.exception('monitor_user_notifications: unexpected error for user %s', user.get('_id') if user else None)
