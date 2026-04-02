"""Agent Workflow Queuer - queues workflows for agents.

Provides a service for queuing workflow requests on behalf of agents,
tracking priority, metadata, and lifecycle of each queued entry.
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
class AgentWorkflowQueuerState:
    """Internal state container for the workflow queuer."""

    entries: dict = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowQueuer:
    """Queues workflows for agents with priority ordering and metadata tracking."""

    PREFIX = "awqu-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowQueuerState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID from data combined with the internal sequence counter."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries by created_at if entries exceed MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._state.entries,
            key=lambda k: self._state.entries[k]["created_at"],
        )
        to_remove = len(self._state.entries) - self.MAX_ENTRIES
        for item_id in sorted_ids[:to_remove]:
            del self._state.entries[item_id]

    # ------------------------------------------------------------------
    # Event firing
    # ------------------------------------------------------------------

    def _fire(self, event: str, data: Any) -> None:
        """Fire event to on_change handler and all registered callbacks."""
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception as exc:
                logger.error("on_change handler error: %s", exc)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.error("Callback '%s' error: %s", name, exc)

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Return the current on_change handler."""
        return self._on_change

    @on_change.setter
    def on_change(self, handler: Optional[Callable]) -> None:
        """Set the on_change handler."""
        self._on_change = handler

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback. Returns True if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def queue_workflow(
        self,
        agent_id: str,
        workflow_name: str,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Queue a workflow for an agent. Returns the record ID.

        Args:
            agent_id: Non-empty identifier for the agent.
            workflow_name: Non-empty name of the workflow.
            priority: Priority value (default 0).
            metadata: Optional metadata dict (deep-copied for isolation).

        Raises:
            ValueError: If agent_id or workflow_name is empty.
        """
        if not agent_id:
            raise ValueError("agent_id must not be empty")
        if not workflow_name:
            raise ValueError("workflow_name must not be empty")

        record_id = self._generate_id(f"{agent_id}{workflow_name}")
        now = time.time()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "priority": priority,
            "metadata": copy.deepcopy(metadata) if metadata is not None else None,
            "created_at": now,
            "_seq": self._state._seq - 1,
        }
        self._prune()
        self._fire("queued", {"record_id": record_id})
        return record_id

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_queued(self, record_id: str) -> Optional[dict]:
        """Return a copy of a queued entry by record_id, or None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_queued_items(self, agent_id: str = "") -> List[dict]:
        """Return all queued items, optionally filtered by agent_id.

        Results are sorted by priority (ascending), then by _seq (ascending).
        """
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(copy.deepcopy(entry))
        results.sort(key=lambda e: (e["priority"], e["_seq"]))
        return results

    def get_queued_count(self, agent_id: str = "") -> int:
        """Return the count of queued items, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        """Return aggregate statistics about the queuer."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_queued": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowQueuerState()
        self._fire("reset", {})
