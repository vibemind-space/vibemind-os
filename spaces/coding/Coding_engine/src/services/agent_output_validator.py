"""Agent Output Validator – validates agent outputs against rules.

Registers validation rules per output type and validates agent outputs
against them. Supports schema checks, range validation, custom validators,
and tracks validation history with pass/fail statistics.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ValidationRule:
    rule_id: str
    name: str
    output_type: str
    validator_fn: Optional[Callable]
    required_fields: List[str]
    total_checked: int
    total_passed: int
    total_failed: int
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _ValidationResult:
    result_id: str
    rule_id: str
    agent: str
    passed: bool
    errors: List[str]
    timestamp: float


class AgentOutputValidator:
    """Validates agent outputs against registered rules."""

    def __init__(self, max_rules: int = 5000, max_history: int = 100000):
        self._rules: Dict[str, _ValidationRule] = {}
        self._name_index: Dict[str, str] = {}
        self._type_index: Dict[str, List[str]] = {}
        self._history: List[_ValidationResult] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_rules = max_rules
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_validations = 0
        self._total_passes = 0
        self._total_failures = 0

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(
        self,
        name: str,
        output_type: str,
        validator_fn: Optional[Callable] = None,
        required_fields: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or not output_type:
            return ""
        if name in self._name_index:
            return ""
        if len(self._rules) >= self._max_rules:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{output_type}-{now}-{self._seq}"
        rid = "vrl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        rule = _ValidationRule(
            rule_id=rid,
            name=name,
            output_type=output_type,
            validator_fn=validator_fn,
            required_fields=required_fields or [],
            total_checked=0,
            total_passed=0,
            total_failed=0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._rules[rid] = rule
        self._name_index[name] = rid
        self._type_index.setdefault(output_type, []).append(rid)
        self._fire("rule_added", {"rule_id": rid, "name": name})
        return rid

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        r = self._rules.get(rule_id)
        if not r:
            return None
        pass_rate = r.total_passed / r.total_checked if r.total_checked > 0 else 0.0
        return {
            "rule_id": r.rule_id,
            "name": r.name,
            "output_type": r.output_type,
            "required_fields": list(r.required_fields),
            "total_checked": r.total_checked,
            "total_passed": r.total_passed,
            "total_failed": r.total_failed,
            "pass_rate": pass_rate,
            "tags": list(r.tags),
            "created_at": r.created_at,
        }

    def get_rule_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        rid = self._name_index.get(name)
        if not rid:
            return None
        return self.get_rule(rid)

    def remove_rule(self, rule_id: str) -> bool:
        r = self._rules.pop(rule_id, None)
        if not r:
            return False
        self._name_index.pop(r.name, None)
        type_list = self._type_index.get(r.output_type, [])
        if rule_id in type_list:
            type_list.remove(rule_id)
        return True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(
        self,
        agent: str,
        output_type: str,
        output: Any,
    ) -> Dict[str, Any]:
        """Validate an agent output against all matching rules."""
        errors = []
        rules_checked = 0
        rules_passed = 0

        rule_ids = self._type_index.get(output_type, [])
        for rid in rule_ids:
            rule = self._rules.get(rid)
            if not rule:
                continue

            rule_errors = []
            rules_checked += 1
            rule.total_checked += 1

            # check required fields
            if rule.required_fields and isinstance(output, dict):
                for field_name in rule.required_fields:
                    if field_name not in output:
                        rule_errors.append(f"missing field: {field_name}")

            # run custom validator
            if rule.validator_fn:
                try:
                    result = rule.validator_fn(output)
                    if isinstance(result, list):
                        rule_errors.extend(result)
                    elif isinstance(result, str) and result:
                        rule_errors.append(result)
                    elif isinstance(result, bool) and not result:
                        rule_errors.append(f"rule '{rule.name}' failed")
                except Exception as exc:
                    rule_errors.append(f"validator error: {str(exc)}")

            if rule_errors:
                rule.total_failed += 1
                errors.extend(rule_errors)
            else:
                rule.total_passed += 1
                rules_passed += 1

            rule.updated_at = time.time()

        passed = len(errors) == 0
        self._total_validations += 1
        if passed:
            self._total_passes += 1
        else:
            self._total_failures += 1

        # record history
        self._seq += 1
        now = time.time()
        raw = f"{agent}-{output_type}-{now}-{self._seq}"
        vrid = "vrs-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        record = _ValidationResult(
            result_id=vrid,
            rule_id="",
            agent=agent,
            passed=passed,
            errors=errors,
            timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(record)

        if not passed:
            self._fire("validation_failed", {
                "agent": agent, "output_type": output_type,
                "errors": errors,
            })

        return {
            "passed": passed,
            "rules_checked": rules_checked,
            "rules_passed": rules_passed,
            "errors": errors,
        }

    def validate_single(self, rule_id: str, output: Any) -> Dict[str, Any]:
        """Validate output against a single rule."""
        rule = self._rules.get(rule_id)
        if not rule:
            return {"passed": False, "errors": ["rule not found"]}

        errors = []
        rule.total_checked += 1

        if rule.required_fields and isinstance(output, dict):
            for field_name in rule.required_fields:
                if field_name not in output:
                    errors.append(f"missing field: {field_name}")

        if rule.validator_fn:
            try:
                result = rule.validator_fn(output)
                if isinstance(result, list):
                    errors.extend(result)
                elif isinstance(result, str) and result:
                    errors.append(result)
                elif isinstance(result, bool) and not result:
                    errors.append(f"rule '{rule.name}' failed")
            except Exception as exc:
                errors.append(f"validator error: {str(exc)}")

        if errors:
            rule.total_failed += 1
        else:
            rule.total_passed += 1
        rule.updated_at = time.time()

        return {"passed": len(errors) == 0, "errors": errors}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_rules(
        self,
        output_type: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for r in self._rules.values():
            if output_type and r.output_type != output_type:
                continue
            if tag and tag not in r.tags:
                continue
            results.append(self.get_rule(r.rule_id))
        return results

    def get_history(
        self,
        agent: str = "",
        passed: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for r in reversed(self._history):
            if agent and r.agent != agent:
                continue
            if passed is not None and r.passed != passed:
                continue
            results.append({
                "result_id": r.result_id,
                "agent": r.agent,
                "passed": r.passed,
                "errors": list(r.errors),
                "timestamp": r.timestamp,
            })
            if len(results) >= limit:
                break
        return results

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
            "current_rules": len(self._rules),
            "total_validations": self._total_validations,
            "total_passes": self._total_passes,
            "total_failures": self._total_failures,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._rules.clear()
        self._name_index.clear()
        self._type_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_validations = 0
        self._total_passes = 0
        self._total_failures = 0
