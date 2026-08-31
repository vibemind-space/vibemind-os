"""Read-only metrics tools — aggregates over the marketing.* views
(migration 013). Never reveals candidate emails or message bodies.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..sync import _db


def get_stack_metrics() -> Dict[str, Any]:
    """Single-row top-level snapshot for the dashboard tile."""
    row = _db.query_one("SELECT * FROM marketing.v_stack_metrics")
    return {"success": True, "message": "ok", "data": row or {}}


def get_campaign_metrics(campaign_id: Optional[str] = None) -> Dict[str, Any]:
    """Per-campaign aggregate metrics. Without campaign_id returns all rows."""
    where = ""
    if campaign_id:
        where = f"WHERE campaign_id = {_db._sql_literal(campaign_id)}::uuid"
    rows = _db.query_via_docker(
        f"SELECT campaign_id::text AS campaign_id, campaign_name, campaign_status, "
        f"       audience_id::text AS audience_id, sends_total, sends_sent, "
        f"       sends_delivered, sends_bounced, sends_replied, "
        f"       bounce_rate_pct, reply_rate_pct, last_send_at::text AS last_send_at "
        f"FROM marketing.v_campaign_metrics {where} ORDER BY last_send_at DESC NULLS LAST"
    )
    return {"success": True, "message": f"{len(rows)} campaign(s)", "data": rows}


def get_send_activity_daily(days_back: int = 30) -> Dict[str, Any]:
    """Per-day x per-campaign send activity for the last N days.

    Defaults to 30 days; capped at 365.
    """
    days_back = min(max(1, int(days_back)), 365)
    rows = _db.query_via_docker(
        f"SELECT date_bucket::text AS date, campaign_id::text AS campaign_id, "
        f"       campaign_name, sends, bounces, replies, delivered "
        f"FROM marketing.v_send_activity_daily "
        f"WHERE date_bucket >= (now() - interval '{days_back} days')::date "
        f"ORDER BY date_bucket DESC, campaign_name"
    )
    return {"success": True, "message": f"{len(rows)} day-bucket(s)", "data": rows}


__all__ = [
    "get_stack_metrics",
    "get_campaign_metrics",
    "get_send_activity_daily",
]
