"""Agent Workflow History -- records history of agent workflow executions.

Tracks per-agent workflow executions with timing, status, and metadata.
Provides duration analytics, execution counting, and searchable history.

Usage::

    history = AgentWorkflowHistory()

    # Record an execution
    exec_id = history.record_execution("agent-1", "deploy", status="success", duration_ms=1200)

    # Query
    record = history.get_execution(exec_id)
    hist = history.get_history("agent-1")
    avg = history.get_average_duration("agent-1", "deploy")
    stats = history.get_stats()
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentWorkflowHistoryState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowHistory:
    """Records history of agent workflow executions with timing and outcomes."""

    PREFIX = "awh-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowHistoryState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        self._state._seq += 1
        raw = f"{data}-{time.time()}-{self._state._seq}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"{self.PREFIX}{h}"

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, fn):
        self._on_change = fn

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_execution(
        self,
        agent_id: str,
        workflow_name: str,
        status: str = "success",
        duration_ms: int = 0,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a workflow execution. Returns the execution ID."""
        self._state._seq += 1
        execution_id = self._generate_id(f"{agent_id}:{workflow_name}")
        entry = {
            "execution_id": execution_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "status": status,
            "duration_ms": duration_ms,
            "metadata": metadata or {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[execution_id] = entry
        self._prune()
        self._fire("execution_recorded", entry)
        return execution_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_execution(self, execution_id: str) -> dict:
        """Return a single execution record by ID, or None if not found."""
        return self._state.entries.get(execution_id)

    def get_history(
        self,
        agent_id: str,
        workflow_name: str = "",
        status: str = "",
        limit: int = 50,
    ) -> list:
        """Query history newest first with optional filters."""
        results = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id
            and (not workflow_name or e["workflow_name"] == workflow_name)
            and (not status or e["status"] == status)
        ]
        results.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_latest_execution(self, agent_id: str, workflow_name: str) -> dict:
        """Return the most recent execution for agent+workflow, or None."""
        matches = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["workflow_name"] == workflow_name
        ]
        if not matches:
            return None
        return max(matches, key=lambda x: (x.get("created_at", 0), x.get("_seq", 0)))

    def get_execution_count(self, agent_id: str = "", status: str = "") -> int:
        """Return the number of executions matching optional filters."""
        if not agent_id and not status:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if (not agent_id or e["agent_id"] == agent_id)
            and (not status or e["status"] == status)
        )

    def get_average_duration(self, agent_id: str, workflow_name: str) -> float:
        """Return average duration_ms for agent+workflow. 0.0 if none."""
        matches = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["workflow_name"] == workflow_name
        ]
        if not matches:
            return 0.0
        total = sum(e["duration_ms"] for e in matches)
        return total / len(matches)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def clear_history(self, agent_id: str) -> int:
        """Remove all executions for an agent. Return count removed."""
        to_remove = [
            k for k, v in self._state.entries.items()
            if v["agent_id"] == agent_id
        ]
        for k in to_remove:
            del self._state.entries[k]
        if to_remove:
            self._fire("history_cleared", {"agent_id": agent_id, "count": len(to_remove)})
        return len(to_remove)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        entries = list(self._state.entries.values())
        agents = set(e["agent_id"] for e in entries)
        success_count = sum(1 for e in entries if e["status"] == "success")
        failure_count = sum(1 for e in entries if e["status"] == "failure")
        return {
            "total_executions": len(entries),
            "unique_agents": len(agents),
            "success_count": success_count,
            "failure_count": failure_count,
        }

    def reset(self):
        """Clear all state, callbacks, and counters."""
        self._state = AgentWorkflowHistoryState()
        self._callbacks = {}
        self._on_change = None
