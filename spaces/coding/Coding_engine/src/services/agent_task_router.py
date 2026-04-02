"""Agent Task Router -- routes tasks to agents based on configurable routing rules.

Provides type-based matching so that incoming tasks are dispatched to the
most appropriate agent according to priority-ranked routing rules.

Usage::

    router = AgentTaskRouter()

    rid = router.add_route("build", "agent-backend-1", priority=10)
    router.add_route("build", "agent-backend-2", priority=5)

    best = router.route_task("build")  # -> "agent-backend-1"
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# -------------------------------------------------------------------
# Internal state
# -------------------------------------------------------------------

@dataclass
class _RouteEntry:
    """A single routing rule mapping a task type to an agent."""

    route_id: str
    task_type: str
    agent_id: str
    priority: int
    seq: int = 0
    created_at: float = field(default_factory=time.time)


# -------------------------------------------------------------------
# AgentTaskRouter
# -------------------------------------------------------------------

class AgentTaskRouter:
    """Routes tasks to agents based on configurable routing rules (type-based matching)."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._routes: Dict[str, _RouteEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

        # Stats counters
        self._total_added: int = 0
        self._total_removed: int = 0
        self._total_routed: int = 0

    # ---------------------------------------------------------------
    # ID generation
    # ---------------------------------------------------------------

    def _next_id(self, key: str) -> str:
        """Generate a collision-free route ID with prefix ``atr-``."""
        self._seq += 1
        raw = f"{key}-{uuid.uuid4()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"atr-{digest}"

    # ---------------------------------------------------------------
    # Route management
    # ---------------------------------------------------------------

    def add_route(self, task_type: str, agent_id: str, priority: int = 0) -> str:
        """Add a routing rule that maps *task_type* to *agent_id*.

        Args:
            task_type: The task type string to match against.
            agent_id: The agent that should handle tasks of this type.
            priority: Higher values indicate higher priority.  When multiple
                routes exist for the same task type the highest-priority
                route wins.

        Returns:
            The generated route ID, or ``""`` if parameters are invalid
            or max entries has been reached.
        """
        if not task_type or not agent_id:
            return ""
        if len(self._routes) >= self._max_entries:
            return ""

        route_id = self._next_id(task_type)

        self._routes[route_id] = _RouteEntry(
            route_id=route_id,
            task_type=task_type,
            agent_id=agent_id,
            priority=priority,
            seq=self._seq,
        )

        self._total_added += 1

        logger.info(
            "route_added",
            route_id=route_id,
            task_type=task_type,
            agent_id=agent_id,
            priority=priority,
        )
        self._fire("route_added", {
            "route_id": route_id,
            "task_type": task_type,
            "agent_id": agent_id,
            "priority": priority,
        })
        return route_id

    def remove_route(self, route_id: str) -> bool:
        """Remove a routing rule by its ID.

        Returns:
            ``True`` if removed, ``False`` if *route_id* was not found.
        """
        entry = self._routes.pop(route_id, None)
        if not entry:
            return False

        self._total_removed += 1

        logger.info("route_removed", route_id=route_id, task_type=entry.task_type)
        self._fire("route_removed", {
            "route_id": route_id,
            "task_type": entry.task_type,
            "agent_id": entry.agent_id,
        })
        return True

    # ---------------------------------------------------------------
    # Routing
    # ---------------------------------------------------------------

    def route_task(self, task_type: str) -> Optional[str]:
        """Find the best agent for the given *task_type*.

        Selects the route with the highest priority among all routes
        registered for *task_type*.  If there are ties the route added
        first (lowest sequence number) wins.

        Args:
            task_type: The task type to look up.

        Returns:
            The *agent_id* of the best matching route, or ``None`` if no
            route is registered for the given type.
        """
        if not task_type:
            return None

        best: Optional[_RouteEntry] = None
        for entry in self._routes.values():
            if entry.task_type != task_type:
                continue
            if best is None:
                best = entry
            elif entry.priority > best.priority:
                best = entry
            elif entry.priority == best.priority and entry.seq < best.seq:
                best = entry

        if best is None:
            return None

        self._total_routed += 1

        logger.debug(
            "task_routed",
            task_type=task_type,
            agent_id=best.agent_id,
            route_id=best.route_id,
        )
        self._fire("task_routed", {
            "task_type": task_type,
            "agent_id": best.agent_id,
            "route_id": best.route_id,
        })
        return best.agent_id

    # ---------------------------------------------------------------
    # Queries
    # ---------------------------------------------------------------

    def get_routes_for_type(self, task_type: str) -> List[Dict[str, Any]]:
        """Return all routes registered for *task_type*.

        Results are sorted by priority descending (highest first).
        """
        results: List[Dict[str, Any]] = []
        for entry in self._routes.values():
            if entry.task_type == task_type:
                results.append({
                    "route_id": entry.route_id,
                    "task_type": entry.task_type,
                    "agent_id": entry.agent_id,
                    "priority": entry.priority,
                    "created_at": entry.created_at,
                })
        results.sort(key=lambda d: d["priority"], reverse=True)
        return results

    def get_routes_for_agent(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all routes assigned to a specific *agent_id*.

        Results are sorted by task type alphabetically.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._routes.values():
            if entry.agent_id == agent_id:
                results.append({
                    "route_id": entry.route_id,
                    "task_type": entry.task_type,
                    "agent_id": entry.agent_id,
                    "priority": entry.priority,
                    "created_at": entry.created_at,
                })
        results.sort(key=lambda d: d["task_type"])
        return results

    def list_task_types(self) -> List[str]:
        """Return a sorted list of all distinct task types with registered routes."""
        types: set[str] = set()
        for entry in self._routes.values():
            types.add(entry.task_type)
        return sorted(types)

    def get_route_count(self) -> int:
        """Return the total number of currently registered routes."""
        return len(self._routes)

    # ---------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named callback invoked on state changes.

        Args:
            name: Unique name for this callback.
            callback: ``callback(action, data)`` where *action* is a string
                like ``"route_added"`` or ``"task_routed"`` and *data* is a dict.
        """
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name.

        Returns:
            ``True`` if removed, ``False`` if *name* was not registered.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *detail*."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.warning("callback_error", action=action, exc_info=True)

    # ---------------------------------------------------------------
    # Stats / Reset
    # ---------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return router statistics as a dict.

        Keys include ``current_routes``, ``total_added``, ``total_removed``,
        ``total_routed``, ``task_type_count``, and ``callback_count``.
        """
        return {
            "current_routes": len(self._routes),
            "total_added": self._total_added,
            "total_removed": self._total_removed,
            "total_routed": self._total_routed,
            "task_type_count": len(self.list_task_types()),
            "callback_count": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all router state, returning it to a pristine condition."""
        self._routes.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_added = 0
        self._total_removed = 0
        self._total_routed = 0
        logger.info("router_reset")
