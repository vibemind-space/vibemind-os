"""Pipeline data validator.

Validates data flowing through the pipeline against defined schemas,
rules, and constraints. Tracks validation results and violations.
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Schema:
    """Validation schema."""
    schema_id: str = ""
    name: str = ""
    fields: Dict = field(default_factory=dict)  # field_name -> {type, required, ...}
    tags: List[str] = field(default_factory=list)
    status: str = "active"  # active, disabled, deprecated
    total_validated: int = 0
    total_passed: int = 0
    total_failed: int = 0
    created_at: float = 0.0


@dataclass
class _ValidationResult:
    """Result of a validation."""
    result_id: str = ""
    schema_id: str = ""
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data_source: str = ""
    timestamp: float = 0.0


@dataclass
class _Rule:
    """Custom validation rule."""
    rule_id: str = ""
    name: str = ""
    field_name: str = ""
    rule_type: str = ""  # min, max, pattern, in_list, not_empty, custom
    params: Dict = field(default_factory=dict)
    enabled: bool = True
    times_checked: int = 0
    times_failed: int = 0
    created_at: float = 0.0


FIELD_TYPES = ("string", "int", "float", "bool", "list", "dict", "any")
RULE_TYPES = ("min", "max", "pattern", "in_list", "not_empty", "min_length",
              "max_length", "type_check")


class PipelineDataValidator:
    """Validates data against schemas and rules."""

    def __init__(self, max_schemas: int = 5000, max_rules: int = 10000,
                 max_results: int = 50000):
        self._max_schemas = max_schemas
        self._max_rules = max_rules
        self._max_results = max_results
        self._schemas: Dict[str, _Schema] = {}
        self._rules: Dict[str, _Rule] = {}
        self._results: Dict[str, _ValidationResult] = {}
        self._schema_rules: Dict[str, List[str]] = {}  # schema_id -> [rule_ids]
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_schemas_created": 0,
            "total_validations": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_rules_created": 0,
        }

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_schema(self, name: str, fields: Optional[Dict] = None,
                      tags: Optional[List[str]] = None) -> str:
        """Create a validation schema."""
        if not name:
            return ""
        if len(self._schemas) >= self._max_schemas:
            return ""

        sid = "schema-" + hashlib.md5(
            f"{name}{time.time()}".encode()
        ).hexdigest()[:12]

        self._schemas[sid] = _Schema(
            schema_id=sid,
            name=name,
            fields=fields or {},
            tags=tags or [],
            created_at=time.time(),
        )
        self._schema_rules[sid] = []
        self._stats["total_schemas_created"] += 1
        return sid

    def get_schema(self, schema_id: str) -> Optional[Dict]:
        """Get schema info."""
        s = self._schemas.get(schema_id)
        if not s:
            return None
        return {
            "schema_id": s.schema_id,
            "name": s.name,
            "fields": dict(s.fields),
            "tags": list(s.tags),
            "status": s.status,
            "total_validated": s.total_validated,
            "total_passed": s.total_passed,
            "total_failed": s.total_failed,
            "rule_count": len(self._schema_rules.get(s.schema_id, [])),
        }

    def remove_schema(self, schema_id: str) -> bool:
        """Remove a schema."""
        if schema_id not in self._schemas:
            return False
        # Remove associated rules
        for rid in self._schema_rules.get(schema_id, []):
            self._rules.pop(rid, None)
        self._schema_rules.pop(schema_id, None)
        del self._schemas[schema_id]
        return True

    def disable_schema(self, schema_id: str) -> bool:
        """Disable a schema."""
        s = self._schemas.get(schema_id)
        if not s or s.status != "active":
            return False
        s.status = "disabled"
        return True

    def enable_schema(self, schema_id: str) -> bool:
        """Enable a schema."""
        s = self._schemas.get(schema_id)
        if not s or s.status != "disabled":
            return False
        s.status = "active"
        return True

    def update_fields(self, schema_id: str, fields: Dict) -> bool:
        """Update schema fields."""
        s = self._schemas.get(schema_id)
        if not s:
            return False
        s.fields.update(fields)
        return True

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, schema_id: str, name: str, field_name: str,
                 rule_type: str, params: Optional[Dict] = None) -> str:
        """Add a validation rule to a schema."""
        if schema_id not in self._schemas:
            return ""
        if not name or not field_name:
            return ""
        if rule_type not in RULE_TYPES:
            return ""
        if len(self._rules) >= self._max_rules:
            return ""

        rid = "vrule-" + hashlib.md5(
            f"{name}{field_name}{time.time()}".encode()
        ).hexdigest()[:12]

        self._rules[rid] = _Rule(
            rule_id=rid,
            name=name,
            field_name=field_name,
            rule_type=rule_type,
            params=params or {},
            created_at=time.time(),
        )
        self._schema_rules[schema_id].append(rid)
        self._stats["total_rules_created"] += 1
        return rid

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a validation rule."""
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        for rule_list in self._schema_rules.values():
            if rule_id in rule_list:
                rule_list.remove(rule_id)
        return True

    def get_rule(self, rule_id: str) -> Optional[Dict]:
        """Get rule info."""
        r = self._rules.get(rule_id)
        if not r:
            return None
        return {
            "rule_id": r.rule_id,
            "name": r.name,
            "field_name": r.field_name,
            "rule_type": r.rule_type,
            "params": dict(r.params),
            "enabled": r.enabled,
            "times_checked": r.times_checked,
            "times_failed": r.times_failed,
        }

    def enable_rule(self, rule_id: str) -> bool:
        """Enable a rule."""
        r = self._rules.get(rule_id)
        if not r or r.enabled:
            return False
        r.enabled = True
        return True

    def disable_rule(self, rule_id: str) -> bool:
        """Disable a rule."""
        r = self._rules.get(rule_id)
        if not r or not r.enabled:
            return False
        r.enabled = False
        return True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def check_data(self, schema_id: str, data: Dict,
                   data_source: str = "") -> Optional[Dict]:
        """Validate data against a schema. Returns validation result."""
        s = self._schemas.get(schema_id)
        if not s or s.status != "active":
            return None

        if len(self._results) >= self._max_results:
            self._prune_results()

        errors = []
        warnings = []

        # Check required fields
        for fname, fspec in s.fields.items():
            if isinstance(fspec, dict) and fspec.get("required", False):
                if fname not in data:
                    errors.append(f"Missing required field: {fname}")

        # Check field types
        for fname, fspec in s.fields.items():
            if fname not in data:
                continue
            if isinstance(fspec, dict) and "type" in fspec:
                expected = fspec["type"]
                if expected != "any" and not self._check_type(data[fname], expected):
                    errors.append(
                        f"Type mismatch for {fname}: expected {expected}"
                    )

        # Check rules
        for rid in self._schema_rules.get(schema_id, []):
            rule = self._rules.get(rid)
            if not rule or not rule.enabled:
                continue
            rule.times_checked += 1
            err = self._apply_rule(rule, data)
            if err:
                rule.times_failed += 1
                errors.append(err)

        # Record result
        passed = len(errors) == 0
        vid = "vr-" + hashlib.md5(
            f"{schema_id}{time.time()}{len(self._results)}".encode()
        ).hexdigest()[:12]

        self._results[vid] = _ValidationResult(
            result_id=vid,
            schema_id=schema_id,
            passed=passed,
            errors=errors,
            warnings=warnings,
            data_source=data_source,
            timestamp=time.time(),
        )

        s.total_validated += 1
        self._stats["total_validations"] += 1
        if passed:
            s.total_passed += 1
            self._stats["total_passed"] += 1
        else:
            s.total_failed += 1
            self._stats["total_failed"] += 1
            self._fire("validation_failed", {
                "result_id": vid, "schema_id": schema_id,
                "error_count": len(errors),
            })

        return {
            "result_id": vid,
            "passed": passed,
            "errors": list(errors),
            "warnings": list(warnings),
        }

    def get_result(self, result_id: str) -> Optional[Dict]:
        """Get validation result."""
        r = self._results.get(result_id)
        if not r:
            return None
        return {
            "result_id": r.result_id,
            "schema_id": r.schema_id,
            "passed": r.passed,
            "errors": list(r.errors),
            "warnings": list(r.warnings),
            "data_source": r.data_source,
            "timestamp": r.timestamp,
        }

    # ------------------------------------------------------------------
    # Rule application
    # ------------------------------------------------------------------

    def _check_type(self, value: Any, expected: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            "string": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        expected_type = type_map.get(expected)
        if not expected_type:
            return True
        # bool is subclass of int, handle specially
        if expected == "int" and isinstance(value, bool):
            return False
        return isinstance(value, expected_type)

    def _apply_rule(self, rule: _Rule, data: Dict) -> str:
        """Apply a rule. Returns error message or empty string."""
        value = data.get(rule.field_name)

        if rule.rule_type == "not_empty":
            if value is None or value == "" or value == [] or value == {}:
                return f"{rule.field_name}: must not be empty"

        if value is None:
            return ""  # Skip other rules if field not present

        if rule.rule_type == "min":
            threshold = rule.params.get("value", 0)
            if isinstance(value, (int, float)) and value < threshold:
                return f"{rule.field_name}: value {value} below minimum {threshold}"

        elif rule.rule_type == "max":
            threshold = rule.params.get("value", 0)
            if isinstance(value, (int, float)) and value > threshold:
                return f"{rule.field_name}: value {value} above maximum {threshold}"

        elif rule.rule_type == "pattern":
            pattern = rule.params.get("value", "")
            if isinstance(value, str) and pattern:
                if not re.match(pattern, value):
                    return f"{rule.field_name}: does not match pattern {pattern}"

        elif rule.rule_type == "in_list":
            allowed = rule.params.get("values", [])
            if value not in allowed:
                return f"{rule.field_name}: value not in allowed list"

        elif rule.rule_type == "min_length":
            length = rule.params.get("value", 0)
            if hasattr(value, "__len__") and len(value) < length:
                return f"{rule.field_name}: length below minimum {length}"

        elif rule.rule_type == "max_length":
            length = rule.params.get("value", 0)
            if hasattr(value, "__len__") and len(value) > length:
                return f"{rule.field_name}: length above maximum {length}"

        elif rule.rule_type == "type_check":
            expected = rule.params.get("value", "any")
            if not self._check_type(value, expected):
                return f"{rule.field_name}: type mismatch, expected {expected}"

        return ""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_schema_results(self, schema_id: str, passed: Optional[bool] = None,
                           limit: int = 50) -> List[Dict]:
        """Get validation results for a schema."""
        result = []
        for r in self._results.values():
            if r.schema_id != schema_id:
                continue
            if passed is not None and r.passed != passed:
                continue
            result.append({
                "result_id": r.result_id,
                "passed": r.passed,
                "error_count": len(r.errors),
                "timestamp": r.timestamp,
            })
        result.sort(key=lambda x: -x["timestamp"])
        return result[:limit]

    def get_pass_rate(self, schema_id: str) -> float:
        """Get pass rate for a schema."""
        s = self._schemas.get(schema_id)
        if not s or s.total_validated == 0:
            return 0.0
        return round(s.total_passed / s.total_validated, 4)

    def get_most_failing_rules(self, limit: int = 10) -> List[Dict]:
        """Get rules that fail most often."""
        items = sorted(
            [r for r in self._rules.values() if r.times_failed > 0],
            key=lambda r: -r.times_failed
        )
        return [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "field_name": r.field_name,
                "times_checked": r.times_checked,
                "times_failed": r.times_failed,
                "failure_rate": round(r.times_failed / r.times_checked, 4) if r.times_checked > 0 else 0,
            }
            for r in items[:limit]
        ]

    def list_schemas(self, status: Optional[str] = None,
                     tag: Optional[str] = None) -> List[Dict]:
        """List schemas with optional filters."""
        result = []
        for s in self._schemas.values():
            if status and s.status != status:
                continue
            if tag and tag not in s.tags:
                continue
            result.append({
                "schema_id": s.schema_id,
                "name": s.name,
                "status": s.status,
                "total_validated": s.total_validated,
                "rule_count": len(self._schema_rules.get(s.schema_id, [])),
            })
        return result

    def get_schema_rules(self, schema_id: str) -> List[Dict]:
        """Get all rules for a schema."""
        result = []
        for rid in self._schema_rules.get(schema_id, []):
            r = self._rules.get(rid)
            if r:
                result.append({
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "field_name": r.field_name,
                    "rule_type": r.rule_type,
                    "enabled": r.enabled,
                })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_results(self) -> None:
        """Remove oldest results."""
        items = sorted(self._results.items(), key=lambda x: x[1].timestamp)
        to_remove = len(items) // 4
        for k, _ in items[:to_remove]:
            del self._results[k]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_schemas": len(self._schemas),
            "active_schemas": sum(
                1 for s in self._schemas.values() if s.status == "active"
            ),
            "current_rules": len(self._rules),
            "current_results": len(self._results),
        }

    def reset(self) -> None:
        self._schemas.clear()
        self._rules.clear()
        self._results.clear()
        self._schema_rules.clear()
        self._stats = {k: 0 for k in self._stats}
