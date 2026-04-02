"""Agent Task Delegator V2 -- delegates tasks between agents with simplified interface.

Tracks delegation records supporting querying, filtering, and aggregate statistics.

Usage::

    delegator = AgentTaskDelegatorV2()

    # Create a delegation
    record_id = delegator.delegate_v2("task-1", "planner", target_agent="builder")

    # Query
    entry = delegator.get_delegation(record_id)
    delegations = delegator.get_delegations(agent_id="planner")
    stats = delegator.get_stats()
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
class AgentTaskDelegatorV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskDelegatorV2:
    """Delegates tasks between agents (v2)."""

    PREFIX = "atdv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskDelegatorV2State()
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
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k].get("_seq", 0),
            ),
        )
        quarter = max(1, len(self._state.entries) // 4)
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]

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

    def _fire(self, action: str, **detail: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, **detail)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, **detail)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Delegation operations
    # ------------------------------------------------------------------

    def delegate_v2(
        self,
        task_id: str,
        agent_id: str,
        target_agent: str = "",
        metadata: dict | None = None,
    ) -> str:
        """Create a delegation record.

        Returns the record ID on success or ``""`` if task_id or agent_id is empty.
        """
        if not task_id or not agent_id:
            return ""

        self._prune()

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "target_agent": target_agent,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._fire("delegation_created", record_id=record_id, task_id=task_id)
        logger.debug(
            "Delegation created: %s (task=%s, agent=%s, target=%s)",
            record_id,
            task_id,
            agent_id,
            target_agent,
        )
        return record_id

    def get_delegation(self, record_id: str) -> Optional[dict]:
        """Return the delegation entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_delegations(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        """Query delegations, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(
            key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True
        )
        return results[:limit]

    def get_delegation_count(self, agent_id: str = "") -> int:
        """Return the number of delegations, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if e["agent_id"] == agent_id:
                count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        agents: set[str] = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_delegations": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskDelegatorV2State()
        self._on_change = None
        logger.debug("AgentTaskDelegatorV2 reset")
