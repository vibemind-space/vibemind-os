"""Webhook delivery worker.

Drains marketing.webhook_events (rows where fanned_out_at IS NULL),
fans out to every active subscription whose `events` array matches
the event_kind, signs the JSON body, POSTs it, and tracks the
delivery in marketing.webhook_deliveries.

Retry contract (mirrors the migration-020 docstring):
  2xx       → mark delivered, increment subscription.last_success_at
  4xx       → mark delivered (permanent fail), bump failure_count
  5xx / net → leave delivered_at NULL, increment retry_count, backoff
  50 cons.  → auto-disable subscription, write audit_log row

Designed to be run as a polling loop (every few seconds) or one-shot
(for tests). Has NO external dependencies beyond urllib + _db.

Entry-points:
  run_one_cycle()  -- single pass: fanout + deliver + retry. Returns stats.
  run_forever()    -- loop with sleep; intended for a host service.
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.sync import _db                       # noqa: E402
from spaces.marketing.tools.webhooks import sign_payload    # noqa: E402


logger = logging.getLogger("marketing.webhook_delivery")


# ─── Constants ─────────────────────────────────────────────────────────


# Exponential backoff schedule for 5xx / transport errors (seconds).
# After the last entry, the delivery is marked `dead=true`.
_RETRY_SCHEDULE_S: Tuple[int, ...] = (60, 5 * 60, 15 * 60, 60 * 60, 4 * 3600)
_AUTO_DISABLE_AFTER_FAILURES = 50
_HTTP_TIMEOUT_S = 15
_RESPONSE_BODY_TRUNCATE = 1000
_FANOUT_BATCH_LIMIT = 200
_DELIVERY_BATCH_LIMIT = 100


# ─── Fan-out: webhook_events → webhook_deliveries ─────────────────────


def _fanout_pending_events(limit: int = _FANOUT_BATCH_LIMIT) -> int:
    """Pick events with fanned_out_at IS NULL, insert one delivery row
    per matching subscription, mark the event fanned_out_at = now().

    Returns number of events fanned out (not number of delivery rows).
    """
    events = _db.query_via_docker(
        f"SELECT id::text AS id, event_kind, occurred_at::text AS occurred_at, "
        f"       payload::text AS payload "
        f"FROM marketing.webhook_events "
        f"WHERE fanned_out_at IS NULL "
        f"ORDER BY occurred_at "
        f"LIMIT {int(limit)}"
    )
    if not events:
        return 0

    subs = _db.query_via_docker(
        "SELECT id::text AS id, events, name, channel_filter "
        "FROM marketing.webhook_subscriptions "
        "WHERE active = true"
    )

    fanned_count = 0
    for ev in events:
        evid = ev["id"]
        ekind = ev["event_kind"]
        # channel-aware routing (038): a subscription may bind to ONE channel
        # via channel_filter; matched against the event payload's channel.
        try:
            ev_channel = (json.loads(ev.get("payload") or "{}") or {}).get("channel")
        except (ValueError, TypeError):
            ev_channel = None
        matching: List[str] = []
        for s in subs:
            evs = s.get("events") or []
            if isinstance(evs, str):
                # postgres array sometimes deserializes as "{a,b,c}"
                evs = [t.strip().strip('"') for t in evs.strip("{}").split(",") if t.strip()]
            if "*" not in evs and ekind not in evs:
                continue
            ch_filter = s.get("channel_filter")
            if ch_filter and ch_filter != ev_channel:
                continue  # bound to a different channel
            matching.append(s["id"])
        # Insert delivery rows (idempotent via UNIQUE(event_id, subscription_id))
        if matching:
            values = ", ".join(
                f"({_db._sql_literal(evid)}::uuid, {_db._sql_literal(sid)}::uuid, now())"
                for sid in matching
            )
            _db.execute_via_docker(
                f"INSERT INTO marketing.webhook_deliveries "
                f"(event_id, subscription_id, next_retry_at) "
                f"VALUES {values} "
                f"ON CONFLICT (event_id, subscription_id) DO NOTHING"
            )
        # Mark the event fanned out regardless of matching count
        _db.execute_via_docker(
            f"UPDATE marketing.webhook_events "
            f"SET fanned_out_at = now(), fanout_count = {len(matching)} "
            f"WHERE id = {_db._sql_literal(evid)}::uuid"
        )
        fanned_count += 1
    return fanned_count


# ─── HTTP delivery ────────────────────────────────────────────────────


def _post_to_subscription(url: str, secret: str,
                          event_id: str, event_kind: str,
                          payload: Dict[str, Any]) -> Dict[str, Any]:
    """Single HTTP POST with signed body. Returns dict:
       {"ok": bool, "http_status": int|None, "body": str, "error": str|None}
    """
    body_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Vibemind-Signature": sign_payload(secret, body_bytes),
        "X-Vibemind-Event": event_kind,
        "X-Vibemind-Event-Id": event_id,
        "X-Vibemind-Timestamp": str(int(time.time())),
        "User-Agent": "vibemind-webhook/1.0",
    }
    req = urllib.request.Request(url, data=body_bytes, method="POST",
                                  headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as r:
            body = r.read(_RESPONSE_BODY_TRUNCATE + 1).decode("utf-8", "replace")
            return {"ok": True, "http_status": r.status,
                    "body": body[:_RESPONSE_BODY_TRUNCATE], "error": None}
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read(_RESPONSE_BODY_TRUNCATE + 1)
        except Exception:
            pass
        return {"ok": False, "http_status": e.code,
                "body": body.decode("utf-8", "replace")[:_RESPONSE_BODY_TRUNCATE],
                "error": None}
    except Exception as e:
        return {"ok": False, "http_status": None, "body": "",
                "error": f"{type(e).__name__}: {e}"[:_RESPONSE_BODY_TRUNCATE]}


# ─── Deliver pending rows ─────────────────────────────────────────────


def _compute_next_retry(retry_count: int) -> Optional[int]:
    """Return seconds-from-now for next attempt, or None if dead."""
    if retry_count >= len(_RETRY_SCHEDULE_S):
        return None
    base = _RETRY_SCHEDULE_S[retry_count]
    # ±10% jitter to avoid thundering herd
    jitter = random.uniform(-0.1, 0.1) * base
    return max(1, int(base + jitter))


def _deliver_pending(limit: int = _DELIVERY_BATCH_LIMIT) -> Dict[str, int]:
    """Drain webhook_deliveries where delivered_at IS NULL AND dead = false
    AND (next_retry_at IS NULL OR next_retry_at <= now()).
    """
    rows = _db.query_via_docker(
        f"SELECT d.id::text AS id, d.event_id::text AS event_id, "
        f"       d.subscription_id::text AS subscription_id, "
        f"       d.retry_count, "
        f"       e.event_kind, e.payload::text AS payload_json, "
        f"       e.occurred_at::text AS occurred_at, "
        f"       s.url, s.secret, s.name AS sub_name "
        f"FROM marketing.webhook_deliveries d "
        f"JOIN marketing.webhook_events e        ON e.id = d.event_id "
        f"JOIN marketing.webhook_subscriptions s ON s.id = d.subscription_id "
        f"WHERE d.delivered_at IS NULL "
        f"  AND d.dead = false "
        f"  AND s.active = true "
        f"  AND (d.next_retry_at IS NULL OR d.next_retry_at <= now()) "
        f"ORDER BY d.attempted_at "
        f"LIMIT {int(limit)}"
    )
    stats = {"attempted": 0, "delivered": 0, "retried": 0, "dead": 0}
    for row in rows:
        stats["attempted"] += 1
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            payload = {}
        envelope = {
            "event_id": row["event_id"],
            "event_kind": row["event_kind"],
            "occurred_at": row["occurred_at"],
            "delivery_attempt": int(row["retry_count"]) + 1,
            "data": payload,
        }
        res = _post_to_subscription(
            row["url"], row["secret"],
            row["event_id"], row["event_kind"], envelope,
        )
        _record_attempt(row, res, stats)
    return stats


def _record_attempt(row: Dict[str, Any], res: Dict[str, Any],
                    stats: Dict[str, int]) -> None:
    """Update webhook_deliveries + webhook_subscriptions based on outcome."""
    delivery_id = row["id"]
    sub_id = row["subscription_id"]
    rc = int(row["retry_count"])
    http_status = res["http_status"]
    body = res["body"][:_RESPONSE_BODY_TRUNCATE] if res["body"] else ""
    err = res["error"] or ""

    if res["ok"] and http_status is not None and 200 <= http_status < 300:
        # SUCCESS
        _db.execute_via_docker(
            f"UPDATE marketing.webhook_deliveries "
            f"SET delivered_at = now(), "
            f"    http_status = {int(http_status)}, "
            f"    response_body = {_db._sql_literal(body)}, "
            f"    error = NULL "
            f"WHERE id = {_db._sql_literal(delivery_id)}::uuid"
        )
        _db.execute_via_docker(
            f"UPDATE marketing.webhook_subscriptions "
            f"SET success_count = success_count + 1, "
            f"    last_success_at = now(), "
            f"    failure_count = 0, "
            f"    last_error = NULL "
            f"WHERE id = {_db._sql_literal(sub_id)}::uuid"
        )
        stats["delivered"] += 1
        return

    # FAILURE — decide retry vs permanent
    permanent = http_status is not None and 400 <= http_status < 500
    next_retry_s = None if permanent else _compute_next_retry(rc)

    if next_retry_s is None:
        # Dead letter
        _db.execute_via_docker(
            f"UPDATE marketing.webhook_deliveries "
            f"SET delivered_at = now(), "
            f"    dead = true, "
            f"    retry_count = {rc + 1}, "
            f"    http_status = {http_status if http_status is not None else 'NULL'}, "
            f"    response_body = {_db._sql_literal(body)}, "
            f"    error = {_db._sql_literal(err)} "
            f"WHERE id = {_db._sql_literal(delivery_id)}::uuid"
        )
        stats["dead"] += 1
    else:
        _db.execute_via_docker(
            f"UPDATE marketing.webhook_deliveries "
            f"SET retry_count = {rc + 1}, "
            f"    next_retry_at = now() + interval '{int(next_retry_s)} seconds', "
            f"    http_status = {http_status if http_status is not None else 'NULL'}, "
            f"    response_body = {_db._sql_literal(body)}, "
            f"    error = {_db._sql_literal(err)} "
            f"WHERE id = {_db._sql_literal(delivery_id)}::uuid"
        )
        stats["retried"] += 1

    # Update subscription failure count, possibly auto-disable
    _db.execute_via_docker(
        f"UPDATE marketing.webhook_subscriptions "
        f"SET failure_count = failure_count + 1, "
        f"    last_failure_at = now(), "
        f"    last_error = {_db._sql_literal(err or f'HTTP {http_status}')[:1000]} "
        f"WHERE id = {_db._sql_literal(sub_id)}::uuid"
    )
    # Check disable threshold
    sub_row = _db.query_one(
        f"SELECT failure_count FROM marketing.webhook_subscriptions "
        f"WHERE id = {_db._sql_literal(sub_id)}::uuid"
    )
    if sub_row and int(sub_row.get("failure_count", 0)) >= _AUTO_DISABLE_AFTER_FAILURES:
        _db.execute_via_docker(
            f"UPDATE marketing.webhook_subscriptions "
            f"SET active = false, "
            f"    disabled_at = now(), "
            f"    disabled_reason = 'auto-disable: {_AUTO_DISABLE_AFTER_FAILURES} consecutive failures' "
            f"WHERE id = {_db._sql_literal(sub_id)}::uuid"
        )
        _db.execute_via_docker(
            f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
            f"VALUES ('webhook_delivery', 'subscription.auto_disabled', "
            f"        'marketing.webhook_subscriptions', "
            f"        {_db._sql_literal(json.dumps({'subscription_id': sub_id, 'reason': 'consecutive_failures'}))}::jsonb)"
        )


# ─── Entry-points ─────────────────────────────────────────────────────


def run_one_cycle() -> Dict[str, int]:
    """One pass: fan-out then deliver. Returns combined stats."""
    fanned = _fanout_pending_events()
    delivery_stats = _deliver_pending()
    return {"fanned_out": fanned, **delivery_stats}


def run_forever(poll_interval_s: float = 5.0) -> None:
    """Long-running loop. Logs each cycle's stats."""
    logger.info("webhook_delivery worker starting "
                "(poll_interval=%.1fs)", poll_interval_s)
    while True:
        try:
            stats = run_one_cycle()
            if any(v > 0 for v in stats.values()):
                logger.info("cycle: %s", stats)
        except KeyboardInterrupt:
            logger.info("webhook_delivery worker stopping")
            return
        except Exception as e:
            logger.exception("cycle failed: %s", e)
        time.sleep(poll_interval_s)


__all__ = ["run_one_cycle", "run_forever"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    interval = float(os.environ.get("WEBHOOK_DELIVERY_POLL_INTERVAL_S", "5"))
    run_forever(interval)
