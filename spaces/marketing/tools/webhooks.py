"""Webhook event emission + signing helpers.

Two halves:
  1. emit_event(kind, payload, ...) -- single canonical entry point for
     emitting lifecycle events to marketing.webhook_events. Send-workers,
     bounce-workers, reply-linkage and unsubscribe routes call this.
  2. sign_payload(secret, body_bytes) -- canonical HMAC-SHA256 signing.
     Both the delivery worker and any test/verify helpers share this.

NEVER emit events that name secrets. Subscription `secret` columns are
truncated to prefix before being included in audit_log; never in the
event payload.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from ..sync import _db


logger = logging.getLogger("marketing.webhooks")


# Known event kinds — mirrored on the SQL CHECK constraint in migration 020.
KNOWN_EVENT_KINDS = frozenset({
    "sent", "open", "click", "bounce",
    "unsubscribe", "reply", "send_failed",
    "campaign_status_change", "subscription_test",
})


# ─── Emission ──────────────────────────────────────────────────────────


def emit_event(kind: str, payload: Dict[str, Any], *,
               campaign_id: Optional[str] = None,
               email: Optional[str] = None) -> Optional[str]:
    """Insert a row into marketing.webhook_events.

    Returns the new event_id (str) on success, or None if the kind is
    unknown / DB is unreachable. NEVER raises -- a failure here MUST NOT
    block the send-worker. Caller logs the error if it cares.
    """
    if kind not in KNOWN_EVENT_KINDS:
        logger.warning("webhook emit refused: unknown event_kind=%r", kind)
        return None
    try:
        sql_kind = _db._sql_literal(kind)
        sql_payload = _db._sql_literal(json.dumps(payload, default=str))
        sql_campaign = (
            f"{_db._sql_literal(campaign_id)}::uuid"
            if campaign_id else "NULL"
        )
        sql_email = _db._sql_literal(email) if email else "NULL"
        out = _db.execute_via_docker(
            f"SELECT marketing.emit_webhook_event("
            f"{sql_kind}, {sql_payload}::jsonb, {sql_campaign}, {sql_email}"
            f") AS event_id"
        )
        # execute_via_docker returns text; pull the UUID line.
        for line in (out or "").splitlines():
            line = line.strip()
            if len(line) == 36 and line.count("-") == 4:
                return line
        return None
    except Exception as e:
        logger.warning("webhook emit_event(%r) failed: %s", kind, e)
        return None


# ─── Signing ──────────────────────────────────────────────────────────


def sign_payload(secret: str, body_bytes: bytes) -> str:
    """Return `sha256=<hex>` matching the X-Vibemind-Signature header
    format. body_bytes MUST be the exact bytes the receiver sees -- so
    callers serialize JSON once and reuse the bytes.
    """
    if not isinstance(secret, str) or not secret:
        raise ValueError("sign_payload: secret must be non-empty str")
    if not isinstance(body_bytes, (bytes, bytearray)):
        raise TypeError("sign_payload: body_bytes must be bytes")
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body_bytes: bytes, header_value: str) -> bool:
    """Constant-time verify. Used by tests + an optional receiver-side helper."""
    if not header_value or not isinstance(header_value, str):
        return False
    try:
        expected = sign_payload(secret, body_bytes)
    except Exception:
        return False
    return hmac.compare_digest(expected, header_value.strip())


__all__ = [
    "KNOWN_EVENT_KINDS",
    "emit_event",
    "sign_payload",
    "verify_signature",
]
