"""Pipeline step condition evaluation — manages conditional rules on pipeline steps.

Each condition associates a field with an operator and expected value. When
evaluated, all conditions for a given pipeline step must pass for the step to
proceed. Supported operators: eq, neq, gt, lt, in.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepConditionState:
    """Internal state for the PipelineStepCondition service."""

    conditions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepCondition:
    """Manages conditional rules on individual pipeline steps.

    Conditions are evaluated against a context dictionary. A step passes
    only when every associated condition is satisfied.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepConditionState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psc-{self._state._seq}-{id(self)}"
        return "psc-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

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
        total = sum(len(conds) for conds in self._state.conditions.values())
        if total <= self._max_entries:
            return
        all_entries: List[Dict[str, Any]] = []
        for conds in self._state.conditions.values():
            all_entries.extend(conds)
        all_entries.sort(key=lambda e: e["created_at"])
        remove_count = total - self._max_entries
        for entry in all_entries[:remove_count]:
            pid = entry["pipeline_id"]
            if pid in self._state.conditions:
                self._state.conditions[pid] = [
                    c for c in self._state.conditions[pid]
                    if c["condition_id"] != entry["condition_id"]
                ]
                if not self._state.conditions[pid]:
                    del self._state.conditions[pid]

    # ------------------------------------------------------------------
    # Add condition
    # ------------------------------------------------------------------

    def add_condition(
        self,
        pipeline_id: str,
        step_name: str,
        field: str,
        operator: str,
        value: Any,
    ) -> str:
        """Add a condition to a pipeline step. Returns condition_id (psc-...).

        Supported operators: "eq", "neq", "gt", "lt", "in".
        """
        self._prune_if_needed()
        condition_id = self._generate_id()

        entry: Dict[str, Any] = {
            "condition_id": condition_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "field": field,
            "operator": operator,
            "value": value,
            "created_at": time.time(),
        }

        if pipeline_id not in self._state.conditions:
            self._state.conditions[pipeline_id] = []
        self._state.conditions[pipeline_id].append(entry)

        self._fire("condition_added", dict(entry))
        return condition_id

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------

    def evaluate(self, pipeline_id: str, step_name: str, context: Dict[str, Any]) -> bool:
        """Evaluate ALL conditions for a pipeline step.

        Returns True only if every condition for the step passes.
        Returns True when no conditions exist for the step.
        """
        conds = self._state.conditions.get(pipeline_id)
        if conds is None:
            return True

        step_conds = [c for c in conds if c["step_name"] == step_name]
        if not step_conds:
            return True

        for cond in step_conds:
            fld = cond["field"]
            op = cond["operator"]
            expected = cond["value"]

            if fld not in context:
                return False

            actual = context[fld]

            if op == "eq":
                if actual != expected:
                    return False
            elif op == "neq":
                if actual == expected:
                    return False
            elif op == "gt":
                if not (actual > expected):
                    return False
            elif op == "lt":
                if not (actual < expected):
                    return False
            elif op == "in":
                if actual not in expected:
                    return False
            else:
                logger.warning("unknown_operator", operator=op, condition_id=cond["condition_id"])
                return False

        return True

    # ------------------------------------------------------------------
    # Get conditions
    # ------------------------------------------------------------------

    def get_conditions(self, pipeline_id: str, step_name: str = "") -> List[Dict[str, Any]]:
        """Get conditions for a pipeline, optionally filtered by step_name."""
        conds = self._state.conditions.get(pipeline_id)
        if conds is None:
            return []
        if step_name:
            return [dict(c) for c in conds if c["step_name"] == step_name]
        return [dict(c) for c in conds]

    # ------------------------------------------------------------------
    # Remove condition
    # ------------------------------------------------------------------

    def remove_condition(self, condition_id: str) -> bool:
        """Remove a condition by its ID. Returns True if removed."""
        for pid, conds in self._state.conditions.items():
            for i, cond in enumerate(conds):
                if cond["condition_id"] == condition_id:
                    removed = conds.pop(i)
                    if not conds:
                        del self._state.conditions[pid]
                    self._fire("condition_removed", dict(removed))
                    return True
        return False

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_condition_count(self, pipeline_id: str = "") -> int:
        """Return condition count. If pipeline_id given, count only that pipeline."""
        if pipeline_id:
            conds = self._state.conditions.get(pipeline_id)
            if conds is None:
                return 0
            return len(conds)
        return sum(len(conds) for conds in self._state.conditions.values())

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have conditions."""
        return list(self._state.conditions.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        total = 0
        operators: Dict[str, int] = {}
        for conds in self._state.conditions.values():
            for entry in conds:
                total += 1
                op = entry["operator"]
                operators[op] = operators.get(op, 0) + 1
        return {
            "total_conditions": total,
            "max_entries": self._max_entries,
            "pipelines": len(self._state.conditions),
            "operators": operators,
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored conditions, callbacks, and reset counters."""
        self._state.conditions.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
