"""Agent Task Grouper -- groups related agent tasks into named groups.

Groups multiple task IDs into a single group record with agent association,
group name, and metadata. Supports querying, filtering, and statistics.

Usage::

    grouper = AgentTaskGrouper()

    # Group tasks
    group_id = grouper.group(["task-1", "task-2"], "agent-1", group_name="batch-a")

    # Query
    entry = grouper.get_group(group_id)
    entries = grouper.get_groups(agent_id="agent-1")
    stats = grouper.get_stats()
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
class AgentTaskGrouperState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskGrouper:
    """Groups related agent tasks into named groups."""

    PREFIX = "atgr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskGrouperState()
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
    # Group operations
    # ------------------------------------------------------------------

    def group(
        self,
        task_ids: List[str],
        agent_id: str,
        group_name: str = "",
        metadata: dict = None,
    ) -> str:
        """Group multiple tasks into a single record.

        Returns the group ID on success or ``""`` on failure.
        """
        if not task_ids or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        group_id = self._generate_id()
        self._state.entries[group_id] = {
            "group_id": group_id,
            "task_ids": list(task_ids),
            "agent_id": agent_id,
            "group_name": group_name,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("grouped", self._state.entries[group_id])
        logger.debug(
            "Tasks grouped: %s (tasks=%s, agent=%s, group_name=%s)",
            group_id,
            task_ids,
            agent_id,
            group_name,
        )
        return group_id

    def get_group(self, group_id: str) -> Optional[dict]:
        """Return the group entry or None."""
        entry = self._state.entries.get(group_id)
        return dict(entry) if entry else None

    def get_groups(
        self, agent_id: str = "", group_name: str = "", limit: int = 50
    ) -> List[dict]:
        """Query groups, newest first.

        Optionally filter by agent_id and/or group_name.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if group_name and entry["group_name"] != group_name:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_group_count(self, agent_id: str = "") -> int:
        """Return the number of group entries, optionally filtered by agent."""
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
        unique_group_names = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
            if entry["group_name"]:
                unique_group_names.add(entry["group_name"])
            for tid in entry["task_ids"]:
                unique_tasks.add(tid)
        return {
            "total_groups": len(self._state.entries),
            "unique_agents": len(unique_agents),
            "unique_tasks": len(unique_tasks),
            "unique_group_names": len(unique_group_names),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskGrouperState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskGrouper reset")
