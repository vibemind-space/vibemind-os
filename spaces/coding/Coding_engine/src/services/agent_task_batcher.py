"""Agent Task Batcher -- batches multiple agent tasks for bulk processing.

Groups multiple task IDs into a single batch record with agent association,
batch size, and metadata. Supports querying, filtering, and statistics.

Usage::

    batcher = AgentTaskBatcher()

    # Batch tasks
    batch_id = batcher.batch(["task-1", "task-2"], "agent-1", batch_size=10)

    # Query
    entry = batcher.get_batch(batch_id)
    entries = batcher.get_batches(agent_id="agent-1")
    stats = batcher.get_stats()
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
class AgentTaskBatcherState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskBatcher:
    """Batches multiple agent tasks for bulk processing."""

    PREFIX = "atbt-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskBatcherState()
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
    # Batch operations
    # ------------------------------------------------------------------

    def batch(
        self,
        task_ids: List[str],
        agent_id: str,
        batch_size: int = 10,
        metadata: dict = None,
    ) -> str:
        """Batch multiple tasks into a single record for bulk processing.

        Returns the batch record ID on success or ``""`` on failure.
        """
        if not task_ids or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        batch_id = self._generate_id()
        self._state.entries[batch_id] = {
            "batch_id": batch_id,
            "task_ids": list(task_ids),
            "agent_id": agent_id,
            "batch_size": batch_size,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("batched", self._state.entries[batch_id])
        logger.debug(
            "Tasks batched: %s (tasks=%s, agent=%s, batch_size=%d)",
            batch_id,
            task_ids,
            agent_id,
            batch_size,
        )
        return batch_id

    def get_batch(self, batch_id: str) -> Optional[dict]:
        """Return the batch entry or None."""
        entry = self._state.entries.get(batch_id)
        return dict(entry) if entry else None

    def get_batches(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query batches, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_batch_count(self, agent_id: str = "") -> int:
        """Return the number of batch entries, optionally filtered by agent."""
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
        total_batch_size = 0
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
            total_batch_size += entry["batch_size"]
            for tid in entry["task_ids"]:
                unique_tasks.add(tid)
        return {
            "total_batches": len(self._state.entries),
            "unique_agents": len(unique_agents),
            "unique_tasks": len(unique_tasks),
            "total_batch_size": total_batch_size,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskBatcherState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskBatcher reset")
