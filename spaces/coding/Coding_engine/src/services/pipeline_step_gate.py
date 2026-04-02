"""Pipeline step gate enforcement — manages conditional gates on individual pipeline steps.

Each gate associates a condition key with a required value. When checked, the gate
evaluates whether the provided context satisfies the condition. Gates can also be
forced open or closed, bypassing condition evaluation entirely.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepGateState:
    """Internal state for the PipelineStepGate service."""

    gates: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepGate:
    """Manages conditional gates on individual pipeline steps.

    Gates evaluate a condition key against a required value from a context
    dictionary, or can be forced open/closed regardless of conditions.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepGateState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psg-{self._state._seq}-{id(self)}"
        return "psg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict the oldest entries when the store exceeds max_entries."""
        total = sum(
            len(steps) for steps in self._state.gates.values()
        )
        if total <= self._max_entries:
            return
        all_entries: List[Dict[str, Any]] = []
        for steps in self._state.gates.values():
            for entry in steps.values():
                all_entries.append(entry)
        all_entries.sort(key=lambda e: e["created_at"])
        remove_count = total - self._max_entries
        for entry in all_entries[:remove_count]:
            pid = entry["pipeline_id"]
            sname = entry["step_name"]
            if pid in self._state.gates and sname in self._state.gates[pid]:
                del self._state.gates[pid][sname]
                if not self._state.gates[pid]:
                    del self._state.gates[pid]

    # ------------------------------------------------------------------
    # Create gate
    # ------------------------------------------------------------------

    def create_gate(
        self,
        pipeline_id: str,
        step_name: str,
        condition_key: str,
        required_value: Any = True,
    ) -> str:
        """Create a step gate. Returns gate_id with 'psg-' prefix."""
        self._prune_if_needed()
        gate_id = self._generate_id()

        entry: Dict[str, Any] = {
            "gate_id": gate_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "condition_key": condition_key,
            "required_value": required_value,
            "forced_state": None,
            "created_at": time.time(),
            "check_count": 0,
        }

        if pipeline_id not in self._state.gates:
            self._state.gates[pipeline_id] = {}
        self._state.gates[pipeline_id][step_name] = entry

        self._fire("gate_created", dict(entry))
        return gate_id

    # ------------------------------------------------------------------
    # Check gate
    # ------------------------------------------------------------------

    def check_gate(self, pipeline_id: str, step_name: str, context: Dict[str, Any]) -> bool:
        """Check if the gate passes for the given context.

        Returns True if forced open, False if forced closed, otherwise
        evaluates context.get(condition_key) == required_value.
        Increments the check_count on each call.
        """
        steps = self._state.gates.get(pipeline_id)
        if steps is None:
            return False
        entry = steps.get(step_name)
        if entry is None:
            return False

        entry["check_count"] += 1

        if entry["forced_state"] == "open":
            return True
        if entry["forced_state"] == "closed":
            return False

        return context.get(entry["condition_key"]) == entry["required_value"]

    # ------------------------------------------------------------------
    # Open / Close gate
    # ------------------------------------------------------------------

    def open_gate(self, pipeline_id: str, step_name: str) -> bool:
        """Force gate open (always passes). Returns False if not found."""
        steps = self._state.gates.get(pipeline_id)
        if steps is None:
            return False
        entry = steps.get(step_name)
        if entry is None:
            return False
        entry["forced_state"] = "open"
        self._fire("gate_opened", dict(entry))
        return True

    def close_gate(self, pipeline_id: str, step_name: str) -> bool:
        """Force gate closed (always fails). Returns False if not found."""
        steps = self._state.gates.get(pipeline_id)
        if steps is None:
            return False
        entry = steps.get(step_name)
        if entry is None:
            return False
        entry["forced_state"] = "closed"
        self._fire("gate_closed", dict(entry))
        return True

    # ------------------------------------------------------------------
    # Get gate
    # ------------------------------------------------------------------

    def get_gate(self, pipeline_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """Get gate by pipeline_id and step_name. Returns dict or None."""
        steps = self._state.gates.get(pipeline_id)
        if steps is None:
            return None
        entry = steps.get(step_name)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_gate_count(self, pipeline_id: str = "") -> int:
        """Return gate count. If pipeline_id given, count only that pipeline."""
        if pipeline_id:
            steps = self._state.gates.get(pipeline_id)
            if steps is None:
                return 0
            return len(steps)
        return sum(len(steps) for steps in self._state.gates.values())

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have gates."""
        return list(self._state.gates.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        total = 0
        forced_open = 0
        forced_closed = 0
        total_checks = 0
        for steps in self._state.gates.values():
            for entry in steps.values():
                total += 1
                total_checks += entry["check_count"]
                if entry["forced_state"] == "open":
                    forced_open += 1
                elif entry["forced_state"] == "closed":
                    forced_closed += 1
        return {
            "total_gates": total,
            "max_entries": self._max_entries,
            "forced_open": forced_open,
            "forced_closed": forced_closed,
            "total_checks": total_checks,
            "pipelines": len(self._state.gates),
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored gates, callbacks, and reset counters."""
        self._state.gates.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
