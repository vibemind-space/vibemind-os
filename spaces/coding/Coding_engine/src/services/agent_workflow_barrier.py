"""Agent Workflow Barrier -- manages synchronization barriers for workflow steps.

Barriers require a specified number of arrivals before they are considered
complete.  Useful for fan-in synchronization where multiple agents or tasks
must finish before a workflow can proceed.
Uses SHA-256-based IDs with an ``awba-`` prefix.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowBarrierState:
    """Internal store for workflow barrier entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowBarrier:
    """Manages synchronization barriers for agent workflow steps.

    A barrier is created with a *required_count* of arrivals.  Agents call
    :meth:`arrive` to record their arrival.  The barrier is complete once the
    number of arrivals meets or exceeds *required_count*.
    """

    PREFIX = "awba-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowBarrierState()
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
    # Create barrier
    # ------------------------------------------------------------------

    def create_barrier(
        self,
        workflow_id: str,
        required_count: int = 1,
        label: str = "",
    ) -> str:
        """Create a barrier needing *required_count* arrivals.

        Returns the barrier ID (``awba-`` prefix).
        """
        self._prune()
        barrier_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "barrier_id": barrier_id,
            "workflow_id": workflow_id,
            "required_count": required_count,
            "label": label,
            "arrivals": [],
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[barrier_id] = entry
        self._fire("barrier_created", entry)
        logger.debug(
            "Barrier created: %s workflow=%s required=%d label=%s",
            barrier_id, workflow_id, required_count, label,
        )
        return barrier_id

    # ------------------------------------------------------------------
    # Arrive
    # ------------------------------------------------------------------

    def arrive(self, barrier_id: str, agent_id: str = "") -> bool:
        """Record an arrival at a barrier.  Returns ``True`` if the arrival
        was recorded successfully.
        """
        entry = self._state.entries.get(barrier_id)
        if entry is None:
            return False
        entry["arrivals"].append({
            "agent_id": agent_id,
            "arrived_at": time.time(),
        })
        self._fire("barrier_arrival", entry)
        if len(entry["arrivals"]) >= entry["required_count"]:
            self._fire("barrier_completed", entry)
        return True

    # ------------------------------------------------------------------
    # Is complete
    # ------------------------------------------------------------------

    def is_complete(self, barrier_id: str) -> bool:
        """Return ``True`` if arrivals >= required_count."""
        entry = self._state.entries.get(barrier_id)
        if entry is None:
            return False
        return len(entry["arrivals"]) >= entry["required_count"]

    # ------------------------------------------------------------------
    # Get barrier by ID
    # ------------------------------------------------------------------

    def get_barrier(self, barrier_id: str) -> Optional[dict]:
        """Get a barrier by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(barrier_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get barriers (query)
    # ------------------------------------------------------------------

    def get_barriers(
        self,
        workflow_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query barriers, newest first.

        Optionally filter by *workflow_id* and cap results with *limit*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if not workflow_id or e["workflow_id"] == workflow_id
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get barrier count
    # ------------------------------------------------------------------

    def get_barrier_count(self, workflow_id: str = "") -> int:
        """Return the number of barriers, optionally filtered by *workflow_id*."""
        if not workflow_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["workflow_id"] == workflow_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the barrier service."""
        total_barriers = len(self._state.entries)
        completed_barriers = 0
        total_arrivals = 0
        for entry in self._state.entries.values():
            total_arrivals += len(entry["arrivals"])
            if len(entry["arrivals"]) >= entry["required_count"]:
                completed_barriers += 1
        return {
            "total_barriers": total_barriers,
            "completed_barriers": completed_barriers,
            "total_arrivals": total_arrivals,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored barriers, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
