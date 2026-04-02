"""Agent Workflow State – persists current state of workflows agents execute.

Part of the emergent pipeline system. Manages per-agent, per-workflow state
snapshots with history tracking, change callbacks, and thread-safe access.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class _WorkflowState:
    state_id: str
    agent_id: str
    workflow_id: str
    state_data: Dict[str, Any]
    step: str
    metadata: Dict[str, Any]
    created_at: float
    updated_at: float


class AgentWorkflowState:
    """Manages agent workflow state with persistence and history."""

    def __init__(self, max_entries: int = 10000):
        self._states: Dict[str, _WorkflowState] = {}  # keyed by agent_id:workflow_id
        self._history: Dict[str, List[Dict[str, Any]]] = {}  # keyed same
        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._seq = 0

        # stats
        self._total_saves = 0
        self._total_deletes = 0
        self._total_clears = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_key(self, agent_id: str, workflow_id: str) -> str:
        return f"{agent_id}:{workflow_id}"

    def _generate_id(self, agent_id: str, workflow_id: str) -> str:
        self._seq += 1
        raw = f"{agent_id}-{workflow_id}-{time.time()}-{self._seq}"
        return "aws-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _state_to_dict(self, s: _WorkflowState) -> Dict[str, Any]:
        return {
            "state_id": s.state_id,
            "agent_id": s.agent_id,
            "workflow_id": s.workflow_id,
            "state_data": dict(s.state_data),
            "step": s.step,
            "metadata": dict(s.metadata),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }

    def _append_history(self, key: str, state: _WorkflowState) -> None:
        if key not in self._history:
            self._history[key] = []
        self._history[key].append({
            "state_id": state.state_id,
            "state_data": dict(state.state_data),
            "step": state.step,
            "metadata": dict(state.metadata),
            "timestamp": state.updated_at,
        })

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def save_state(
        self,
        agent_id: str,
        workflow_id: str,
        state_data: Dict[str, Any],
        step: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save workflow state. Returns state_id. Overwrites if same agent+workflow."""
        if not agent_id or not workflow_id:
            logger.warning("save_state called with empty agent_id or workflow_id")
            return ""

        with self._lock:
            key = self._make_key(agent_id, workflow_id)
            now = time.time()
            existing = self._states.get(key)

            if existing is None and len(self._states) >= self._max_entries:
                logger.warning("max_entries (%d) reached, rejecting save", self._max_entries)
                return ""

            state_id = self._generate_id(agent_id, workflow_id)

            if existing:
                existing.state_id = state_id
                existing.state_data = dict(state_data)
                existing.step = step
                existing.metadata = dict(metadata) if metadata else existing.metadata
                existing.updated_at = now
                state_obj = existing
            else:
                state_obj = _WorkflowState(
                    state_id=state_id,
                    agent_id=agent_id,
                    workflow_id=workflow_id,
                    state_data=dict(state_data),
                    step=step,
                    metadata=dict(metadata) if metadata else {},
                    created_at=now,
                    updated_at=now,
                )
                self._states[key] = state_obj

            self._append_history(key, state_obj)
            self._total_saves += 1

        logger.debug("Saved state %s for agent=%s workflow=%s", state_id, agent_id, workflow_id)
        self._fire("state_saved", {
            "state_id": state_id,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "step": step,
        })
        return state_id

    def get_state(self, agent_id: str, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get current state for an agent+workflow pair."""
        with self._lock:
            key = self._make_key(agent_id, workflow_id)
            s = self._states.get(key)
            if s is None:
                return None
            return self._state_to_dict(s)

    def get_agent_states(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get all workflow states for a given agent."""
        results: List[Dict[str, Any]] = []
        with self._lock:
            for s in self._states.values():
                if s.agent_id == agent_id:
                    results.append(self._state_to_dict(s))
        return results

    def delete_state(self, agent_id: str, workflow_id: str) -> bool:
        """Delete a workflow state. Returns False if not found."""
        with self._lock:
            key = self._make_key(agent_id, workflow_id)
            removed = self._states.pop(key, None)
            if removed is None:
                return False
            self._total_deletes += 1

        logger.debug("Deleted state for agent=%s workflow=%s", agent_id, workflow_id)
        self._fire("state_deleted", {"agent_id": agent_id, "workflow_id": workflow_id})
        return True

    def get_state_history(
        self,
        agent_id: str,
        workflow_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get state change history for an agent+workflow pair."""
        with self._lock:
            key = self._make_key(agent_id, workflow_id)
            entries = self._history.get(key, [])
            return list(entries[-limit:])

    def clear_agent_states(self, agent_id: str) -> int:
        """Clear all states for a given agent. Returns count removed."""
        with self._lock:
            keys_to_remove = [
                k for k, s in self._states.items() if s.agent_id == agent_id
            ]
            for k in keys_to_remove:
                del self._states[k]
            count = len(keys_to_remove)
            if count:
                self._total_clears += 1

        if count:
            logger.debug("Cleared %d states for agent=%s", count, agent_id)
            self._fire("agent_cleared", {"agent_id": agent_id, "count": count})
        return count

    # ------------------------------------------------------------------
    # Listing / Counting
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """List all agents that have saved states."""
        with self._lock:
            agents = sorted({s.agent_id for s in self._states.values()})
        return agents

    def list_workflows(self, agent_id: Optional[str] = None) -> List[str]:
        """List all workflow IDs, optionally filtered by agent."""
        with self._lock:
            if agent_id:
                workflows = sorted(
                    {s.workflow_id for s in self._states.values() if s.agent_id == agent_id}
                )
            else:
                workflows = sorted({s.workflow_id for s in self._states.values()})
        return workflows

    def get_state_count(self, agent_id: Optional[str] = None) -> int:
        """Count states, optionally filtered by agent."""
        with self._lock:
            if agent_id:
                return sum(1 for s in self._states.values() if s.agent_id == agent_id)
            return len(self._states)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._callbacks[name] = callback
        logger.debug("Registered callback: %s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback. Returns False if not found."""
        with self._lock:
            removed = self._callbacks.pop(name, None)
        return removed is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Fire all registered callbacks."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                logger.exception("Callback error during %s", action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            agents = len({s.agent_id for s in self._states.values()})
            workflows = len({s.workflow_id for s in self._states.values()})
            return {
                "current_states": len(self._states),
                "max_entries": self._max_entries,
                "agents": agents,
                "workflows": workflows,
                "history_keys": len(self._history),
                "total_saves": self._total_saves,
                "total_deletes": self._total_deletes,
                "total_clears": self._total_clears,
                "callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Reset all state, history, callbacks, and counters."""
        with self._lock:
            self._states.clear()
            self._history.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_saves = 0
            self._total_deletes = 0
            self._total_clears = 0
        logger.info("AgentWorkflowState reset")
