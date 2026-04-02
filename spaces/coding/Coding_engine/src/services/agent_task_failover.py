"""Agent Task Failover -- handles task failover for agents.

Allows failing over tasks from one agent to another with reason and metadata,
querying failovers, and tracking statistics.

Usage::

    failover_svc = AgentTaskFailover()

    # Failover a task
    record_id = failover_svc.failover("task-1", "agent-a", "agent-b", reason="crashed")

    # Query
    entry = failover_svc.get_failover(record_id)
    entries = failover_svc.get_failovers(from_agent="agent-a")
    stats = failover_svc.get_stats()
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
class AgentTaskFailoverState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskFailover:
    """Handles task failover for agents."""

    PREFIX = "atfo-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskFailoverState()
        self._on_change: Optional[Callable] = None

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
        remove_count = len(entries) - self.MAX_ENTRIES + len(entries) // 4
        for key in sorted_keys[:remove_count]:
            del entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for name, cb in list(self._state.callbacks.items()):
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
    # Core operations
    # ------------------------------------------------------------------

    def failover(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Failover a task from one agent to another.

        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not from_agent or not to_agent:
            return ""

        self._prune()

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("failover", self._state.entries[record_id])
        logger.debug(
            "Task failover: %s (task=%s, from=%s, to=%s, reason=%s)",
            record_id,
            task_id,
            from_agent,
            to_agent,
            reason,
        )
        return record_id

    def get_failover(self, record_id: str) -> Optional[dict]:
        """Return the failover entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_failovers(
        self, from_agent: str = "", limit: int = 50
    ) -> List[dict]:
        """Query failovers, newest first.

        Optionally filter by from_agent.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if from_agent and entry["from_agent"] != from_agent:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_failover_count(self, from_agent: str = "") -> int:
        """Return the number of failover entries, optionally filtered by from_agent."""
        if not from_agent:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["from_agent"] == from_agent
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["from_agent"])
            unique_agents.add(entry["to_agent"])
        return {
            "total_failovers": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskFailoverState()
        self._on_change = None
        logger.debug("AgentTaskFailover reset")
