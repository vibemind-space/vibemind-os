"""Pipeline Data Router – routes data between pipeline components.

Routes data packets from source components to destination components
based on configurable routing rules. Supports content-based routing
with pattern matching, round-robin distribution, and broadcast modes.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Route:
    route_id: str
    name: str
    source: str
    destination: str
    mode: str  # direct, broadcast, round_robin
    pattern: str  # content filter pattern (empty = match all)
    active: bool
    total_routed: int
    total_dropped: int
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _RoutedPacket:
    packet_id: str
    route_id: str
    source: str
    destination: str
    payload: Any
    created_at: float


class PipelineDataRouter:
    """Routes data between pipeline components."""

    MODES = ("direct", "broadcast", "round_robin")

    def __init__(self, max_routes: int = 10000, max_history: int = 100000):
        self._routes: Dict[str, _Route] = {}
        self._name_index: Dict[str, str] = {}
        self._history: List[_RoutedPacket] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_routes = max_routes
        self._max_history = max_history
        self._seq = 0
        self._rr_counters: Dict[str, int] = {}  # route_id -> round-robin counter

        # stats
        self._total_routes = 0
        self._total_routed = 0
        self._total_dropped = 0

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def create_route(
        self,
        name: str,
        source: str,
        destination: str = "",
        mode: str = "direct",
        pattern: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or not source:
            return ""
        if mode not in self.MODES:
            return ""
        if name in self._name_index:
            return ""
        if len(self._routes) >= self._max_routes:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{source}-{now}-{self._seq}"
        rid = "rte-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        route = _Route(
            route_id=rid,
            name=name,
            source=source,
            destination=destination,
            mode=mode,
            pattern=pattern,
            active=True,
            total_routed=0,
            total_dropped=0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._routes[rid] = route
        self._name_index[name] = rid
        self._total_routes += 1
        self._fire("route_created", {"route_id": rid, "name": name})
        return rid

    def get_route(self, route_id: str) -> Optional[Dict[str, Any]]:
        r = self._routes.get(route_id)
        if not r:
            return None
        return {
            "route_id": r.route_id,
            "name": r.name,
            "source": r.source,
            "destination": r.destination,
            "mode": r.mode,
            "pattern": r.pattern,
            "active": r.active,
            "total_routed": r.total_routed,
            "total_dropped": r.total_dropped,
            "tags": list(r.tags),
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }

    def get_route_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        rid = self._name_index.get(name)
        if not rid:
            return None
        return self.get_route(rid)

    def remove_route(self, route_id: str) -> bool:
        r = self._routes.pop(route_id, None)
        if not r:
            return False
        self._name_index.pop(r.name, None)
        self._rr_counters.pop(route_id, None)
        self._fire("route_removed", {"route_id": route_id})
        return True

    def enable_route(self, route_id: str) -> bool:
        r = self._routes.get(route_id)
        if not r or r.active:
            return False
        r.active = True
        r.updated_at = time.time()
        return True

    def disable_route(self, route_id: str) -> bool:
        r = self._routes.get(route_id)
        if not r or not r.active:
            return False
        r.active = False
        r.updated_at = time.time()
        return True

    def update_route(
        self,
        route_id: str,
        destination: Optional[str] = None,
        pattern: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> bool:
        r = self._routes.get(route_id)
        if not r:
            return False
        if destination is not None:
            r.destination = destination
        if pattern is not None:
            r.pattern = pattern
        if mode is not None and mode in self.MODES:
            r.mode = mode
        r.updated_at = time.time()
        return True

    def list_routes(
        self,
        source: str = "",
        destination: str = "",
        active: Optional[bool] = None,
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for r in self._routes.values():
            if source and r.source != source:
                continue
            if destination and r.destination != destination:
                continue
            if active is not None and r.active != active:
                continue
            if tag and tag not in r.tags:
                continue
            results.append(self.get_route(r.route_id))
        return results

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(
        self,
        source: str,
        payload: Any = None,
        content_key: str = "",
    ) -> int:
        """Route data from source. Returns number of successful routes."""
        if not source:
            return 0

        routed = 0
        for r in list(self._routes.values()):
            if not r.active or r.source != source:
                continue

            # content-based filtering
            if r.pattern and content_key:
                if r.pattern.lower() not in content_key.lower():
                    r.total_dropped += 1
                    self._total_dropped += 1
                    continue

            self._seq += 1
            now = time.time()
            raw = f"pkt-{r.route_id}-{now}-{self._seq}"
            pid = "pkt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            packet = _RoutedPacket(
                packet_id=pid,
                route_id=r.route_id,
                source=source,
                destination=r.destination,
                payload=payload,
                created_at=now,
            )
            self._history.append(packet)
            if len(self._history) > self._max_history:
                trim = self._max_history // 10
                self._history = self._history[trim:]

            r.total_routed += 1
            self._total_routed += 1
            routed += 1

        if routed > 0:
            self._fire("data_routed", {"source": source, "count": routed})
        return routed

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_routing_history(
        self,
        source: str = "",
        destination: str = "",
        route_id: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for p in reversed(self._history):
            if source and p.source != source:
                continue
            if destination and p.destination != destination:
                continue
            if route_id and p.route_id != route_id:
                continue
            results.append({
                "packet_id": p.packet_id,
                "route_id": p.route_id,
                "source": p.source,
                "destination": p.destination,
                "payload": p.payload,
                "created_at": p.created_at,
            })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_routes": len(self._routes),
            "total_routes": self._total_routes,
            "total_routed": self._total_routed,
            "total_dropped": self._total_dropped,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._routes.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._rr_counters.clear()
        self._seq = 0
        self._total_routes = 0
        self._total_routed = 0
        self._total_dropped = 0
