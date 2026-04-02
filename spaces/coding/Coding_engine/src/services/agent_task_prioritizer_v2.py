"""Agent Task Prioritizer V2 -- prioritizes agent tasks.

Records task prioritizations for agents, tracking priority levels and metadata.
Supports querying, filtering, and statistics.

Usage::

    prioritizer = AgentTaskPrioritizerV2()

    # Prioritize a task
    record_id = prioritizer.prioritize_v2("task-1", "agent-1", priority=8)

    # Query
    entry = prioritizer.get_prioritization(record_id)
    entries = prioritizer.get_prioritizations(agent_id="agent-1")
    stats = prioritizer.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskPrioritizerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskPrioritizerV2:
    """Prioritizes agent tasks (v2)."""

    PREFIX = "atpr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskPrioritizerV2State()
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

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
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
        """Remove a callback by name. Returns True if removed, False if not found."""
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Prioritization operations
    # ------------------------------------------------------------------

    def prioritize_v2(
        self,
        task_id: str,
        agent_id: str,
        priority: int = 5,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a task prioritization.

        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "priority": priority,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._prune()
        self._fire("prioritize_v2", record_id=record_id, task_id=task_id, agent_id=agent_id)
        logger.debug(
            "Task prioritized: %s (task=%s, agent=%s, priority=%d)",
            record_id,
            task_id,
            agent_id,
            priority,
        )
        return record_id

    def get_prioritization(self, record_id: str) -> Optional[dict]:
        """Return the prioritization entry or None."""
        entry = self._state.entries.get(record_id)
        return copy.deepcopy(entry) if entry else None

    def get_prioritizations(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query prioritizations, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(copy.deepcopy(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_prioritization_count(self, agent_id: str = "") -> int:
        """Return the number of prioritization entries, optionally filtered by agent."""
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
            "total_prioritizations": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskPrioritizerV2State()
        self._on_change = None
        logger.debug("AgentTaskPrioritizerV2 reset")
