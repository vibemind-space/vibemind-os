"""Pipeline output validator.

Validates pipeline stage outputs against defined schemas and rules before
passing them to the next stage.  Ensures data quality and catches malformed
outputs early in the pipeline.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _ValidationStage:
    stage_id: str
    name: str
    tags: List[str]
    total_validations: int
    total_passes: int
    total_failures: int
    created_at: float


@dataclass
class _ValidationRule:
    rule_id: str
    stage_name: str
    rule_name: str
    rule_type: str
    config: Dict[str, Any]
    created_at: float


@dataclass
class _ValidationResult:
    result_id: str
    stage_name: str
    valid: bool
    errors: List[Dict[str, str]]
    warnings: List[str]
    timestamp: float


@dataclass
class _ValidationEvent:
    event_id: str
    stage_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


# ------------------------------------------------------------------
# Safe type mapping (no eval)
# ------------------------------------------------------------------

_TYPE_MAP: Dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


class PipelineOutputValidator:
    """Validate pipeline stage outputs against defined schemas/rules."""

    RULE_TYPES = ("required_field", "type_check", "range_check", "regex", "custom")

    def __init__(self, max_stages: int = 5000, max_history: int = 100000):
        self._stages: Dict[str, _ValidationStage] = {}
        self._name_index: Dict[str, str] = {}          # name -> stage_id
        self._rules: Dict[str, List[_ValidationRule]] = {}  # stage_name -> rules
        self._history: List[_ValidationEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_stages = max(1, max_stages)
        self._max_history = max(1, max_history)
        self._seq = 0

        # stat counters
        self._total_stages_created = 0
        self._total_rules_created = 0
        self._total_validations = 0
        self._total_passes = 0
        self._total_failures = 0

    # ------------------------------------------------------------------
    # Stage management
    # ------------------------------------------------------------------

    def register_stage(self, name: str, tags: Optional[List[str]] = None) -> str:
        """Register a pipeline stage. Returns stage ID (prefix ``ovs-``)."""
        if not name or name in self._name_index:
            return ""
        if len(self._stages) >= self._max_stages:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        sid = "ovs-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        stage = _ValidationStage(
            stage_id=sid,
            name=name,
            tags=tags or [],
            total_validations=0,
            total_passes=0,
            total_failures=0,
            created_at=now,
        )
        self._stages[sid] = stage
        self._name_index[name] = sid
        self._rules[name] = []
        self._total_stages_created += 1
        self._fire("stage_registered", {"stage_id": sid, "name": name})
        return sid

    def get_stage(self, name: str) -> Optional[Dict[str, Any]]:
        """Get stage details including rule count and pass rate."""
        sid = self._name_index.get(name)
        if not sid:
            return None
        s = self._stages[sid]
        pass_rate = 0.0
        if s.total_validations > 0:
            pass_rate = round(s.total_passes / s.total_validations * 100, 2)
        return {
            "stage_id": s.stage_id,
            "name": s.name,
            "tags": list(s.tags),
            "rule_count": len(self._rules.get(name, [])),
            "total_validations": s.total_validations,
            "total_passes": s.total_passes,
            "total_failures": s.total_failures,
            "pass_rate_pct": pass_rate,
            "created_at": s.created_at,
        }

    def remove_stage(self, name: str) -> bool:
        """Remove a stage and all its rules."""
        sid = self._name_index.pop(name, None)
        if not sid:
            return False
        self._stages.pop(sid, None)
        self._rules.pop(name, None)
        self._fire("stage_removed", {"stage_id": sid, "name": name})
        return True

    def list_stages(self, tag: str = "") -> List[Dict[str, Any]]:
        """List registered stages, optionally filtered by tag."""
        results: List[Dict[str, Any]] = []
        for s in self._stages.values():
            if tag and tag not in s.tags:
                continue
            pass_rate = 0.0
            if s.total_validations > 0:
                pass_rate = round(s.total_passes / s.total_validations * 100, 2)
            results.append({
                "stage_id": s.stage_id,
                "name": s.name,
                "tags": list(s.tags),
                "rule_count": len(self._rules.get(s.name, [])),
                "total_validations": s.total_validations,
                "pass_rate_pct": pass_rate,
            })
        return results

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(
        self,
        stage_name: str,
        rule_name: str,
        rule_type: str = "required_field",
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a validation rule to a stage. Returns rule ID (prefix ``ovr-``)."""
        if stage_name not in self._name_index:
            return ""
        if not rule_name:
            return ""
        if rule_type not in self.RULE_TYPES:
            return ""
        # Prevent duplicate rule names within a stage
        for r in self._rules.get(stage_name, []):
            if r.rule_name == rule_name:
                return ""

        self._seq += 1
        now = time.time()
        raw = f"{stage_name}-{rule_name}-{now}-{self._seq}"
        rid = "ovr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        rule = _ValidationRule(
            rule_id=rid,
            stage_name=stage_name,
            rule_name=rule_name,
            rule_type=rule_type,
            config=dict(config or {}),
            created_at=now,
        )
        self._rules[stage_name].append(rule)
        self._total_rules_created += 1
        self._fire("rule_added", {"rule_id": rid, "stage_name": stage_name, "rule_name": rule_name})
        return rid

    def remove_rule(self, stage_name: str, rule_name: str) -> bool:
        """Remove a rule from a stage."""
        rules = self._rules.get(stage_name)
        if rules is None:
            return False
        for i, r in enumerate(rules):
            if r.rule_name == rule_name:
                rules.pop(i)
                self._fire("rule_removed", {"stage_name": stage_name, "rule_name": rule_name})
                return True
        return False

    def get_rule(self, stage_name: str, rule_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific rule."""
        for r in self._rules.get(stage_name, []):
            if r.rule_name == rule_name:
                return {
                    "rule_id": r.rule_id,
                    "stage_name": r.stage_name,
                    "rule_name": r.rule_name,
                    "rule_type": r.rule_type,
                    "config": dict(r.config),
                    "created_at": r.created_at,
                }
        return None

    def list_rules(self, stage_name: str) -> List[Dict[str, Any]]:
        """List all rules for a stage."""
        results: List[Dict[str, Any]] = []
        for r in self._rules.get(stage_name, []):
            results.append({
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "rule_type": r.rule_type,
                "config": dict(r.config),
                "created_at": r.created_at,
            })
        return results

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, stage_name: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single output dict against the rules of *stage_name*.

        Returns ``{"valid": bool, "errors": [...], "warnings": [], "validated_at": float}``.
        """
        sid = self._name_index.get(stage_name)
        if not sid:
            return {
                "valid": False,
                "errors": [{"rule": "_system", "message": "stage not found"}],
                "warnings": [],
                "validated_at": time.time(),
            }

        stage = self._stages[sid]
        errors: List[Dict[str, str]] = []
        warnings: List[str] = []
        now = time.time()

        for rule in self._rules.get(stage_name, []):
            err = self._apply_rule(rule, output)
            if err:
                errors.append({"rule": rule.rule_name, "message": err})

        valid = len(errors) == 0

        # Update stage counters
        stage.total_validations += 1
        if valid:
            stage.total_passes += 1
        else:
            stage.total_failures += 1

        # Update global counters
        self._total_validations += 1
        if valid:
            self._total_passes += 1
        else:
            self._total_failures += 1

        # Record result in history
        self._seq += 1
        raw = f"result-{stage_name}-{now}-{self._seq}"
        result_id = "ovr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        self._record_event(stage_name, "validated", {
            "result_id": result_id,
            "valid": valid,
            "error_count": len(errors),
        })

        if not valid:
            self._fire("validation_failed", {
                "stage_name": stage_name,
                "error_count": len(errors),
                "errors": errors,
            })

        return {
            "valid": valid,
            "errors": errors,
            "warnings": warnings,
            "validated_at": now,
        }

    def validate_batch(
        self, stage_name: str, outputs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Validate a list of outputs against the rules of *stage_name*.

        Returns ``{"total": N, "valid_count": N, "invalid_count": N, "results": [...]}``.
        """
        results: List[Dict[str, Any]] = []
        valid_count = 0
        invalid_count = 0

        for output in outputs:
            result = self.validate(stage_name, output)
            results.append(result)
            if result["valid"]:
                valid_count += 1
            else:
                invalid_count += 1

        return {
            "total": len(outputs),
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "results": results,
        }

    # ------------------------------------------------------------------
    # Rule application
    # ------------------------------------------------------------------

    def _apply_rule(self, rule: _ValidationRule, output: Dict[str, Any]) -> str:
        """Apply a single rule to *output*. Returns error message or empty string."""
        cfg = rule.config

        if rule.rule_type == "required_field":
            field_name = cfg.get("field", "")
            if not field_name:
                return ""
            if field_name not in output or output[field_name] is None:
                return f"required field '{field_name}' is missing or None"
            return ""

        if rule.rule_type == "type_check":
            field_name = cfg.get("field", "")
            expected = cfg.get("expected_type", "str")
            if not field_name:
                return ""
            if field_name not in output:
                return f"field '{field_name}' not present for type check"
            expected_cls = _TYPE_MAP.get(expected)
            if expected_cls is None:
                return f"unknown expected_type '{expected}'"
            if not isinstance(output[field_name], expected_cls):
                actual = type(output[field_name]).__name__
                return f"field '{field_name}' expected type '{expected}' but got '{actual}'"
            return ""

        if rule.rule_type == "range_check":
            field_name = cfg.get("field", "")
            if not field_name or field_name not in output:
                return f"field '{field_name}' not present for range check" if field_name else ""
            value = output[field_name]
            if not isinstance(value, (int, float)):
                return f"field '{field_name}' is not numeric for range check"
            min_val = cfg.get("min")
            max_val = cfg.get("max")
            if min_val is not None and value < min_val:
                return f"field '{field_name}' value {value} is below minimum {min_val}"
            if max_val is not None and value > max_val:
                return f"field '{field_name}' value {value} is above maximum {max_val}"
            return ""

        if rule.rule_type == "regex":
            field_name = cfg.get("field", "")
            pattern = cfg.get("pattern", "")
            if not field_name or not pattern:
                return ""
            if field_name not in output:
                return f"field '{field_name}' not present for regex check"
            if not re.match(pattern, str(output[field_name])):
                return f"field '{field_name}' value '{output[field_name]}' does not match pattern '{pattern}'"
            return ""

        if rule.rule_type == "custom":
            # Placeholder for user-supplied validators; skip in this implementation
            return ""

        return ""

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_validation_summary(self) -> Dict[str, Any]:
        """Get an overall validation summary with per-stage breakdown."""
        pass_rate = 0.0
        if self._total_validations > 0:
            pass_rate = round(self._total_passes / self._total_validations * 100, 2)

        by_stage: List[Dict[str, Any]] = []
        for s in self._stages.values():
            stage_pass_rate = 0.0
            if s.total_validations > 0:
                stage_pass_rate = round(s.total_passes / s.total_validations * 100, 2)
            by_stage.append({
                "name": s.name,
                "total_validations": s.total_validations,
                "total_passes": s.total_passes,
                "total_failures": s.total_failures,
                "pass_rate_pct": stage_pass_rate,
            })

        return {
            "total_validations": self._total_validations,
            "total_passes": self._total_passes,
            "total_failures": self._total_failures,
            "pass_rate_pct": pass_rate,
            "by_stage": by_stage,
        }

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        limit: int = 50,
        stage_name: str = "",
        action: str = "",
    ) -> List[Dict[str, Any]]:
        """Return recent history events, most-recent first."""
        results: List[Dict[str, Any]] = []
        for ev in reversed(self._history):
            if stage_name and ev.stage_name != stage_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "stage_name": ev.stage_name,
                "action": ev.action,
                "data": dict(ev.data),
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, stage_name: str, action: str, data: Dict[str, Any]) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{stage_name}-{action}-{now}-{self._seq}"
        evid = "ove-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _ValidationEvent(
            event_id=evid,
            stage_name=stage_name,
            action=action,
            data=data,
            timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if *name* already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
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
        """Return aggregate statistics."""
        return {
            "total_stages": len(self._stages),
            "total_stages_created": self._total_stages_created,
            "total_rules_created": self._total_rules_created,
            "total_validations": self._total_validations,
            "total_passes": self._total_passes,
            "total_failures": self._total_failures,
            "history_size": len(self._history),
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all internal state."""
        self._stages.clear()
        self._name_index.clear()
        self._rules.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_stages_created = 0
        self._total_rules_created = 0
        self._total_validations = 0
        self._total_passes = 0
        self._total_failures = 0
