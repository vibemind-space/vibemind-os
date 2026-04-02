"""Agent Workflow Forker -- forks agent workflows into named branches.

Forks an agent workflow into a named branch with metadata tracking.
Supports querying, filtering, and statistics.

Usage::

    forker = AgentWorkflowForker()

    # Fork a workflow
    record_id = forker.fork("agent-1", "build-pipeline", "experiment-a")

    # Query
    entry = forker.get_fork(record_id)
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
class AgentWorkflowForkerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowForker:
    """Forks agent workflows into named branches."""

    PREFIX = "awfk-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowForkerState()
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
    # Fork operations
    # ------------------------------------------------------------------

    def fork(
        self,
        agent_id: str,
        workflow_name: str,
        branch_name: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Fork a workflow into a named branch.

        Returns the record ID on success or ``""`` on failure.
        """
        if not agent_id or not workflow_name or not branch_name:
            return ""

        record_id = self._generate_id()
        now = time.time()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "branch_name": branch_name,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("forked", entry)
        logger.debug(
            "Workflow forked: %s (agent=%s, workflow=%s, branch=%s)",
            record_id,
            agent_id,
            workflow_name,
            branch_name,
        )
        return record_id

    def get_fork(self, record_id: str) -> Optional[dict]:
        """Return the fork entry or None."""
        entry = self._state.entries.get(record_id)
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
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
        return {
            "total_forks": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowForkerState()
        self._on_change = None
        logger.debug("AgentWorkflowForker reset")
