"""Agent Task Cloner -- clones agent tasks for parallel execution.

Clones agent tasks so they can be executed in parallel across multiple agents
or contexts. Supports querying, filtering, and statistics.

Usage::

    cloner = AgentTaskCloner()

    # Clone a task
    record_id = cloner.clone("task-1", "agent-1", clone_count=3)

    # Query
    entry = cloner.get_clone(record_id)
    entries = cloner.get_clones(agent_id="agent-1")
    stats = cloner.get_stats()
"""

from __future__ import annotations

import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskClonerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskCloner:
    """Clones agent tasks for parallel execution."""

    PREFIX = "atcl-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskClonerState()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        quarter = max(1, len(sorted_keys) // 4)
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

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
        """Remove a callback by name. Returns True if removed, False if not found."""
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Clone operations
    # ------------------------------------------------------------------

    def clone(
        self,
        task_id: str,
        agent_id: str,
        clone_count: int = 1,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a clone operation for a task.

        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""
        if clone_count < 1:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "clone_count": clone_count,
            "metadata": dict(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("clone", self._state.entries[record_id])
        logger.debug(
            "Task cloned: %s (task=%s, agent=%s, count=%d)",
            record_id,
            task_id,
            agent_id,
            clone_count,
        )
        return record_id

    def get_clone(self, record_id: str) -> Optional[dict]:
        """Return the clone entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_clones(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query clones, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_clone_count(self, agent_id: str = "") -> int:
        """Return the number of clone entries, optionally filtered by agent."""
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
            "total_clones": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskClonerState()
        logger.debug("AgentTaskCloner reset")
