"""Agent Task Dispatcher -- dispatches agent tasks with priority and tracking.

Manages dispatch records for assigning tasks to agents, supporting priority-based
ordering, querying, filtering, and aggregate statistics.

Usage::

    dispatcher = AgentTaskDispatcher()

    # Dispatch a task
    record_id = dispatcher.dispatch("task-1", "builder-agent", priority=3)

    # Query
    entry = dispatcher.get_dispatch(record_id)
    dispatches = dispatcher.get_dispatches(agent_id="builder-agent")
    stats = dispatcher.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskDispatcherState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskDispatcher:
    """Dispatches agent tasks with priority and tracking."""

    PREFIX = "atds-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskDispatcherState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        quarter = len(sorted_keys) // 4
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Dispatch operations
    # ------------------------------------------------------------------

    def dispatch(
        self,
        task_id: str,
        agent_id: str,
        priority: int = 5,
        metadata: Optional[dict] = None,
    ) -> str:
        """Dispatch a task to an agent.

        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        record_id = self._generate_id()
        now = time.time()
        entry = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "priority": priority,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry

        self._prune()
        self._fire("dispatched", entry)
        logger.debug(
            "Task dispatched: %s (task=%s, agent=%s, priority=%d)",
            record_id,
            task_id,
            agent_id,
            priority,
        )
        return record_id

    def get_dispatch(self, record_id: str) -> Optional[dict]:
        """Return the dispatch entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_dispatches(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query dispatches, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_dispatch_count(self, agent_id: str = "") -> int:
        """Return the number of dispatches, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if e["agent_id"] == agent_id:
                count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_dispatches": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskDispatcherState()
        self._on_change = None
        logger.debug("AgentTaskDispatcher reset")
