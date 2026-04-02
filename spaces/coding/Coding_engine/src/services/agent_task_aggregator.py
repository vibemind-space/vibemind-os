"""Agent Task Aggregator -- aggregating agent tasks.

Manages task aggregation records, grouping multiple task IDs
under a single agent with label and metadata tracking.
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
class AgentTaskAggregatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskAggregator:
    """Aggregates agent tasks into grouped records."""

    PREFIX = "atag-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskAggregatorState()
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
    # Aggregation operations
    # ------------------------------------------------------------------

    def aggregate(
        self,
        task_ids: list,
        agent_id: str,
        label: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create an aggregation record.

        Groups multiple task IDs under a single agent with an optional
        label and metadata.  Returns the record ID on success or ``""``
        on failure.
        """
        if not task_ids or not agent_id:
            return ""

        now = time.time()
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "task_ids": list(task_ids),
            "agent_id": agent_id,
            "label": label,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("aggregated", entry)
        logger.debug(
            "Tasks aggregated: %s for agent %s (%d tasks)",
            record_id,
            agent_id,
            len(task_ids),
        )
        return record_id

    def get_aggregation(self, record_id: str) -> Optional[dict]:
        """Return the aggregation entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_aggregations(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query aggregations, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_aggregation_count(self, agent_id: str = "") -> int:
        """Return the number of aggregations matching optional filters."""
        count = 0
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total_aggregations = len(self._state.entries)
        unique_agents: set = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
        return {
            "total_aggregations": total_aggregations,
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskAggregatorState()
        self._on_change = None
        logger.debug("AgentTaskAggregator reset")
