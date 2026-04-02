"""Agent Workflow Rollback – manages rollback points and execution for agent
workflows.

Creates checkpoints that capture workflow state at specific points, supports
rolling back to a previous checkpoint, querying by agent and workflow name,
and collecting statistics.
Uses SHA-256-based IDs with an ``awrb-`` prefix.
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
class AgentWorkflowRollbackState:
    """Internal store for workflow rollback entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowRollback:
    """Manages rollback points and execution for agent workflows.

    Supports creating checkpoints, rolling back to a previous state,
    retrieving and removing checkpoints, with automatic pruning when
    the store exceeds *MAX_ENTRIES*.
    """

    PREFIX = "awrb-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowRollbackState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict the oldest entries when the store exceeds *MAX_ENTRIES*."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(), key=lambda kv: kv[1].get("created_at", 0)
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently ignored."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Create checkpoint
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        agent_id: str,
        workflow_name: str,
        state: dict,
        label: str = "",
    ) -> str:
        """Create a rollback checkpoint for an agent workflow.

        Returns the checkpoint ID (``awrb-`` prefix).
        """
        self._prune()
        checkpoint_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "state": copy.deepcopy(state),
            "label": label,
            "created_at": now,
            "rolled_back": False,
            "seq": self._state._seq,
        }
        self._state.entries[checkpoint_id] = entry
        self._fire("checkpoint_created", entry)
        logger.debug(
            "Checkpoint created: %s for agent=%s workflow=%s",
            checkpoint_id, agent_id, workflow_name,
        )
        return checkpoint_id

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self, checkpoint_id: str) -> dict:
        """Mark a checkpoint as rolled back and return its state.

        Returns ``{"checkpoint_id", "state", "rolled_back": True}``.
        Raises ``KeyError`` if the checkpoint is not found.
        """
        entry = self._state.entries.get(checkpoint_id)
        if entry is None:
            raise KeyError(f"Checkpoint not found: {checkpoint_id}")
        entry["rolled_back"] = True
        self._fire("rollback_executed", entry)
        logger.debug("Rollback executed: %s", checkpoint_id)
        return {
            "checkpoint_id": checkpoint_id,
            "state": copy.deepcopy(entry["state"]),
            "rolled_back": True,
        }

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_checkpoint(self, checkpoint_id: str) -> Optional[dict]:
        """Get checkpoint by ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(checkpoint_id)
        if entry is None:
            return None
        return dict(entry)

    def get_checkpoints(
        self,
        agent_id: str,
        workflow_name: str = "",
    ) -> List[Dict[str, Any]]:
        """Query checkpoints for an agent, newest first.

        Optionally filter by *workflow_name*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if e["agent_id"] == agent_id
            and (not workflow_name or e["workflow_name"] == workflow_name)
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates]

    def get_latest_checkpoint(
        self, agent_id: str, workflow_name: str
    ) -> Optional[dict]:
        """Get the most recent checkpoint for an agent+workflow.

        Returns ``None`` if no matching checkpoint exists.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["workflow_name"] == workflow_name
        ]
        if not candidates:
            return None
        latest = max(
            candidates, key=lambda e: (e.get("created_at", 0), e.get("seq", 0))
        )
        return dict(latest)

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_checkpoint_count(self, agent_id: str = "") -> int:
        """Return the number of stored checkpoints, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def remove_checkpoint(self, checkpoint_id: str) -> bool:
        """Remove a checkpoint by ID.  Returns ``False`` if not found."""
        entry = self._state.entries.pop(checkpoint_id, None)
        if entry is None:
            return False
        self._fire("checkpoint_removed", entry)
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the rollback service."""
        total_rollbacks = sum(
            1 for e in self._state.entries.values() if e.get("rolled_back")
        )
        return {
            "total_checkpoints": len(self._state.entries),
            "total_rollbacks": total_rollbacks,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored checkpoints, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
