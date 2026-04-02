"""Enhanced pipeline step condition evaluator — evaluates conditions to determine
whether pipeline steps should execute.

Supports operators: eq, ne, gt, lt, gte, lte, contains, in. Conditions are
registered with a name, field, operator, and expected value, then evaluated
against a context dictionary.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepConditionV2State:
    """Internal state for the PipelineStepConditionV2 service."""

    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineStepConditionV2:
    """Evaluates conditions to determine whether pipeline steps should execute.

    Conditions are registered with a name, field, operator, and expected value.
    They can be evaluated individually or in bulk against a context dictionary.
    """

    PREFIX = "pscv2-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepConditionV2State()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict the oldest entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._state.entries,
            key=lambda k: self._state.entries[k]["created_at"],
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        for cid in sorted_ids[:remove_count]:
            del self._state.entries[cid]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        if self._on_change is not None:
            try:
                self._on_change(action, detail)
            except Exception:
                logger.exception("on_change callback error for action=%s", action)
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback error for action=%s", action)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Register condition
    # ------------------------------------------------------------------

    def register_condition(
        self,
        name: str,
        field: str,
        operator: str,
        value: Any,
    ) -> str:
        """Register a condition. Returns condition_id.

        Supported operators: "eq", "ne", "gt", "lt", "gte", "lte",
        "contains", "in".
        """
        self._prune()
        condition_id = self._generate_id()

        entry: Dict[str, Any] = {
            "condition_id": condition_id,
            "name": name,
            "field": field,
            "operator": operator,
            "value": value,
            "created_at": time.time(),
            "eval_count": 0,
        }

        self._state.entries[condition_id] = entry
        self._fire("condition_registered", dict(entry))
        return condition_id

    # ------------------------------------------------------------------
    # Evaluate single condition
    # ------------------------------------------------------------------

    def evaluate(self, condition_id: str, context: dict) -> bool:
        """Evaluate a single condition against *context*. Returns True/False."""
        entry = self._state.entries.get(condition_id)
        if entry is None:
            return False

        entry["eval_count"] += 1

        fld = entry["field"]
        op = entry["operator"]
        expected = entry["value"]

        if fld not in context:
            return False

        actual = context[fld]

        if op == "eq":
            return actual == expected
        elif op == "ne":
            return actual != expected
        elif op == "gt":
            return actual > expected
        elif op == "lt":
            return actual < expected
        elif op == "gte":
            return actual >= expected
        elif op == "lte":
            return actual <= expected
        elif op == "contains":
            return expected in actual
        elif op == "in":
            return actual in expected
        else:
            logger.warning("unknown operator %s for condition %s", op, condition_id)
            return False

    # ------------------------------------------------------------------
    # Evaluate multiple conditions
    # ------------------------------------------------------------------

    def evaluate_all(
        self,
        condition_ids: list,
        context: dict,
        mode: str = "all",
    ) -> dict:
        """Evaluate multiple conditions.

        *mode* can be ``"all"`` (every condition must pass) or ``"any"``
        (at least one must pass).

        Returns a dict with keys: passed, results, total, passed_count.
        """
        results: List[Dict[str, Any]] = []
        passed_count = 0

        for cid in condition_ids:
            result = self.evaluate(cid, context)
            results.append({"condition_id": cid, "passed": result})
            if result:
                passed_count += 1

        total = len(condition_ids)

        if mode == "any":
            passed = passed_count > 0
        else:
            passed = passed_count == total

        return {
            "passed": passed,
            "results": results,
            "total": total,
            "passed_count": passed_count,
        }

    # ------------------------------------------------------------------
    # Get condition(s)
    # ------------------------------------------------------------------

    def get_condition(self, condition_id: str) -> dict:
        """Return a copy of a single condition entry, or empty dict."""
        entry = self._state.entries.get(condition_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_conditions(self) -> list:
        """Return a list of all condition entries (copies)."""
        return [dict(e) for e in self._state.entries.values()]

    def get_condition_count(self) -> int:
        """Return the number of registered conditions."""
        return len(self._state.entries)

    # ------------------------------------------------------------------
    # Remove condition
    # ------------------------------------------------------------------

    def remove_condition(self, condition_id: str) -> bool:
        """Remove a condition by its ID. Returns True if removed."""
        if condition_id in self._state.entries:
            removed = self._state.entries.pop(condition_id)
            self._fire("condition_removed", dict(removed))
            return True
        return False

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        total_evaluations = sum(
            e["eval_count"] for e in self._state.entries.values()
        )
        return {
            "total_conditions": len(self._state.entries),
            "total_evaluations": total_evaluations,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all conditions, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
