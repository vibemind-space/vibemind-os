"""Agent Task Merger -- merges multiple agent tasks into a single combined task.

Combines multiple task IDs into a single merge record with agent association,
label, and metadata. Supports querying, filtering, and statistics.

Usage::

    merger = AgentTaskMerger()

    # Merge tasks
    merge_id = merger.merge(["task-1", "task-2"], "agent-1", label="combined")

    # Query
    entry = merger.get_merge(merge_id)
    entries = merger.get_merges(agent_id="agent-1")
    stats = merger.get_stats()
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
class AgentTaskMergerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskMerger:
    """Merges multiple agent tasks into a single combined task."""

    PREFIX = "atmg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskMergerState()
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
    # Merge operations
    # ------------------------------------------------------------------

    def merge(
        self,
        task_ids: List[str],
        agent_id: str,
        label: str = "",
        metadata: dict = None,
    ) -> str:
        """Merge multiple tasks into a single record.

        Returns the merge ID on success or ``""`` on failure.
        """
        if not task_ids or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        merge_id = self._generate_id()
        self._state.entries[merge_id] = {
            "merge_id": merge_id,
            "task_ids": list(task_ids),
            "agent_id": agent_id,
            "label": label,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("merged", self._state.entries[merge_id])
        logger.debug(
            "Tasks merged: %s (tasks=%s, agent=%s)",
            merge_id,
            task_ids,
            agent_id,
        )
        return merge_id

    def get_merge(self, merge_id: str) -> Optional[dict]:
        """Return the merge entry or None."""
        entry = self._state.entries.get(merge_id)
        return dict(entry) if entry else None

    def get_merges(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query merges, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_merge_count(self, agent_id: str = "") -> int:
        """Return the number of merge entries, optionally filtered by agent."""
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
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
            for tid in entry["task_ids"]:
                unique_tasks.add(tid)
        return {
            "total_merges": len(self._state.entries),
            "unique_agents": len(unique_agents),
            "unique_tasks": len(unique_tasks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskMergerState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskMerger reset")
