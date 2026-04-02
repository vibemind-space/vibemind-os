"""Agent Activity Log -- records and queries agent activity entries.

Provides a central, in-memory log for agent activities.  Every logged
activity captures the agent, activity type, description, and timestamp.
The log supports filtering by agent and activity type, per-agent queries,
and automatic pruning when the entry limit is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the activity log."""

    activities: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentActivityLog:
    """In-memory activity log for agents.

    Parameters
    ----------
    max_entries:
        Maximum total number of activity entries to keep.  When the limit
        is reached the oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = _State()

        # stats counters
        self._stats: Dict[str, int] = {
            "total_logged": 0,
            "total_pruned": 0,
            "total_cleared": 0,
            "total_queries": 0,
        }

        logger.debug("agent_activity_log.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, activity_type: str, now: float) -> str:
        """Create a collision-free activity ID using SHA-256 + _seq."""
        raw = f"{agent_id}-{activity_type}-{now}-{self._state._seq}"
        return "aal-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Total entry count (internal)
    # ------------------------------------------------------------------

    def _total_entries(self) -> int:
        """Return the total number of activity entries across all agents."""
        return sum(len(v) for v in self._state.activities.values())

    # ------------------------------------------------------------------
    # Logging activities
    # ------------------------------------------------------------------

    def log_activity(
        self,
        agent_id: str,
        activity_type: str,
        description: str = "",
    ) -> str:
        """Log an activity and return its ``activity_id``.

        Returns the generated ``aal-...`` identifier for the new entry.
        """
        with self._lock:
            # prune if at capacity
            if self._total_entries() >= self._max_entries:
                self._prune()

            self._state._seq += 1
            now = time.time()
            activity_id = self._generate_id(agent_id, activity_type, now)

            entry: Dict[str, Any] = {
                "activity_id": activity_id,
                "agent_id": agent_id,
                "activity_type": activity_type,
                "description": description,
                "timestamp": now,
            }

            self._state.activities.setdefault(agent_id, []).append(entry)
            self._stats["total_logged"] += 1

        logger.debug(
            "agent_activity_log.log_activity",
            activity_id=activity_id,
            agent_id=agent_id,
            activity_type=activity_type,
        )
        self._fire("activity_logged", {
            "activity_id": activity_id,
            "agent_id": agent_id,
            "activity_type": activity_type,
            "description": description,
        })
        return activity_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_activities(
        self,
        agent_id: str,
        activity_type: str = "",
    ) -> List[Dict[str, Any]]:
        """Return activities for *agent_id*, optionally filtered by *activity_type*."""
        with self._lock:
            self._stats["total_queries"] += 1
            entries = list(self._state.activities.get(agent_id, []))
            if activity_type:
                entries = [e for e in entries if e["activity_type"] == activity_type]
            return entries

    def get_latest_activity(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent activity for *agent_id*, or ``None``."""
        with self._lock:
            self._stats["total_queries"] += 1
            entries = self._state.activities.get(agent_id, [])
            if not entries:
                return None
            return dict(entries[-1])

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_activity_count(self, agent_id: str = "") -> int:
        """Count activities, optionally filtered to a single agent."""
        with self._lock:
            if not agent_id:
                return self._total_entries()
            return len(self._state.activities.get(agent_id, []))

    # ------------------------------------------------------------------
    # Clearing
    # ------------------------------------------------------------------

    def clear_activities(self, agent_id: str) -> int:
        """Remove all activities for *agent_id*.

        Returns the number of activities removed.
        """
        with self._lock:
            entries = self._state.activities.pop(agent_id, [])
            count = len(entries)
            self._stats["total_cleared"] += count

        if count:
            logger.debug(
                "agent_activity_log.clear_activities",
                agent_id=agent_id,
                removed=count,
            )
            self._fire("activities_cleared", {
                "agent_id": agent_id,
                "count": count,
            })

        return count

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one activity."""
        with self._lock:
            return [
                aid
                for aid, entries in self._state.activities.items()
                if entries
            ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._state.callbacks:
                del self._state.callbacks[name]
                return True
            else:
                return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._state.callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            return {
                **self._stats,
                "current_entries": self._total_entries(),
                "unique_agents": len([
                    aid for aid, entries in self._state.activities.items()
                    if entries
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.activities.clear()
            self._state._seq = 0
            self._state.callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_activity_log.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        # collect all entries with their agent_id for removal
        all_entries: List[tuple] = []
        for aid, entries in self._state.activities.items():
            for entry in entries:
                all_entries.append((aid, entry))

        all_entries.sort(key=lambda x: x[1]["timestamp"])
        to_remove = max(len(all_entries) // 4, 1)

        for aid, entry in all_entries[:to_remove]:
            agent_list = self._state.activities.get(aid, [])
            try:
                agent_list.remove(entry)
            except ValueError:
                pass

        self._stats["total_pruned"] += to_remove
        logger.debug("agent_activity_log.prune", removed=to_remove)
