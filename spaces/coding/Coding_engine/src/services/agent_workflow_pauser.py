"""Agent Workflow Pauser -- pauses and resumes workflow execution.

Manages pause records for agent workflows.  Each pause captures the agent,
workflow name, reason, and optional metadata.  Paused workflows can later be
resumed.  When the store exceeds ``MAX_ENTRIES`` the oldest quarter of entries
is pruned automatically.

Uses SHA-256-based IDs with an ``awpa-`` prefix.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowPauserState:
    """Internal store for workflow pause entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowPauser:
    """Pauses and resumes workflow execution for agents.

    Each pause record tracks which agent paused which workflow, along with an
    optional reason and metadata.  Records can be resumed individually.
    """

    PREFIX = "awpa-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowPauserState()
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
        """Remove the oldest quarter of entries when at capacity."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(),
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("seq", 0)),
        )
        remove_count = len(sorted_entries) // 4
        if remove_count < 1:
            remove_count = 1
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
    # Pause workflow
    # ------------------------------------------------------------------

    def pause(
        self,
        agent_id: str,
        workflow_name: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Pause a workflow for an agent.

        Returns the pause record ID (``awpa-`` prefix).
        """
        self._prune()
        record_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "reason": reason,
            "metadata": metadata or {},
            "status": "paused",
            "created_at": now,
            "resumed_at": None,
            "seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._fire("paused", entry)
        logger.debug(
            "Workflow paused: %s agent=%s workflow=%s reason=%s",
            record_id, agent_id, workflow_name, reason,
        )
        return record_id

    # ------------------------------------------------------------------
    # Resume workflow
    # ------------------------------------------------------------------

    def resume_workflow(self, record_id: str) -> bool:
        """Mark a paused workflow as resumed.

        Returns ``True`` if the record was found and resumed, ``False``
        otherwise (not found or already resumed).
        """
        entry = self._state.entries.get(record_id)
        if entry is None:
            return False
        if entry["status"] != "paused":
            return False
        entry["status"] = "resumed"
        entry["resumed_at"] = time.time()
        self._fire("resumed", entry)
        logger.debug("Workflow resumed: %s", record_id)
        return True

    # ------------------------------------------------------------------
    # Get pause by ID
    # ------------------------------------------------------------------

    def get_pause(self, record_id: str) -> Optional[dict]:
        """Get a pause record by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get pauses (query)
    # ------------------------------------------------------------------

    def get_pauses(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query pause records, newest first.

        Optionally filter by *agent_id* and cap results with *limit*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if not agent_id or e["agent_id"] == agent_id
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get pause count
    # ------------------------------------------------------------------

    def get_pause_count(self, agent_id: str = "") -> int:
        """Return the number of pause records, optionally filtered by *agent_id*."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the pauser service."""
        total = len(self._state.entries)
        paused = sum(1 for e in self._state.entries.values() if e["status"] == "paused")
        resumed = sum(1 for e in self._state.entries.values() if e["status"] == "resumed")
        return {
            "total_pauses": total,
            "active_pauses": paused,
            "resumed_pauses": resumed,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored pause records, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
