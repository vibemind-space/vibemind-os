"""Agent task notifier -- sends notifications about task state changes.

Provides an in-memory notification system that records and queries
notifications related to agent task events.  Each notification captures
the originating task, agent, event type, message, optional metadata,
and creation timestamp.  Supports per-agent and per-event-type filtering,
automatic pruning when the entry limit is reached, and change callbacks.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# State dataclass
# ------------------------------------------------------------------

@dataclass
class AgentTaskNotifierState:
    """Holds all mutable state for the notifier."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentTaskNotifier:
    """In-memory task notification service.

    Sends and stores notifications about task state changes for agents.
    Notifications are keyed by a SHA-256-based ID and can be queried by
    agent, event type, or both.

    Parameters
    ----------
    max_entries:
        Maximum number of notifications to keep.  When the limit is reached
        the oldest quarter of entries is pruned automatically.
    """

    PREFIX = "atnf-"
    MAX_ENTRIES = 10000

    def __init__(self, max_entries: int | None = None) -> None:
        self._max_entries = max_entries if max_entries is not None else self.MAX_ENTRIES
        self._state = AgentTaskNotifierState()
        self._callbacks: Dict[str, Callable] = {}

        logger.debug("agent_task_notifier.init max_entries=%d", self._max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries = sorted(
            self._state.entries.values(),
            key=lambda e: (e["created_at"], e["_seq"]),
        )
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            del self._state.entries[e["notification_id"]]
        logger.debug("agent_task_notifier.prune removed=%d", to_remove)

    # ------------------------------------------------------------------
    # Notify
    # ------------------------------------------------------------------

    def notify(
        self,
        task_id: str,
        agent_id: str,
        event_type: str,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a notification and return its ID.

        Returns an empty string when *task_id*, *agent_id*, or *event_type*
        is falsy.
        """
        if not task_id or not agent_id or not event_type:
            return ""

        if len(self._state.entries) >= self._max_entries:
            self._prune()

        now = time.time()
        notification_id = self._generate_id(f"{task_id}{agent_id}{event_type}{now}")
        seq = self._state._seq

        entry: Dict[str, Any] = {
            "notification_id": notification_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "message": message,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": seq,
        }
        self._state.entries[notification_id] = entry

        logger.debug(
            "agent_task_notifier.notify id=%s task=%s agent=%s event=%s",
            notification_id,
            task_id,
            agent_id,
            event_type,
        )
        self._fire("notification_created", dict(entry))
        return notification_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_notification(self, notif_id: str) -> Optional[Dict[str, Any]]:
        """Return a single notification by ID, or ``None`` if not found."""
        entry = self._state.entries.get(notif_id)
        if entry is None:
            return None
        return dict(entry)

    def get_notifications(
        self,
        agent_id: str = "",
        event_type: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return notifications filtered by *agent_id* and/or *event_type*.

        Results are sorted newest-first (by ``created_at`` then ``_seq``,
        descending).  At most *limit* results are returned.
        """
        results = list(self._state.entries.values())

        if agent_id:
            results = [e for e in results if e["agent_id"] == agent_id]
        if event_type:
            results = [e for e in results if e["event_type"] == event_type]

        results.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in results[:limit]]

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_notification_count(self, agent_id: str = "") -> int:
        """Return the number of stored notifications.

        If *agent_id* is provided, count only notifications for that agent.
        """
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Dict[str, Callable]:
        """Return current callback registry (read-only copy)."""
        return dict(self._callbacks)

    @on_change.setter
    def on_change(self, value: tuple) -> None:
        """Register a callback as ``(name, callable)``."""
        name, callback = value
        self._callbacks[name] = callback

    def _on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback by name."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        agents = set()
        event_types = set()
        task_ids = set()
        for e in self._state.entries.values():
            agents.add(e["agent_id"])
            event_types.add(e["event_type"])
            task_ids.add(e["task_id"])
        return {
            "total_notifications": len(self._state.entries),
            "unique_agents": len(agents),
            "unique_event_types": len(event_types),
            "unique_tasks": len(task_ids),
            "seq": self._state._seq,
            "max_entries": self._max_entries,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state and callbacks."""
        self._state = AgentTaskNotifierState()
        self._callbacks.clear()
        logger.debug("agent_task_notifier.reset")
