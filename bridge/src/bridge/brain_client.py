"""Async HTTP client for Brain (Tahlamus) routing API."""

import logging

import httpx

from bridge.config import settings
from bridge.models import RoutingInfo

logger = logging.getLogger(__name__)

_FALLBACK_ROUTING = RoutingInfo(
    primary_space="ideas",
    secondary_spaces=[],
    confidence=0.0,
    routing_id="rt_fallback",
)


async def route(user_text: str, event_type: str = "") -> RoutingInfo:
    """Ask Brain to route a task to a space.

    POST /api/cortex/route → {primary_space, secondary_spaces, confidence, routing_id}
    """
    try:
        async with httpx.AsyncClient(timeout=settings.brain_timeout_secs) as client:
            resp = await client.post(
                f"{settings.brain_url}/api/cortex/route",
                json={"user_text": user_text[:200], "event_type": event_type or ""},
            )
            resp.raise_for_status()
            data = resp.json()
            return RoutingInfo(
                primary_space=data["primary_space"],
                secondary_spaces=data.get("secondary_spaces", []),
                confidence=data.get("confidence", 0.0),
                routing_id=data.get("routing_id", "rt_unknown"),
            )
    except Exception as e:
        logger.warning(f"Brain routing failed, using fallback: {e}")
        return _FALLBACK_ROUTING


async def reward(routing_id: str, success: bool) -> bool:
    """Send reward signal back to Brain for Hebbian learning.

    POST /api/cortex/route/reward → {ok, routing_id}
    Fire-and-forget: failures are logged but not raised.
    """
    if routing_id == "rt_fallback":
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{settings.brain_url}/api/cortex/route/reward",
                json={"routing_id": routing_id, "success": success},
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.debug(f"Brain reward failed (non-critical): {e}")
        return False
