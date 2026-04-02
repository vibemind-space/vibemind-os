"""Pipeline input validator -- validates pipeline input data against registered rules.

Supports rule types: required, min, max, type, pattern.  Rules are keyed by
pipeline ID so each pipeline can have its own validation constraints.  Fires
callbacks on validation events and exposes lightweight stats / reset helpers.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# Valid rule types accepted by add_rule.
RULE_TYPES = ("required", "min", "max", "type", "pattern")

# Python types accepted by the "type" rule.
TYPE_MAP: Dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


@dataclass
class _RuleEntry:
    """Internal record for a single validation rule."""

    rule_id: str = ""
    pipeline_id: str = ""
    field_name: str = ""
    rule_type: str = "required"
    value: Any = None
    seq: int = 0
    created_at: float = field(default_factory=time.time)


class PipelineInputValidator:
    """Validates pipeline input data against registered rules."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._rules: Dict[str, _RuleEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries
        self._stats = {
            "rules_added": 0,
            "rules_removed": 0,
            "validations_run": 0,
            "validations_passed": 0,
            "validations_failed": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{uuid.uuid4().hex}{self._seq}"
        return "piv-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is exceeded."""
        if len(self._rules) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._rules,
            key=lambda rid: self._rules[rid].created_at,
        )
        remove_count = len(self._rules) - self._max_entries
        for rid in sorted_ids[:remove_count]:
            entry = self._rules.pop(rid)
            logger.debug(
                "pipeline_input_validator.pruned",
                rule_id=rid,
                pipeline_id=entry.pipeline_id,
            )

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(
        self,
        pipeline_id: str,
        field_name: str,
        rule_type: str = "required",
        value: Any = None,
    ) -> str:
        """Add a validation rule for *pipeline_id*.

        Supported *rule_type* values:
        - ``"required"`` -- field must be present and not ``None``
        - ``"min"``      -- numeric field must be >= *value*
        - ``"max"``      -- numeric field must be <= *value*
        - ``"type"``     -- field must be an instance of the type named by *value*
                            (one of ``"str"``, ``"int"``, ``"float"``, ``"bool"``,
                            ``"list"``, ``"dict"``)
        - ``"pattern"``  -- string field must match the regex in *value*

        Returns the rule ID, or ``""`` on failure.
        """
        if not pipeline_id or not field_name:
            return ""
        if rule_type not in RULE_TYPES:
            return ""

        rid = self._generate_id(f"{pipeline_id}:{field_name}:{rule_type}")
        entry = _RuleEntry(
            rule_id=rid,
            pipeline_id=pipeline_id,
            field_name=field_name,
            rule_type=rule_type,
            value=value,
            seq=self._seq,
            created_at=time.time(),
        )
        self._rules[rid] = entry
        self._stats["rules_added"] += 1
        self._prune_if_needed()

        logger.info(
            "pipeline_input_validator.rule_added",
            rule_id=rid,
            pipeline_id=pipeline_id,
            field_name=field_name,
            rule_type=rule_type,
        )
        self._fire("rule_added", {"rule_id": rid, "pipeline_id": pipeline_id})
        return rid

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by its ID.  Returns ``True`` on success."""
        entry = self._rules.pop(rule_id, None)
        if entry is None:
            return False

        self._stats["rules_removed"] += 1
        logger.info(
            "pipeline_input_validator.rule_removed",
            rule_id=rule_id,
            pipeline_id=entry.pipeline_id,
        )
        self._fire("rule_removed", {"rule_id": rule_id, "pipeline_id": entry.pipeline_id})
        return True

    def get_rules(self, pipeline_id: str) -> List[Dict]:
        """Return all rules registered for *pipeline_id*."""
        results: List[Dict] = []
        for entry in self._rules.values():
            if entry.pipeline_id != pipeline_id:
                continue
            results.append({
                "rule_id": entry.rule_id,
                "pipeline_id": entry.pipeline_id,
                "field_name": entry.field_name,
                "rule_type": entry.rule_type,
                "value": entry.value,
                "seq": entry.seq,
                "created_at": entry.created_at,
            })
        results.sort(key=lambda r: r["seq"])
        return results

    def get_rule_count(self) -> int:
        """Return the total number of registered rules across all pipelines."""
        return len(self._rules)

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of distinct pipeline IDs that have rules."""
        pipeline_ids: set[str] = set()
        for entry in self._rules.values():
            pipeline_ids.add(entry.pipeline_id)
        return sorted(pipeline_ids)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, pipeline_id: str, data: Dict) -> Dict:
        """Validate *data* against all rules for *pipeline_id*.

        Returns ``{"valid": bool, "errors": List[str]}``.
        """
        self._stats["validations_run"] += 1
        errors: List[str] = []

        for entry in self._rules.values():
            if entry.pipeline_id != pipeline_id:
                continue
            err = self._apply_rule(entry, data)
            if err:
                errors.append(err)

        valid = len(errors) == 0
        if valid:
            self._stats["validations_passed"] += 1
        else:
            self._stats["validations_failed"] += 1
            self._fire("validation_failed", {
                "pipeline_id": pipeline_id,
                "error_count": len(errors),
            })

        logger.info(
            "pipeline_input_validator.validated",
            pipeline_id=pipeline_id,
            valid=valid,
            error_count=len(errors),
        )
        return {"valid": valid, "errors": errors}

    # ------------------------------------------------------------------
    # Rule application (internal)
    # ------------------------------------------------------------------

    def _apply_rule(self, entry: _RuleEntry, data: Dict) -> str:
        """Apply a single rule to *data*.  Returns an error string or ``""``."""
        field_name = entry.field_name
        value = data.get(field_name)

        if entry.rule_type == "required":
            if field_name not in data or value is None:
                return f"{field_name}: field is required"
            return ""

        # For non-required rules, skip if field is absent.
        if field_name not in data or value is None:
            return ""

        if entry.rule_type == "min":
            threshold = entry.value
            if isinstance(value, (int, float)) and value < threshold:
                return f"{field_name}: value {value} is below minimum {threshold}"
            return ""

        if entry.rule_type == "max":
            threshold = entry.value
            if isinstance(value, (int, float)) and value > threshold:
                return f"{field_name}: value {value} is above maximum {threshold}"
            return ""

        if entry.rule_type == "type":
            expected_type = TYPE_MAP.get(str(entry.value))
            if expected_type is None:
                return f"{field_name}: unknown type constraint '{entry.value}'"
            if not isinstance(value, expected_type):
                return f"{field_name}: expected type {entry.value}, got {type(value).__name__}"
            return ""

        if entry.rule_type == "pattern":
            pattern = str(entry.value) if entry.value else ""
            if not pattern:
                return ""
            if not isinstance(value, str):
                return f"{field_name}: pattern rule requires a string value"
            try:
                if not re.search(pattern, value):
                    return f"{field_name}: value does not match pattern '{pattern}'"
            except re.error as exc:
                return f"{field_name}: invalid regex pattern '{pattern}': {exc}"
            return ""

        return ""

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> bool:
        """Register a callback.  Returns ``False`` if *name* already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = cb
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception(
                    "pipeline_input_validator.callback_error",
                    action=action,
                )

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_rules": len(self._rules),
            "current_pipelines": len(self.list_pipelines()),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all rules, callbacks, and statistics."""
        self._rules.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_input_validator.reset")
