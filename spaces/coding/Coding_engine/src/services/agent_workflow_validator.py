"""Agent Workflow Validator -- validates agent workflow definitions.

Checks workflow definitions for required fields, valid transitions, and
structural integrity.  Validation rules are registered individually and
can check for field presence, type conformance, or exact value matches.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Internal dataclass
# ------------------------------------------------------------------

@dataclass
class AgentWorkflowValidatorState:
    """Internal state container for the validator."""

    entries: dict = field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowValidator:
    """Validates agent workflow definitions against registered rules.

    Rules can check that a field is present (``required``), that it has
    a particular type (``type``), or that it equals a specific value
    (``value``).  The :meth:`validate` method runs all (or a subset of)
    registered rules against a workflow dict and returns a result summary.
    """

    PREFIX = "awv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowValidatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        self._validation_count: int = 0
        self._total_errors: int = 0

    # ----------------------------------------------------------
    # ID generation
    # ----------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + digest[:16]

    # ----------------------------------------------------------
    # Pruning
    # ----------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(sorted_keys) // 4 or 1
            for key in sorted_keys[:to_remove]:
                del self._state.entries[key]

    # ----------------------------------------------------------
    # Event firing
    # ----------------------------------------------------------

    def _fire(self, event: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception as exc:
                logger.error("on_change callback error: %s", exc)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.error("callback '%s' error: %s", name, exc)

    # ----------------------------------------------------------
    # Callback management
    # ----------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ----------------------------------------------------------
    # Rule registration
    # ----------------------------------------------------------

    def register_rule(
        self,
        rule_name: str,
        field: str,
        check_type: str = "required",
        expected_value: Any = None,
    ) -> str:
        """Register a validation rule.

        Parameters
        ----------
        rule_name:
            Human-readable name for the rule.
        field:
            The workflow dict key to validate.
        check_type:
            One of ``"required"``, ``"type"``, or ``"value"``.
        expected_value:
            For ``"type"`` checks, the type name (e.g. ``"str"``).
            For ``"value"`` checks, the exact expected value.

        Returns
        -------
        str
            The generated rule ID.
        """
        rule_id = self._generate_id(rule_name)
        self._state.entries[rule_id] = {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "field": field,
            "check_type": check_type,
            "expected_value": expected_value,
            "created_at": time.time(),
        }
        self._prune()
        self._fire("rule_registered", {"rule_id": rule_id, "rule_name": rule_name})
        return rule_id

    # ----------------------------------------------------------
    # Validation
    # ----------------------------------------------------------

    def validate(self, workflow: dict, rule_ids: Optional[List[str]] = None) -> dict:
        """Validate a workflow dict against registered rules.

        Parameters
        ----------
        workflow:
            The workflow definition to validate.
        rule_ids:
            Optional list of rule IDs to check.  If ``None`` all rules
            are checked.

        Returns
        -------
        dict
            ``{"valid": bool, "errors": [...], "rules_checked": int,
            "rules_passed": int}``
        """
        self._validation_count += 1
        errors: List[str] = []

        if rule_ids is None:
            rules_to_check = list(self._state.entries.values())
        else:
            rules_to_check = [
                self._state.entries[rid]
                for rid in rule_ids
                if rid in self._state.entries
            ]

        rules_passed = 0

        for rule in rules_to_check:
            field_name = rule["field"]
            check_type = rule["check_type"]
            expected = rule["expected_value"]

            if check_type == "required":
                if field_name not in workflow:
                    errors.append(
                        f"Rule '{rule['rule_name']}': field '{field_name}' is required but missing"
                    )
                else:
                    rules_passed += 1

            elif check_type == "type":
                if field_name not in workflow:
                    errors.append(
                        f"Rule '{rule['rule_name']}': field '{field_name}' is missing (expected type '{expected}')"
                    )
                elif type(workflow[field_name]).__name__ != expected:
                    errors.append(
                        f"Rule '{rule['rule_name']}': field '{field_name}' expected type '{expected}', "
                        f"got '{type(workflow[field_name]).__name__}'"
                    )
                else:
                    rules_passed += 1

            elif check_type == "value":
                if field_name not in workflow:
                    errors.append(
                        f"Rule '{rule['rule_name']}': field '{field_name}' is missing (expected value {expected!r})"
                    )
                elif workflow[field_name] != expected:
                    errors.append(
                        f"Rule '{rule['rule_name']}': field '{field_name}' expected {expected!r}, "
                        f"got {workflow[field_name]!r}"
                    )
                else:
                    rules_passed += 1

        self._total_errors += len(errors)
        result = {
            "valid": len(errors) == 0,
            "errors": errors,
            "rules_checked": len(rules_to_check),
            "rules_passed": rules_passed,
        }
        self._fire("validation_complete", result)
        return result

    # ----------------------------------------------------------
    # Rule queries
    # ----------------------------------------------------------

    def get_rule(self, rule_id: str) -> dict:
        """Return rule info or empty dict if not found."""
        return dict(self._state.entries.get(rule_id, {}))

    def get_rules(self) -> list:
        """Return a list of all registered rules."""
        return [dict(v) for v in self._state.entries.values()]

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID.  Returns True if removed."""
        if rule_id in self._state.entries:
            del self._state.entries[rule_id]
            self._fire("rule_removed", {"rule_id": rule_id})
            return True
        return False

    def get_rule_count(self) -> int:
        """Return the number of registered rules."""
        return len(self._state.entries)

    # ----------------------------------------------------------
    # Stats
    # ----------------------------------------------------------

    def get_validation_count(self) -> int:
        """Return the total number of validations performed."""
        return self._validation_count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        return {
            "total_rules": len(self._state.entries),
            "total_validations": self._validation_count,
            "total_errors": self._total_errors,
        }

    # ----------------------------------------------------------
    # Reset
    # ----------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowValidatorState()
        self._callbacks.clear()
        self._on_change = None
        self._validation_count = 0
        self._total_errors = 0
        self._fire("reset", {})
