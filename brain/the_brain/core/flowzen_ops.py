"""Privacy-minimal Flowzen operations backed by the shared Supabase schema."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional


_RECOMMENDATION_ID = re.compile(r"^fzr_[0-9a-f]{16}$")
_CIRCADIAN_MATRIX = {
    "energized": {"early_morning": "deep_work", "morning": "deep_work", "midday": "deep_work", "afternoon": "creative", "evening": "social", "night": "rest"},
    "focused": {"early_morning": "deep_work", "morning": "deep_work", "midday": "deep_work", "afternoon": "deep_work", "evening": "admin", "night": "rest"},
    "calm": {"early_morning": "creative", "morning": "creative", "midday": "admin", "afternoon": "creative", "evening": "rest", "night": "rest"},
    "tired": {"early_morning": "rest", "morning": "admin", "midday": "rest", "afternoon": "admin", "evening": "rest", "night": "rest"},
    "anxious": {"early_morning": "admin", "morning": "admin", "midday": "admin", "afternoon": "admin", "evening": "rest", "night": "rest"},
}


def _failure(event_id: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "event_id": event_id, "error": message}


async def _latest(client: Any, table: str, select: str) -> Optional[list]:
    return await client._request(
        "GET", f"/{table}",
        params={"select": select, "order": "created_at.desc", "limit": "1"},
    )


def _category(mood: str, time_window: str) -> str:
    return _CIRCADIAN_MATRIX.get(mood, _CIRCADIAN_MATRIX["calm"]).get(time_window, "rest")


def _recommendation_from_checkin(checkin: Dict[str, Any]) -> Dict[str, Any]:
    mood = str(checkin.get("mood") or "").strip().lower()
    time_window = str(checkin.get("time_window") or "").strip().lower()
    category = _category(mood, time_window)
    token_source = f"{checkin.get('id', '')}|{category}|{time_window}"
    return {
        "recommendation_id": "fzr_" + hashlib.sha256(token_source.encode()).hexdigest()[:16],
        "category": category,
        "time_window": time_window,
        "energy": checkin.get("energy"),
    }


async def recommend_op(client: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deterministic recommendation without persisting user data."""
    rows = await _latest(client, "flowzen_checkins", "id,mood,energy,time_window,hour,created_at")
    if rows is None:
        return _failure("rose.recommend", "flowzen_checkins unavailable")
    if not rows:
        return _failure("rose.recommend", "no flowzen check-in available")
    return {
        "ok": True, "event_id": "rose.recommend",
        "recommendation": _recommendation_from_checkin(rows[0]),
        "source": "supabase:flowzen_checkins", "mutated": False,
    }


async def accept_op(client: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist only an opaque acceptance marker, then verify it by read-back."""
    recommendation_id = str(payload.get("recommendation_log_id") or "").strip()
    if not _RECOMMENDATION_ID.fullmatch(recommendation_id):
        return _failure("rose.accept", "invalid recommendation_log_id")
    latest = await _latest(client, "flowzen_checkins", "id,mood,energy,time_window,hour,created_at")
    if latest is None:
        return _failure("rose.accept", "flowzen_checkins unavailable")
    if not latest or _recommendation_from_checkin(latest[0])["recommendation_id"] != recommendation_id:
        return _failure("rose.accept", "recommendation_log_id is not current")
    row = {"event_type": f"recommendation_accepted:{recommendation_id}", "time_window": "", "hour": 0}
    inserted = await client._request("POST", "/flowzen_activity", json=row, prefer="return=representation")
    if not inserted or not isinstance(inserted, list) or not inserted[0].get("id"):
        return _failure("rose.accept", "flowzen acceptance write failed")
    activity_id = str(inserted[0]["id"])
    verified = await client._request(
        "GET", "/flowzen_activity",
        params={"select": "id,event_type", "id": f"eq.{activity_id}", "limit": "1"},
    )
    if not verified or verified[0].get("event_type") != row["event_type"]:
        return _failure("rose.accept", "flowzen acceptance read-back failed")
    return {
        "ok": True, "event_id": "rose.accept", "recommendation_id": recommendation_id,
        "activity_id": activity_id, "status": "accepted", "verified": True,
    }


async def status_op(client: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return latest minimal Flowzen state without notes or diary text."""
    checkins = await _latest(client, "flowzen_checkins", "mood,energy,time_window,hour,created_at")
    activities = await _latest(client, "flowzen_activity", "id,event_type,time_window,hour,created_at")
    if checkins is None or activities is None:
        return _failure("rose.status", "flowzen status unavailable")
    latest_checkin = None
    if checkins:
        checkin = checkins[0]
        latest_checkin = {
            key: checkin.get(key)
            for key in ("mood", "energy", "time_window", "hour", "created_at")
        }
    latest_activity = None
    if activities:
        activity = activities[0]
        event_type = str(activity.get("event_type") or "")
        latest_activity = {
            "activity_id": activity.get("id"),
            "status": "accepted" if event_type.startswith("recommendation_accepted:") else "observed",
            "time_window": activity.get("time_window"), "hour": activity.get("hour"),
            "created_at": activity.get("created_at"),
        }
    return {
        "ok": True, "event_id": "rose.status",
        "status": {"latest_checkin": latest_checkin, "latest_activity": latest_activity},
        "source": "supabase", "mutated": False,
    }
