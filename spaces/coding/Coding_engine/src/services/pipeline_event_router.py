"""Pipeline event router.

Routes pipeline events to target pipelines based on event type.
Supports priority-based resolution, enable/disable toggling,
and callback notifications on route mutations.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RouteRecord:
    """A single event route definition."""

    route_id: str = ""
    event_type: str = ""
    target_pipeline: str = ""
    priority: int = 0
    enabled: bool = True
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Event Router
# ---------------------------------------------------------------------------


class PipelineEventRouter:
    """Route pipeline events to target pipelines by event type."""

    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._routes: Dict[str, RouteRecord] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_registered": 0,
            "total_deleted": 0,
            "total_resolved": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix ``per-``."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"per-{digest}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_dict(self, rec: RouteRecord) -> Dict:
        return {
            "route_id": rec.route_id,
            "event_type": rec.event_type,
            "target_pipeline": rec.target_pipeline,
            "priority": rec.priority,
            "enabled": rec.enabled,
            "created_at": rec.created_at,
        }

    def _fire(self, action: str, route_id: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, route_id)
            except Exception:
                logger.warning("callback_error", action=action, route_id=route_id)

    def _prune_if_needed(self) -> None:
        """Remove oldest routes if max entries exceeded."""
        if len(self._routes) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._routes,
            key=lambda rid: self._routes[rid].created_at,
        )
        to_remove = len(self._routes) - self.MAX_ENTRIES
        for rid in sorted_ids[:to_remove]:
            del self._routes[rid]
            logger.debug("route_pruned", route_id=rid)

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------

    def register_route(
        self,
        event_type: str,
        target_pipeline: str,
        priority: int = 0,
    ) -> str:
        """Register a new event route.

        Returns route_id (``per-...``).  Each call creates a new route,
        even for duplicate event_type + target_pipeline combinations.
        """
        if not event_type or not target_pipeline:
            logger.warning(
                "register_route_invalid",
                event_type=event_type,
                target_pipeline=target_pipeline,
            )
            return ""

        route_id = self._generate_id(f"{event_type}:{target_pipeline}")
        now = time.time()

        rec = RouteRecord(
            route_id=route_id,
            event_type=event_type,
            target_pipeline=target_pipeline,
            priority=priority,
            enabled=True,
            created_at=now,
        )

        self._routes[route_id] = rec
        self._stats["total_registered"] += 1
        self._prune_if_needed()

        logger.info(
            "route_registered",
            route_id=route_id,
            event_type=event_type,
            target_pipeline=target_pipeline,
            priority=priority,
        )
        self._fire("register", route_id)
        return route_id

    # ------------------------------------------------------------------
    # Route retrieval
    # ------------------------------------------------------------------

    def get_route(self, route_id: str) -> Optional[Dict]:
        """Return route dict or ``None``."""
        self._stats["total_lookups"] += 1
        rec = self._routes.get(route_id)
        if rec is None:
            return None
        return self._to_dict(rec)

    # ------------------------------------------------------------------
    # Target resolution
    # ------------------------------------------------------------------

    def resolve_targets(self, event_type: str) -> List[str]:
        """Return target_pipeline strings for *event_type*, sorted by priority desc.

        Only enabled routes are included.
        """
        self._stats["total_resolved"] += 1
        matches = [
            rec
            for rec in self._routes.values()
            if rec.event_type == event_type and rec.enabled
        ]
        matches.sort(key=lambda r: r.priority, reverse=True)
        return [r.target_pipeline for r in matches]

    # ------------------------------------------------------------------
    # Enable / Disable
    # ------------------------------------------------------------------

    def disable_route(self, route_id: str) -> bool:
        """Disable a route. Returns ``True`` if disabled, ``False`` if not found."""
        rec = self._routes.get(route_id)
        if rec is None:
            return False
        rec.enabled = False
        logger.info("route_disabled", route_id=route_id)
        self._fire("disable", route_id)
        return True

    def enable_route(self, route_id: str) -> bool:
        """Enable a route. Returns ``True`` if enabled, ``False`` if not found."""
        rec = self._routes.get(route_id)
        if rec is None:
            return False
        rec.enabled = True
        logger.info("route_enabled", route_id=route_id)
        self._fire("enable", route_id)
        return True

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_route(self, route_id: str) -> bool:
        """Delete a route. Returns ``True`` if deleted, ``False`` if not found."""
        rec = self._routes.get(route_id)
        if rec is None:
            return False
        del self._routes[route_id]
        self._stats["total_deleted"] += 1
        logger.info("route_deleted", route_id=route_id)
        self._fire("delete", route_id)
        return True

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def get_routes_for_event(self, event_type: str) -> List[Dict]:
        """Return list of route dicts for *event_type* (all, including disabled)."""
        return [
            self._to_dict(rec)
            for rec in self._routes.values()
            if rec.event_type == event_type
        ]

    def list_event_types(self) -> List[str]:
        """Return list of unique event_types."""
        seen: set = set()
        result: List[str] = []
        for rec in self._routes.values():
            if rec.event_type not in seen:
                seen.add(rec.event_type)
                result.append(rec.event_type)
        return result

    def get_route_count(self) -> int:
        """Return total number of registered routes."""
        return len(self._routes)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns ``True`` if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "active_routes": len(self._routes),
            "active_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._routes.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_event_router_reset")
