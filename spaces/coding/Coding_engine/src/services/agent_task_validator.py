"""Agent Task Validator -- validates task inputs and outputs against rules.

Validates data dictionaries against configurable rules such as required fields,
type checking, and non-empty values. Tracks validation results per task with
pass/fail outcomes.

Usage::

    validator = AgentTaskValidator()

    # Validate task data
    vid = validator.validate("task-1", {"name": "test", "count": 5},
                             rules=["required_fields", "type_check"],
                             label="input")

    # Query
    entry = validator.get_validation(vid)
    results = validator.get_validations(task_id="task-1")
    stats = validator.get_stats()
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
class AgentTaskValidatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskValidator:
    """Validates task inputs and outputs against rules."""

    PREFIX = "atva-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskValidatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Validation rules
    # ------------------------------------------------------------------

    def _check_required_fields(self, data: dict) -> List[str]:
        """Check that data is not empty (has at least one field)."""
        errors: List[str] = []
        if not data:
            errors.append("data has no fields")
        return errors

    def _check_type_check(self, data: dict) -> List[str]:
        """Check that all values are of basic serialisable types."""
        errors: List[str] = []
        allowed = (str, int, float, bool, list, dict, type(None))
        for key, value in data.items():
            if not isinstance(value, allowed):
                errors.append(f"field '{key}' has unsupported type {type(value).__name__}")
        return errors

    def _check_non_empty(self, data: dict) -> List[str]:
        """Check that no values are empty strings, empty lists, or empty dicts."""
        errors: List[str] = []
        for key, value in data.items():
            if value == "" or value == [] or value == {}:
                errors.append(f"field '{key}' is empty")
        return errors

    # ------------------------------------------------------------------
    # Validation operations
    # ------------------------------------------------------------------

    def validate(
        self,
        task_id: str,
        data: dict,
        rules: List[str] = None,
        label: str = "",
    ) -> str:
        """Validate data against rules.

        Supported rules: ``"required_fields"``, ``"type_check"``, ``"non_empty"``.
        Returns the validation ID on success or ``""`` on failure.
        """
        if not task_id or data is None:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        active_rules = rules if rules is not None else ["required_fields"]
        data_copy = copy.deepcopy(data)

        all_errors: List[str] = []
        rule_map = {
            "required_fields": self._check_required_fields,
            "type_check": self._check_type_check,
            "non_empty": self._check_non_empty,
        }
        for rule in active_rules:
            checker = rule_map.get(rule)
            if checker:
                all_errors.extend(checker(data_copy))

        passed = len(all_errors) == 0
        now = time.time()
        validation_id = self._generate_id()

        self._state.entries[validation_id] = {
            "validation_id": validation_id,
            "task_id": task_id,
            "data": data_copy,
            "rules": list(active_rules),
            "label": label,
            "passed": passed,
            "errors": all_errors,
            "created_at": now,
            "_seq": self._state._seq,
        }

        self._fire("validation_created", self._state.entries[validation_id])
        logger.debug(
            "Validation created: %s (task=%s, passed=%s)",
            validation_id,
            task_id,
            passed,
        )
        return validation_id

    def get_validation(self, validation_id: str) -> Optional[dict]:
        """Return the validation entry or None."""
        entry = self._state.entries.get(validation_id)
        return dict(entry) if entry else None

    def get_validations(
        self,
        task_id: str = "",
        label: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query validations, newest first.

        Optionally filter by task_id and/or label.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if task_id and entry["task_id"] != task_id:
                continue
            if label and entry["label"] != label:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_validation_count(self, task_id: str = "", passed: bool = None) -> int:
        """Return the number of validations, optionally filtered."""
        if not task_id and passed is None:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if task_id and e["task_id"] != task_id:
                continue
            if passed is not None and e["passed"] != passed:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = len(self._state.entries)
        passed_count = sum(1 for e in self._state.entries.values() if e["passed"])
        failed_count = total - passed_count
        return {
            "total_validations": total,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "pass_rate": passed_count / total if total > 0 else 0.0,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskValidatorState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskValidator reset")
