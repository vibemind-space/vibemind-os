"""Agent Task Forker -- forks a task into multiple parallel subtasks.

Forks a task into parallel subtasks with configurable strategy and agent association.
Supports querying, filtering, and statistics.

Usage::

    forker = AgentTaskForker()

    # Fork a task
    fork_id = forker.fork("task-1", "agent-1", fork_count=3, strategy="clone")

    # Query
    entry = forker.get_fork(fork_id)
    entries = forker.get_forks(agent_id="agent-1")
    stats = forker.get_stats()
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
class AgentTaskForkerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskForker:
    """Forks a task into multiple parallel subtasks."""

    PREFIX = "atfk-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskForkerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

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
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
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
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Fork operations
    # ------------------------------------------------------------------

    def fork(
        self,
        task_id: str,
        agent_id: str,
        fork_count: int = 2,
        strategy: str = "clone",
        metadata: dict = None,
    ) -> str:
        """Fork a task into parallel subtasks.

        Returns the fork record ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""
        if fork_count < 1:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        fork_id = self._generate_id()
        subtask_ids = [f"{fork_id}-sub-{i}" for i in range(fork_count)]
        self._state.entries[fork_id] = {
            "fork_id": fork_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "fork_count": fork_count,
            "subtask_ids": subtask_ids,
            "strategy": strategy,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("fork", self._state.entries[fork_id])
        logger.debug(
            "Task forked: %s (task=%s, agent=%s, count=%d, strategy=%s)",
            fork_id,
            task_id,
            agent_id,
            fork_count,
            strategy,
        )
        return fork_id

    def get_fork(self, fork_id: str) -> Optional[dict]:
        """Return the fork entry or None."""
        entry = self._state.entries.get(fork_id)
        return dict(entry) if entry else None

    def get_forks(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query forks, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_fork_count(self, agent_id: str = "") -> int:
        """Return the number of fork entries, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents = set()
        unique_tasks = set()
        total_subtasks = 0
        strategies = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
            unique_tasks.add(entry["task_id"])
            total_subtasks += entry["fork_count"]
            strategies.add(entry["strategy"])
        return {
            "total_forks": len(self._state.entries),
            "unique_agents": len(unique_agents),
            "unique_tasks": len(unique_tasks),
            "total_subtasks": total_subtasks,
            "strategies": len(strategies),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskForkerState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskForker reset")
