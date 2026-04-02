"""Agent Workflow Scaler – service module for scaling agent workflows.

Manages workflow scaling records for agents, supports querying by agent,
collecting statistics, and automatic pruning when the store exceeds
*MAX_ENTRIES*.  Uses SHA-256-based IDs with an ``awsc-`` prefix.
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
class AgentWorkflowScalerState:
    """Internal store for workflow scaler entries."""

    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowScaler:
    """Manages scaling of agent workflows.

    Supports creating, retrieving, and querying scaling records with automatic
    pruning when the store exceeds *MAX_ENTRIES*.
    """

    PREFIX = "awsc-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowScalerState()
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
        """Evict the oldest quarter of entries when the store exceeds *MAX_ENTRIES*."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(),
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("_seq", 0)),
        )
        remove_count = len(self._state.entries) // 4
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, **detail: Any) -> None:
        """Invoke on_change and all registered callbacks; exceptions are silently ignored."""
        if self._on_change is not None:
            try:
                self._on_change(action, detail)
            except Exception:
                pass
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
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
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Scale
    # ------------------------------------------------------------------

    def scale(
        self,
        agent_id: str,
        workflow_name: str,
        factor: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> str:
        """Scale an agent workflow.

        Returns the record ID (``awsc-`` prefix), or ``""`` if inputs are invalid.
        """
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "factor": factor,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("scale", record_id=record_id, agent_id=agent_id, workflow_name=workflow_name)
        logger.debug(
            "Scaling recorded: %s for agent=%s workflow=%s factor=%s",
            record_id,
            agent_id,
            workflow_name,
            factor,
        )
        return record_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_scaling(self, record_id: str) -> Optional[dict]:
        """Get scaling record by record ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_scalings(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query scaling records, optionally filtered by *agent_id*, newest first.

        Returns at most *limit* results as copies.
        """
        if agent_id:
            candidates = [
                e
                for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            ]
        else:
            candidates = list(self._state.entries.values())
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_scaling_count(self, agent_id: str = "") -> int:
        """Return the number of stored scaling records, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the scaler service."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_scalings": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored scaling records and reset state."""
        self._state = AgentWorkflowScalerState()
        self._on_change = None
