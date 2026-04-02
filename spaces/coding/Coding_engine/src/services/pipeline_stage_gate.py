"""Pipeline stage gate enforcement — manages approval gates between pipeline stages.

Each gate tracks required approvals, current approvals, rejections, and status.
Gates transition from "pending" to "approved" when enough approvals are collected,
or to "rejected" when any approver rejects.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class GateEntry:
    """A single stage gate entry."""

    gate_id: str = ""
    pipeline_id: str = ""
    stage_name: str = ""
    required_approvals: int = 1
    approvals: List[str] = field(default_factory=list)
    rejections: List[Tuple[str, str]] = field(default_factory=list)
    status: str = "pending"
    created_at: float = 0.0


class PipelineStageGate:
    """Manages approval gates that control pipeline stage transitions.

    Gates enforce that a configurable number of approvals are collected
    before a pipeline may proceed past a stage boundary.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._gates: Dict[str, GateEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"psg2-{self._seq}-{id(self)}"
        return "psg2-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Any) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict the oldest entries when the store exceeds max_entries."""
        if len(self._gates) <= self._max_entries:
            return
        sorted_entries = sorted(
            self._gates.values(), key=lambda e: e.created_at
        )
        remove_count = len(self._gates) - self._max_entries
        for entry in sorted_entries[:remove_count]:
            del self._gates[entry.gate_id]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: GateEntry) -> Dict[str, Any]:
        """Convert a GateEntry to a plain dictionary."""
        return {
            "gate_id": entry.gate_id,
            "pipeline_id": entry.pipeline_id,
            "stage_name": entry.stage_name,
            "required_approvals": entry.required_approvals,
            "approvals": list(entry.approvals),
            "rejections": list(entry.rejections),
            "status": entry.status,
            "created_at": entry.created_at,
        }

    # ------------------------------------------------------------------
    # Create gate
    # ------------------------------------------------------------------

    def create_gate(
        self,
        pipeline_id: str,
        stage_name: str,
        required_approvals: int = 1,
    ) -> str:
        """Create a stage gate. Returns gate_id with 'psg2-' prefix."""
        self._prune_if_needed()
        gate_id = self._generate_id()

        entry = GateEntry(
            gate_id=gate_id,
            pipeline_id=pipeline_id,
            stage_name=stage_name,
            required_approvals=required_approvals,
            approvals=[],
            rejections=[],
            status="pending",
            created_at=time.time(),
        )
        self._gates[gate_id] = entry
        self._fire("gate_created", self._entry_to_dict(entry))
        return gate_id

    # ------------------------------------------------------------------
    # Get gate
    # ------------------------------------------------------------------

    def get_gate(self, gate_id: str) -> Optional[Dict[str, Any]]:
        """Get gate by ID. Returns dict or None."""
        entry = self._gates.get(gate_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # Approve gate
    # ------------------------------------------------------------------

    def approve_gate(self, gate_id: str, approver_id: str) -> bool:
        """Approve a gate. Returns False if not found or already finalized."""
        entry = self._gates.get(gate_id)
        if entry is None:
            return False
        if entry.status in ("approved", "rejected"):
            return False

        entry.approvals.append(approver_id)
        if len(entry.approvals) >= entry.required_approvals:
            entry.status = "approved"

        self._fire("gate_approved", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Reject gate
    # ------------------------------------------------------------------

    def reject_gate(self, gate_id: str, approver_id: str, reason: str = "") -> bool:
        """Reject a gate. Returns False if not found or already finalized."""
        entry = self._gates.get(gate_id)
        if entry is None:
            return False
        if entry.status in ("approved", "rejected"):
            return False

        entry.rejections.append((approver_id, reason))
        entry.status = "rejected"

        self._fire("gate_rejected", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def is_approved(self, gate_id: str) -> bool:
        """Return True if the gate has met its required approvals."""
        entry = self._gates.get(gate_id)
        if entry is None:
            return False
        return entry.status == "approved"

    def get_gate_status(self, gate_id: str) -> str:
        """Return the gate status: 'pending', 'approved', or 'rejected'."""
        entry = self._gates.get(gate_id)
        if entry is None:
            return "pending"
        return entry.status

    def get_pipeline_gates(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Return all gates for a pipeline."""
        return [
            self._entry_to_dict(e)
            for e in self._gates.values()
            if e.pipeline_id == pipeline_id
        ]

    # ------------------------------------------------------------------
    # Reset gate
    # ------------------------------------------------------------------

    def reset_gate(self, gate_id: str) -> bool:
        """Reset a gate back to pending. Returns False if not found."""
        entry = self._gates.get(gate_id)
        if entry is None:
            return False
        entry.status = "pending"
        entry.approvals = []
        entry.rejections = []
        self._fire("gate_reset", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Remove gate
    # ------------------------------------------------------------------

    def remove_gate(self, gate_id: str) -> bool:
        """Remove a gate by ID. Returns False if not found."""
        entry = self._gates.pop(gate_id, None)
        if entry is None:
            return False
        self._fire("gate_removed", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of unique pipeline IDs that have gates."""
        seen: Dict[str, None] = {}
        for e in self._gates.values():
            seen[e.pipeline_id] = None
        return list(seen.keys())

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_gate_count(self) -> int:
        """Return the total number of stored gates."""
        return len(self._gates)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        status_counts: Dict[str, int] = {"pending": 0, "approved": 0, "rejected": 0}
        for entry in self._gates.values():
            status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
        return {
            "total_gates": len(self._gates),
            "max_entries": self._max_entries,
            "by_status": dict(status_counts),
            "pipelines": len(self.list_pipelines()),
            "registered_callbacks": len(self._callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored gates, callbacks, and reset counters."""
        self._gates.clear()
        self._callbacks.clear()
        self._seq = 0
