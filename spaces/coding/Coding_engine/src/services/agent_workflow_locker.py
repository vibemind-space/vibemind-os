"""Agent Workflow Locker -- locks workflows for agents.

Stores lock records for agent workflows.  Each record captures the agent,
workflow name, reason, and optional metadata.  When the store exceeds
``MAX_ENTRIES`` the oldest quarter of entries is pruned automatically.

Uses SHA-256-based IDs with an ``awlk-`` prefix.
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
class AgentWorkflowLockerState:
    """Internal store for workflow lock entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowLocker:
    """Locks workflows for agents.

    Each lock record tracks which agent locked which workflow, along with
    the reason and optional metadata.  Records can be queried by agent.
    """

    PREFIX = "awlk-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowLockerState()
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
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("_seq", 0)),
        )
        remove_count = len(sorted_entries) // 4
        if remove_count < 1:
            remove_count = 1
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently ignored."""
        for cb in list(self._state.callbacks.values()):
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
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Lock workflow
    # ------------------------------------------------------------------

    def lock(
        self,
        agent_id: str,
        workflow_name: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Lock a workflow for an agent.

        Returns the record ID (``awlk-`` prefix).

        Returns ``""`` if *agent_id* or *workflow_name* is empty.
        """
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("locked", entry)
        logger.debug(
            "Workflow locked: %s agent=%s workflow=%s reason=%s",
            record_id, agent_id, workflow_name, reason,
        )
        return record_id

    # ------------------------------------------------------------------
    # Get lock by ID
    # ------------------------------------------------------------------

    def get_lock(self, record_id: str) -> Optional[dict]:
        """Get a lock record by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get locks (query)
    # ------------------------------------------------------------------

    def get_locks(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query lock records, newest first.

        Optionally filter by *agent_id* and cap results with *limit*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if (not agent_id or e["agent_id"] == agent_id)
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get lock count
    # ------------------------------------------------------------------

    def get_lock_count(self, agent_id: str = "") -> int:
        """Return the number of lock records, optionally filtered by *agent_id*."""
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
        """Return operational statistics for the locker service."""
        total = len(self._state.entries)
        agents = set(e["agent_id"] for e in self._state.entries.values())
        return {
            "total_locks": total,
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored lock records, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        self._on_change = None
