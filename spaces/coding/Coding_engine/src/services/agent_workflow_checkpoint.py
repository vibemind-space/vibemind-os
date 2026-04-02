"""Agent Workflow Checkpoint -- manages named checkpoints in agent workflows
for save/restore functionality.

Saves and restores named checkpoints keyed by agent, workflow, and checkpoint name.
Supports querying, deletion, pruning, and collecting statistics.
Uses SHA-256-based IDs with an ``awcp-`` prefix.
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
class AgentWorkflowCheckpointState:
    """Internal store for workflow checkpoint entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowCheckpoint:
    """Manages named checkpoints within agent workflows.

    Supports creating, restoring, querying, and removing checkpoints
    with automatic pruning when the store exceeds *MAX_ENTRIES*.
    """

    PREFIX = "awcp-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowCheckpointState()
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
        checkpoint_name: str,
        state: dict,
    ) -> str:
        """Save a checkpoint for an agent workflow.

        Returns the checkpoint ID (``awcp-`` prefix).
        """
        self._prune()
        checkpoint_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "checkpoint_name": checkpoint_name,
            "state": copy.deepcopy(state),
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[checkpoint_id] = entry
        self._fire("checkpoint_created", entry)
        logger.debug(
            "Checkpoint created: %s for agent=%s workflow=%s checkpoint=%s",
            checkpoint_id, agent_id, workflow_name, checkpoint_name,
        )
        return checkpoint_id

    # ------------------------------------------------------------------
    # Get checkpoint by ID
    # ------------------------------------------------------------------

    def get_checkpoint(self, checkpoint_id: str) -> Optional[dict]:
        """Get a checkpoint by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(checkpoint_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get checkpoints (query)
    # ------------------------------------------------------------------

    def get_checkpoints(
        self,
        agent_id: str,
        workflow_name: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query checkpoints for an agent, newest first.

        Optionally filter by *workflow_name* and cap results with *limit*.
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
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Restore checkpoint
    # ------------------------------------------------------------------

    def restore_checkpoint(self, checkpoint_id: str) -> Optional[dict]:
        """Restore a checkpoint by ID.  Returns a deep copy of the stored state,
        or ``None`` if not found.
        """
        entry = self._state.entries.get(checkpoint_id)
        if entry is None:
            return None
        self._fire("checkpoint_restored", entry)
        return copy.deepcopy(entry["state"])

    # ------------------------------------------------------------------
    # Remove checkpoint
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

    def get_stats(self) -> dict:
        """Return operational statistics for the checkpoint service."""
        agents = set()
        workflows = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
            workflows.add(entry["workflow_name"])
        return {
            "total_checkpoints": len(self._state.entries),
            "unique_agents": len(agents),
            "unique_workflows": len(workflows),
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
