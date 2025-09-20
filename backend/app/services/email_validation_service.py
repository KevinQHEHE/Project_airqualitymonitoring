"""Email validation service.

Provides high-level email validation with:
- regex format check
- MX DNS lookup
- disposable domain check (from config file)
- optional external API validation (configurable)
- caching of results in MongoDB with 24h TTL

This module is intentionally small and dependency-free (uses `dnspython` if available
for MX lookup; otherwise falls back to socket lookup). It reads `config/disposable_domains.txt`
from repository root to check disposable domains.
"""
from __future__ import annotations

import logging
import os
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import requests

from flask import current_app

from backend.app import db as db_module

logger = logging.getLogger(__name__)

try:
    import dns.resolver  # type: ignore
except Exception:
    dns = None


DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


@dataclass
class ValidationResult:
    status: str  # 'valid', 'invalid', 'risky', 'unknown'
    reason: Optional[str] = None
    details: Optional[dict] = None


class EmailValidationService:
    EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def __init__(self, disposable_file: Optional[str] = None):
        self.disposable_file = disposable_file or os.path.join(os.getcwd(), 'config', 'disposable_domains.txt')
        self.disposable_domains = self._load_disposable_domains()

    def _load_disposable_domains(self) -> set[str]:
        domains = set()
        try:
            if os.path.exists(self.disposable_file):
                with open(self.disposable_file, 'r', encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        domains.add(line.lower())
        except Exception as e:
            logger.warning(f"Failed to load disposable domains from {self.disposable_file}: {e}")
        return domains

    def _cache_collection(self):
        db = db_module.get_db()
        return db.email_validation_cache

    def _get_cached(self, email: str) -> Optional[ValidationResult]:
        try:
            coll = self._cache_collection()
            doc = coll.find_one({'email': email.lower()})
            if not doc:
                return None
            # Return as ValidationResult
            return ValidationResult(status=doc.get('status', 'unknown'), reason=doc.get('reason'), details=doc.get('details'))
        except Exception as e:
            logger.debug(f"Cache read failed: {e}")
            return None

    def _set_cached(self, email: str, result: ValidationResult, ttl: int = DEFAULT_CACHE_TTL_SECONDS):
        try:
            coll = self._cache_collection()
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            doc = {
                'email': email.lower(),
                'status': result.status,
                'reason': result.reason,
                'details': result.details or {},
                'createdAt': datetime.now(timezone.utc),
                'expiresAt': expires_at,
            }
            coll.replace_one({'email': email.lower()}, doc, upsert=True)
        except Exception as e:
            logger.debug(f"Cache write failed: {e}")

    def _is_disposable(self, domain: str) -> bool:
        return domain.lower() in self.disposable_domains

    def _mx_lookup(self, domain: str) -> bool:
        """Return True if MX records exist for domain. Graceful fallback if resolver not available."""
        try:
            if dns:
                answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
                return len(answers) > 0
            # Fallback: try resolving domain to an A record
            socket.gethostbyname(domain)
            return True
        except Exception:
            return False

    def _call_external_api(self, email: str) -> tuple[Optional[dict], bool]:
        """Call configured external email validation API. Supports Abstract API as example.

        Configuration in Flask config:
        EMAIL_VALIDATION: {
            'provider': 'abstract',
            'api_key': 'xxx',
            'url': 'https://emailvalidation.abstractapi.com/v1/'
        }
        """
        cfg = current_app.config.get('EMAIL_VALIDATION') or {}
        provider = (cfg.get('provider') or '').lower()
        # attempted indicates whether a provider was configured and we attempted a call
        if not provider:
            return None, False
        try:
            # Abstract API
            if provider == 'abstract':
                api_key = cfg.get('api_key')
                if not api_key:
                    # provider configured but missing key -> treated as attempted
                    return None, True
                url = cfg.get('url') or 'https://emailvalidation.abstractapi.com/v1/'
                resp = requests.get(url, params={'api_key': api_key, 'email': email}, timeout=3)
                if resp.status_code == 200:
                    return resp.json(), True
                else:
                    # Log non-200 responses without exposing the API key
                    body = resp.text or ''
                    if len(body) > 1000:
                        body = body[:1000] + '...[truncated]'
                    logger.warning("External provider 'abstract' returned status %s: %s", resp.status_code, body)
                    return None, True

            # an EmailJS-like generic provider) by setting `EMAIL_VALIDATION` in Flask config.

            # EmailJS-like or generic provider (user supplies URL and optional headers)
            if provider in ('emailjs', 'email_js', 'email-js'):
                url = cfg.get('url')
                if not url:
                    return None, True
                method = (cfg.get('method') or 'GET').upper()
                headers = cfg.get('headers') or {}
                params = cfg.get('params') or {}
                # allow using 'email' param placeholder
                if method == 'GET':
                    # merge provided params with email
                    params = {**params, 'email': email}
                    resp = requests.get(url, params=params, headers=headers, timeout=3)
                else:
                    payload = {**(cfg.get('body') or {}), 'email': email}
                    resp = requests.post(url, json=payload, headers=headers, timeout=3)
                # evaluate response
                if resp.status_code == 200:
                    return resp.json(), True
                else:
                    body = resp.text or ''
                    if len(body) > 1000:
                        body = body[:1000] + '...[truncated]'
                    logger.warning("External provider '%s' returned status %s: %s", provider, resp.status_code, body)
                    return None, True

        except requests.RequestException as e:
            logger.warning(f"External email API request failed: {e}")
            return None, True
        return None, False

    def _interpret_api_response(self, api_resp: Any) -> tuple[str, Optional[str], dict]:
        """Interpret common external provider responses and map to (status, reason, details).

        Returns tuple (status, reason, details).
        status in {'valid','invalid','risky','unknown'}
        """
        details = {}
        try:
            if not api_resp:
                return 'unknown', 'no_response', {}

            # If provider returns wrapper containing 'data', unwrap
            if isinstance(api_resp, dict) and 'data' in api_resp and isinstance(api_resp['data'], dict):
                payload = api_resp['data']
            else:
                payload = api_resp

            details['raw'] = payload

            # Common checks across providers
            # 1) deliverability-like fields
            for key in ('deliverability', 'result', 'status', 'deliverable'):
                if key in payload:
                    val = payload.get(key)
                    if isinstance(val, str):
                        v = val.lower()
                        if 'deliver' in v or 'ok' in v or 'valid' in v:
                            return 'valid', f'api_{key}_deliverable', details
                        if 'undeliver' in v or 'undel' in v or 'invalid' in v:
                            return 'invalid', f'api_{key}_undeliverable', details
                        if 'risk' in v or 'risky' in v or 'unknown' in v:
                            return 'risky', f'api_{key}_risky', details
                    elif isinstance(val, bool):
                        if val:
                            return 'valid', f'api_{key}_true', details
                        else:
                            return 'invalid', f'api_{key}_false', details

            # 2) specific known provider fields
            # Hunter: payload.get('result') often is 'deliverable'/'undeliverable'/'risky'
            if isinstance(payload, dict) and 'result' in payload:
                r = str(payload.get('result')).lower()
                if 'deliver' in r:
                    return 'valid', 'api_result_deliverable', details
                if 'undeliver' in r:
                    return 'invalid', 'api_result_undeliverable', details
                if 'risk' in r:
                    return 'risky', 'api_result_risky', details

            # 3) SMTP checks (accept_all, smtp_check)
            if payload.get('smtp_check') is not None:
                smtp_ok = payload.get('smtp_check')
                if smtp_ok:
                    return 'valid', 'api_smtp_check', details
                else:
                    return 'risky', 'api_smtp_failed', details

            # 4) disposable flag
            if payload.get('disposable') is True:
                return 'invalid', 'api_disposable', details

            # fallback to unknown
            return 'unknown', 'api_uninterpretable', details

        except Exception as e:
            logger.debug(f"Failed to interpret API response: {e}")
            return 'unknown', 'interpret_error', {'error': str(e)}

    def validate(self, email: str, strict: str = 'medium') -> ValidationResult:
        """Perform email validation and return ValidationResult.

        strict: one of 'low', 'medium', 'high' affecting how risky results are classified.
        """
        email = (email or '').strip()
        if not email:
            return ValidationResult('invalid', reason='empty')

        # Quick format check
        if not self.EMAIL_RE.match(email):
            return ValidationResult('invalid', reason='format')

        # Check cache first
        cached = self._get_cached(email)
        if cached:
            return cached

        local_result = ValidationResult('unknown')

        try:
            local_result.details = {}
            local_result.details['format_ok'] = True

            local_part, domain = email.rsplit('@', 1)
            domain = domain.lower()

            # Disposable domain check
            if self._is_disposable(domain):
                local_result.status = 'invalid'
                local_result.reason = 'disposable_domain'
                self._set_cached(email, local_result)
                return local_result

            # MX lookup
            has_mx = self._mx_lookup(domain)
            local_result.details['mx'] = bool(has_mx)

            # External API (best-effort)
            api_resp = None
            provider_attempted = False
            try:
                api_resp, provider_attempted = self._call_external_api(email)
            except Exception:
                api_resp = None
                provider_attempted = True

            # Interpret external API response if present
            if api_resp:
                status, reason, details = self._interpret_api_response(api_resp)
                local_result.status = status
                local_result.reason = reason
                local_result.details['api'] = details
            else:
                # Provider was configured but call failed/returned non-200 -> treat as risky or invalid
                if provider_attempted:
                    if strict == 'high':
                        local_result.status = 'invalid'
                        local_result.reason = 'provider_unavailable'
                    else:
                        local_result.status = 'risky'
                        local_result.reason = 'provider_unavailable'
                else:
                    # No provider configured: fallback to MX result
                    if has_mx:
                        local_result.status = 'valid'
                        local_result.reason = 'mx_found'
                    else:
                        # If strict mode is high, treat no MX as invalid
                        if strict == 'high':
                            local_result.status = 'invalid'
                            local_result.reason = 'no_mx'
                        else:
                            local_result.status = 'risky'
                            local_result.reason = 'no_mx'

        except Exception as e:
            logger.exception(f"Email validation internal error for {email}: {e}")
            local_result = ValidationResult('unknown', reason='internal_error')

        # Cache result
        try:
            self._set_cached(email, local_result)
        except Exception:
            pass

        return local_result


def get_default_service() -> EmailValidationService:
    return EmailValidationService()
