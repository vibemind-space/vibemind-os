"""Pipeline Schema Validator – validates data structures against registered schemas.

Defines schemas with required/optional fields, type constraints,
and custom validators. Validates payloads and tracks results.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _SchemaEntry:
    entry_id: str
    name: str
    fields: Dict[str, Dict[str, Any]]  # field_name -> {type, required, default, validator}
    tags: List[str]
    total_validations: int
    total_passed: int
    total_failed: int
    created_at: float
    updated_at: float


@dataclass
class _ValidationEvent:
    event_id: str
    schema_name: str
    passed: bool
    errors: List[str]
    timestamp: float


class PipelineSchemaValidator:
    """Validates data structures against registered schemas."""

    FIELD_TYPES = ("str", "int", "float", "bool", "list", "dict", "any")
    TYPE_MAP = {
        "str": str, "int": int, "float": (int, float),
        "bool": bool, "list": list, "dict": dict,
    }

    def __init__(self, max_schemas: int = 5000, max_history: int = 100000):
        self._schemas: Dict[str, _SchemaEntry] = {}
        self._name_index: Dict[str, str] = {}  # name -> entry_id
        self._history: List[_ValidationEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_schemas = max_schemas
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_validations = 0
        self._total_passed = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def register_schema(
        self,
        name: str,
        fields: Optional[Dict[str, Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a schema. Fields dict maps field_name to {type, required, default, validator}.

        Example fields:
            {"name": {"type": "str", "required": True},
             "age": {"type": "int", "required": False, "default": 0}}
        """
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._schemas) >= self._max_schemas:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        eid = "sch-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        # Normalise field definitions
        normalised: Dict[str, Dict[str, Any]] = {}
        for fname, fdef in (fields or {}).items():
            normalised[fname] = {
                "type": fdef.get("type", "any"),
                "required": fdef.get("required", True),
                "default": fdef.get("default"),
                "validator": fdef.get("validator"),
            }

        entry = _SchemaEntry(
            entry_id=eid,
            name=name,
            fields=normalised,
            tags=tags or [],
            total_validations=0,
            total_passed=0,
            total_failed=0,
            created_at=now,
            updated_at=now,
        )
        self._schemas[eid] = entry
        self._name_index[name] = eid
        self._total_created += 1
        self._fire("schema_registered", {"entry_id": eid, "name": name})
        return eid

    def get_schema(self, entry_id: str) -> Optional[Dict[str, Any]]:
        e = self._schemas.get(entry_id)
        if not e:
            return None
        return {
            "entry_id": e.entry_id,
            "name": e.name,
            "fields": {k: {kk: vv for kk, vv in v.items() if kk != "validator"}
                       for k, v in e.fields.items()},
            "tags": list(e.tags),
            "total_validations": e.total_validations,
            "total_passed": e.total_passed,
            "total_failed": e.total_failed,
            "created_at": e.created_at,
        }

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        eid = self._name_index.get(name)
        if not eid:
            return None
        return self.get_schema(eid)

    def remove_schema(self, entry_id: str) -> bool:
        e = self._schemas.pop(entry_id, None)
        if not e:
            return False
        self._name_index.pop(e.name, None)
        return True

    def add_field(self, entry_id: str, field_name: str, field_def: Dict[str, Any]) -> bool:
        """Add a field to an existing schema."""
        e = self._schemas.get(entry_id)
        if not e or not field_name:
            return False
        if field_name in e.fields:
            return False
        e.fields[field_name] = {
            "type": field_def.get("type", "any"),
            "required": field_def.get("required", True),
            "default": field_def.get("default"),
            "validator": field_def.get("validator"),
        }
        e.updated_at = time.time()
        return True

    def remove_field(self, entry_id: str, field_name: str) -> bool:
        """Remove a field from a schema."""
        e = self._schemas.get(entry_id)
        if not e or field_name not in e.fields:
            return False
        del e.fields[field_name]
        e.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data against a named schema. Returns {passed, errors, schema}."""
        eid = self._name_index.get(name)
        if not eid:
            return {"passed": False, "errors": [f"Schema '{name}' not found"], "schema": name}

        entry = self._schemas[eid]
        errors: List[str] = []

        for fname, fdef in entry.fields.items():
            required = fdef["required"]
            ftype = fdef["type"]
            validator = fdef.get("validator")

            if fname not in data:
                if required:
                    errors.append(f"Missing required field: {fname}")
                continue

            value = data[fname]

            # Type check
            if ftype != "any" and ftype in self.TYPE_MAP:
                expected = self.TYPE_MAP[ftype]
                if not isinstance(value, expected):
                    errors.append(f"Field '{fname}': expected {ftype}, got {type(value).__name__}")
                    continue

            # Custom validator
            if validator and callable(validator):
                try:
                    result = validator(value)
                    if result is False:
                        errors.append(f"Field '{fname}': custom validation failed")
                    elif isinstance(result, str) and result:
                        errors.append(f"Field '{fname}': {result}")
                    elif isinstance(result, list):
                        errors.extend(result)
                except Exception as exc:
                    errors.append(f"Field '{fname}': validator error: {str(exc)}")

        passed = len(errors) == 0
        entry.total_validations += 1
        self._total_validations += 1
        if passed:
            entry.total_passed += 1
            self._total_passed += 1
        else:
            entry.total_failed += 1
            self._total_failed += 1

        self._record_event(name, passed, errors)
        return {"passed": passed, "errors": errors, "schema": name}

    def validate_field(self, name: str, field_name: str, value: Any) -> Dict[str, Any]:
        """Validate a single field value against a schema."""
        eid = self._name_index.get(name)
        if not eid:
            return {"passed": False, "errors": [f"Schema '{name}' not found"]}

        entry = self._schemas[eid]
        fdef = entry.fields.get(field_name)
        if not fdef:
            return {"passed": False, "errors": [f"Field '{field_name}' not in schema"]}

        errors: List[str] = []
        ftype = fdef["type"]
        validator = fdef.get("validator")

        if ftype != "any" and ftype in self.TYPE_MAP:
            expected = self.TYPE_MAP[ftype]
            if not isinstance(value, expected):
                errors.append(f"Expected {ftype}, got {type(value).__name__}")

        if not errors and validator and callable(validator):
            try:
                result = validator(value)
                if result is False:
                    errors.append("Custom validation failed")
                elif isinstance(result, str) and result:
                    errors.append(result)
            except Exception as exc:
                errors.append(f"Validator error: {str(exc)}")

        return {"passed": len(errors) == 0, "errors": errors}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_schemas(
        self,
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in self._schemas.values():
            if tag and tag not in e.tags:
                continue
            results.append(self.get_schema(e.entry_id))
        return results

    def get_history(
        self,
        schema_name: str = "",
        passed: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if schema_name and ev.schema_name != schema_name:
                continue
            if passed is not None and ev.passed != passed:
                continue
            results.append({
                "event_id": ev.event_id,
                "schema_name": ev.schema_name,
                "passed": ev.passed,
                "errors": list(ev.errors),
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, schema_name: str, passed: bool, errors: List[str]) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{schema_name}-{passed}-{now}-{self._seq}"
        evid = "sev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _ValidationEvent(
            event_id=evid,
            schema_name=schema_name,
            passed=passed,
            errors=errors,
            timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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
            "current_schemas": len(self._schemas),
            "total_created": self._total_created,
            "total_validations": self._total_validations,
            "total_passed": self._total_passed,
            "total_failed": self._total_failed,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._schemas.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_validations = 0
        self._total_passed = 0
        self._total_failed = 0
