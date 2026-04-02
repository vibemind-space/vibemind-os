"""Pipeline config validator - validate configuration against schemas and rules."""

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Schema:
    schema_id: str
    name: str
    fields: Dict[str, Dict]  # field_name -> {type, required, default, min, max, pattern, choices}
    created_at: float
    metadata: Dict = field(default_factory=dict)


@dataclass
class _ValidationResult:
    result_id: str
    schema_id: str
    config_name: str
    valid: bool
    errors: List[Dict]  # [{field, message, severity}]
    warnings: List[Dict]
    timestamp: float


class PipelineConfigValidator:
    """Validate pipeline configurations against defined schemas."""

    FIELD_TYPES = ("string", "int", "float", "bool", "list", "dict", "any")

    def __init__(self, max_schemas: int = 500, max_results: int = 10000):
        self._max_schemas = max_schemas
        self._max_results = max_results
        self._schemas: Dict[str, _Schema] = {}
        self._results: List[_ValidationResult] = []
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_validations": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_errors_found": 0,
        }

    # ── Schema Management ──

    def create_schema(self, name: str, fields: Dict[str, Dict],
                      metadata: Optional[Dict] = None) -> str:
        """Create a validation schema.

        fields format: {
            "field_name": {
                "type": "string",   # required
                "required": True,   # optional, default False
                "default": None,    # optional
                "min": 0,           # optional (for int/float: value, for string: length)
                "max": 100,         # optional
                "pattern": "^...$", # optional (regex for strings)
                "choices": [...],   # optional (allowed values)
            }
        }
        """
        if len(self._schemas) >= self._max_schemas:
            return ""
        if not fields:
            return ""

        # Validate field definitions
        for fname, fdef in fields.items():
            ftype = fdef.get("type", "")
            if ftype not in self.FIELD_TYPES:
                return ""

        sid = f"schema-{uuid.uuid4().hex[:10]}"
        self._schemas[sid] = _Schema(
            schema_id=sid,
            name=name,
            fields=dict(fields),
            created_at=time.time(),
            metadata=metadata or {},
        )
        return sid

    def remove_schema(self, schema_id: str) -> bool:
        if schema_id not in self._schemas:
            return False
        del self._schemas[schema_id]
        return True

    def get_schema(self, schema_id: str) -> Optional[Dict]:
        s = self._schemas.get(schema_id)
        if not s:
            return None
        return {
            "schema_id": s.schema_id,
            "name": s.name,
            "fields": dict(s.fields),
            "field_count": len(s.fields),
        }

    def list_schemas(self) -> List[Dict]:
        return [
            {"schema_id": s.schema_id, "name": s.name, "field_count": len(s.fields)}
            for s in self._schemas.values()
        ]

    def add_field(self, schema_id: str, field_name: str, field_def: Dict) -> bool:
        """Add a field to a schema."""
        s = self._schemas.get(schema_id)
        if not s:
            return False
        if field_name in s.fields:
            return False
        ftype = field_def.get("type", "")
        if ftype not in self.FIELD_TYPES:
            return False
        s.fields[field_name] = dict(field_def)
        return True

    def remove_field(self, schema_id: str, field_name: str) -> bool:
        """Remove a field from a schema."""
        s = self._schemas.get(schema_id)
        if not s or field_name not in s.fields:
            return False
        del s.fields[field_name]
        return True

    # ── Validation ──

    def validate(self, schema_id: str, config: Dict,
                 config_name: str = "") -> Optional[Dict]:
        """Validate a config dict against a schema."""
        s = self._schemas.get(schema_id)
        if not s:
            return None

        errors = []
        warnings = []

        for fname, fdef in s.fields.items():
            required = fdef.get("required", False)
            ftype = fdef.get("type", "any")

            if fname not in config:
                if required:
                    errors.append({
                        "field": fname,
                        "message": f"required field '{fname}' is missing",
                        "severity": "error",
                    })
                continue

            value = config[fname]

            # Type check
            type_error = self._check_type(fname, value, ftype)
            if type_error:
                errors.append(type_error)
                continue

            # Range check (min/max)
            range_errors = self._check_range(fname, value, ftype, fdef)
            errors.extend(range_errors)

            # Pattern check
            pattern = fdef.get("pattern")
            if pattern and isinstance(value, str):
                if not re.match(pattern, value):
                    errors.append({
                        "field": fname,
                        "message": f"'{fname}' does not match pattern '{pattern}'",
                        "severity": "error",
                    })

            # Choices check
            choices = fdef.get("choices")
            if choices and value not in choices:
                errors.append({
                    "field": fname,
                    "message": f"'{fname}' must be one of {choices}",
                    "severity": "error",
                })

        # Check for unknown fields
        for key in config:
            if key not in s.fields:
                warnings.append({
                    "field": key,
                    "message": f"unknown field '{key}' not in schema",
                    "severity": "warning",
                })

        valid = len(errors) == 0
        self._stats["total_validations"] += 1
        self._stats["total_errors_found"] += len(errors)
        if valid:
            self._stats["total_passed"] += 1
        else:
            self._stats["total_failed"] += 1

        # Store result
        if len(self._results) >= self._max_results:
            self._results = self._results[-(self._max_results // 2):]

        rid = f"vres-{uuid.uuid4().hex[:10]}"
        self._results.append(_ValidationResult(
            result_id=rid,
            schema_id=schema_id,
            config_name=config_name,
            valid=valid,
            errors=errors,
            warnings=warnings,
            timestamp=time.time(),
        ))

        result = {
            "result_id": rid,
            "valid": valid,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
        }

        if not valid:
            self._fire_callbacks("validation_failed", rid, schema_id)

        return result

    def validate_batch(self, schema_id: str, configs: List[Dict]) -> List[Dict]:
        """Validate multiple configs against same schema."""
        results = []
        for i, config in enumerate(configs):
            r = self.validate(schema_id, config, config_name=f"config_{i}")
            if r:
                results.append(r)
        return results

    def _check_type(self, fname: str, value: Any, expected: str) -> Optional[Dict]:
        if expected == "any":
            return None
        type_map = {
            "string": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        expected_type = type_map.get(expected)
        if expected_type and not isinstance(value, expected_type):
            # Special: don't treat bool as int
            if expected == "int" and isinstance(value, bool):
                return {
                    "field": fname,
                    "message": f"'{fname}' expected {expected}, got bool",
                    "severity": "error",
                }
            return {
                "field": fname,
                "message": f"'{fname}' expected {expected}, got {type(value).__name__}",
                "severity": "error",
            }
        return None

    def _check_range(self, fname: str, value: Any, ftype: str,
                     fdef: Dict) -> List[Dict]:
        errors = []
        fmin = fdef.get("min")
        fmax = fdef.get("max")

        if ftype in ("int", "float") and isinstance(value, (int, float)):
            if fmin is not None and value < fmin:
                errors.append({
                    "field": fname,
                    "message": f"'{fname}' value {value} below minimum {fmin}",
                    "severity": "error",
                })
            if fmax is not None and value > fmax:
                errors.append({
                    "field": fname,
                    "message": f"'{fname}' value {value} above maximum {fmax}",
                    "severity": "error",
                })
        elif ftype == "string" and isinstance(value, str):
            if fmin is not None and len(value) < fmin:
                errors.append({
                    "field": fname,
                    "message": f"'{fname}' length {len(value)} below minimum {fmin}",
                    "severity": "error",
                })
            if fmax is not None and len(value) > fmax:
                errors.append({
                    "field": fname,
                    "message": f"'{fname}' length {len(value)} above maximum {fmax}",
                    "severity": "error",
                })
        elif ftype == "list" and isinstance(value, list):
            if fmin is not None and len(value) < fmin:
                errors.append({
                    "field": fname,
                    "message": f"'{fname}' length {len(value)} below minimum {fmin}",
                    "severity": "error",
                })
            if fmax is not None and len(value) > fmax:
                errors.append({
                    "field": fname,
                    "message": f"'{fname}' length {len(value)} above maximum {fmax}",
                    "severity": "error",
                })

        return errors

    # ── Results ──

    def get_result(self, result_id: str) -> Optional[Dict]:
        for r in self._results:
            if r.result_id == result_id:
                return {
                    "result_id": r.result_id,
                    "schema_id": r.schema_id,
                    "config_name": r.config_name,
                    "valid": r.valid,
                    "errors": r.errors,
                    "warnings": r.warnings,
                    "timestamp": r.timestamp,
                }
        return None

    def list_results(self, schema_id: str = "", valid: Optional[bool] = None,
                     limit: int = 50) -> List[Dict]:
        results = []
        for r in reversed(self._results):
            if schema_id and r.schema_id != schema_id:
                continue
            if valid is not None and r.valid != valid:
                continue
            results.append({
                "result_id": r.result_id,
                "schema_id": r.schema_id,
                "config_name": r.config_name,
                "valid": r.valid,
                "error_count": len(r.errors),
            })
            if len(results) >= limit:
                break
        return results

    # ── Defaults ──

    def get_defaults(self, schema_id: str) -> Dict:
        """Get default values for a schema."""
        s = self._schemas.get(schema_id)
        if not s:
            return {}
        defaults = {}
        for fname, fdef in s.fields.items():
            if "default" in fdef:
                defaults[fname] = fdef["default"]
        return defaults

    def apply_defaults(self, schema_id: str, config: Dict) -> Dict:
        """Apply default values for missing fields."""
        s = self._schemas.get(schema_id)
        if not s:
            return dict(config)
        result = dict(config)
        for fname, fdef in s.fields.items():
            if fname not in result and "default" in fdef:
                result[fname] = fdef["default"]
        return result

    # ── Callbacks ──

    def on_validation(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, action: str, result_id: str, schema_id: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, result_id, schema_id)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_schemas": len(self._schemas),
        }

    def reset(self) -> None:
        self._schemas.clear()
        self._results.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
