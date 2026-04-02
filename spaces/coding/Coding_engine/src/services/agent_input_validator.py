"""Agent Input Validator – validates agent inputs against defined schemas/rules.

Registers validation rules per agent and validates incoming input data
against them before processing. Supports required, type, min, max, and
in-set checks.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentInputValidator:
    """Validates agent inputs against registered rules."""

    rules: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0

    def __post_init__(self) -> None:
        self._callbacks: Dict[str, Callable] = {}
        self._max_rules = 10000
        self._total_added = 0
        self._total_validated = 0
        self._total_removed = 0
        self._logger = logger

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return "aiv-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(
        self,
        agent_id: str,
        field: str,
        rule_type: str = "required",
        rule_value: Any = None,
    ) -> str:
        """Add a validation rule for an agent field.

        rule_type: "required", "type", "min", "max", "in"
        Returns rule ID (aiv-xxx) or empty string on failure.
        """
        if not agent_id or not field:
            return ""
        if len(self.rules) >= self._max_rules:
            return ""

        rid = self._make_id(f"{agent_id}-{field}-{rule_type}")
        self.rules[rid] = {
            "rule_id": rid,
            "agent_id": agent_id,
            "field": field,
            "rule_type": rule_type,
            "rule_value": rule_value,
            "created_at": time.time(),
        }
        self._total_added += 1
        self._fire("rule_added", {"rule_id": rid, "agent_id": agent_id})
        self._logger.info("rule_added", rule_id=rid, agent_id=agent_id)
        return rid

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        if rule_id not in self.rules:
            return False
        self.rules.pop(rule_id)
        self._total_removed += 1
        self._fire("rule_removed", {"rule_id": rule_id})
        return True

    def get_rules(self, agent_id: str) -> list:
        """Get all rules for an agent."""
        return [
            dict(r) for r in self.rules.values() if r["agent_id"] == agent_id
        ]

    def get_rule_count(self, agent_id: str = "") -> int:
        """Count rules, optionally filtered by agent_id."""
        if not agent_id:
            return len(self.rules)
        return sum(1 for r in self.rules.values() if r["agent_id"] == agent_id)

    def list_agents(self) -> list:
        """Return sorted list of unique agent IDs that have rules."""
        return sorted({r["agent_id"] for r in self.rules.values()})

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, agent_id: str, input_data: dict) -> dict:
        """Validate input_data against all rules for agent_id.

        Returns {"valid": bool, "errors": list_of_str}.
        """
        errors: List[str] = []
        agent_rules = self.get_rules(agent_id)

        for rule in agent_rules:
            fld = rule["field"]
            rtype = rule["rule_type"]
            rval = rule["rule_value"]

            if rtype == "required":
                if fld not in input_data or input_data[fld] is None:
                    errors.append(f"field '{fld}' is required")

            elif rtype == "type":
                if fld in input_data and input_data[fld] is not None:
                    type_map = {
                        "str": str,
                        "int": int,
                        "float": float,
                        "bool": bool,
                        "list": list,
                        "dict": dict,
                    }
                    expected = type_map.get(rval)
                    if expected and not isinstance(input_data[fld], expected):
                        errors.append(
                            f"field '{fld}' must be of type {rval}"
                        )

            elif rtype == "min":
                if fld in input_data and input_data[fld] is not None:
                    try:
                        if input_data[fld] < rval:
                            errors.append(
                                f"field '{fld}' must be >= {rval}"
                            )
                    except TypeError:
                        errors.append(f"field '{fld}' is not comparable for min")

            elif rtype == "max":
                if fld in input_data and input_data[fld] is not None:
                    try:
                        if input_data[fld] > rval:
                            errors.append(
                                f"field '{fld}' must be <= {rval}"
                            )
                    except TypeError:
                        errors.append(f"field '{fld}' is not comparable for max")

            elif rtype == "in":
                if fld in input_data and input_data[fld] is not None:
                    if input_data[fld] not in (rval or []):
                        errors.append(
                            f"field '{fld}' must be one of {rval}"
                        )

        self._total_validated += 1
        valid = len(errors) == 0

        if not valid:
            self._fire("validation_failed", {
                "agent_id": agent_id, "errors": errors,
            })

        return {"valid": valid, "errors": errors}

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_rules": len(self.rules),
            "total_added": self._total_added,
            "total_validated": self._total_validated,
            "total_removed": self._total_removed,
            "total_agents": len(self.list_agents()),
        }

    def reset(self) -> None:
        self.rules.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_added = 0
        self._total_validated = 0
        self._total_removed = 0
