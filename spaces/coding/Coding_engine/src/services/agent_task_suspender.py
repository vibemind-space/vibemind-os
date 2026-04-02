"""Agent Task Suspender -- suspends agent tasks temporarily.

Allows suspending tasks with reason and metadata, querying suspensions,
and tracking statistics.

Usage::

    suspender = AgentTaskSuspender()

    # Suspend a task
    record_id = suspender.suspend("task-1", "agent-1", reason="maintenance")

    # Query
    entry = suspender.get_suspension(record_id)
    entries = suspender.get_suspensions(agent_id="agent-1")
    stats = suspender.get_stats()
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
class AgentTaskSuspenderState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskSuspender:
    """Suspends agent tasks temporarily."""

    PREFIX = "atsu-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskSuspenderState()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            entries.keys(),
            key=lambda k: (entries[k]["created_at"], entries[k].get("_seq", 0)),
        )
        remove_count = len(entries) - self.MAX_ENTRIES
        for key in sorted_keys[:remove_count]:
            del entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        on_change = self._state.callbacks.get("__on_change__")
        if on_change is not None:
            try:
                on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for name, cb in list(self._state.callbacks.items()):
            if name == "__on_change__":
                continue
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        if value is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = value

    def remove_callback(self, name: str) -> bool:
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def suspend(
        self,
        task_id: str,
        agent_id: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Suspend a task.

        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) > self.MAX_ENTRIES:
            return ""

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("suspend", self._state.entries[record_id])
        logger.debug(
            "Task suspended: %s (task=%s, agent=%s, reason=%s)",
            record_id,
            task_id,
            agent_id,
            reason,
        )
        return record_id

    def get_suspension(self, record_id: str) -> Optional[dict]:
        """Return the suspension entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_suspensions(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query suspensions, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_suspension_count(self, agent_id: str = "") -> int:
        """Return the number of suspension entries, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
        return {
            "total_suspensions": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskSuspenderState()
        logger.debug("AgentTaskSuspender reset")
