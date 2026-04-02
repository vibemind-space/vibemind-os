"""Pipeline step validator - validates pipeline step inputs and outputs against defined schemas.

Defines input/output schemas per pipeline step and validates data
against those schemas with type checking and error reporting.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

VALID_TYPES = ("str", "int", "float", "bool", "list", "dict")
TYPE_MAP: Dict[str, type | tuple] = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "list": list,
    "dict": dict,
}


@dataclass
class PipelineStepValidator:
    """Validates pipeline step inputs and outputs against defined schemas."""

    max_entries: int = 10000
    _schemas: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _key_index: Dict[str, str] = field(default_factory=dict)  # "pipeline_id::step_name" -> schema_id
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_schemas_defined: int = field(default=0)
    _total_validations: int = field(default=0)
    _total_passed: int = field(default=0)
    _total_failed: int = field(default=0)

    def _next_id(self, seed: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{seed}{self._seq}".encode()).hexdigest()[:12]
        return f"psv-{raw}"

    def _prune(self) -> None:
        while len(self._schemas) > self.max_entries:
            oldest_id = min(
                self._schemas,
                key=lambda sid: self._schemas[sid]["created_at"],
            )
            entry = self._schemas.pop(oldest_id)
            key = f"{entry['pipeline_id']}::{entry['step_name']}"
            self._key_index.pop(key, None)
            logger.debug("pipeline_step_validator.pruned", schema_id=oldest_id)

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "pipeline_step_validator.callback_error",
                    callback=name,
                    event=event,
                )

    # -- schema management ---------------------------------------------------

    def define_schema(
        self,
        pipeline_id: str,
        step_name: str,
        input_fields: Optional[Dict[str, str]] = None,
        output_fields: Optional[Dict[str, str]] = None,
    ) -> str:
        """Define a schema for a pipeline step.

        input_fields and output_fields are dicts like {"field_name": "type"}
        where type is one of "str", "int", "float", "bool", "list", "dict".

        Returns the schema_id (prefixed with 'psv-').
        """
        key = f"{pipeline_id}::{step_name}"

        # If schema already exists for this pipeline+step, update it
        if key in self._key_index:
            existing_id = self._key_index[key]
            existing = self._schemas[existing_id]
            existing["input_fields"] = dict(input_fields or {})
            existing["output_fields"] = dict(output_fields or {})
            existing["updated_at"] = time.time()
            logger.info(
                "pipeline_step_validator.schema_updated",
                schema_id=existing_id,
                pipeline_id=pipeline_id,
                step_name=step_name,
            )
            self._fire("schema_updated", {"schema_id": existing_id, "pipeline_id": pipeline_id, "step_name": step_name})
            return existing_id

        schema_id = self._next_id(key)
        now = time.time()
        entry: Dict[str, Any] = {
            "schema_id": schema_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "input_fields": dict(input_fields or {}),
            "output_fields": dict(output_fields or {}),
            "created_at": now,
            "updated_at": now,
        }
        self._schemas[schema_id] = entry
        self._key_index[key] = schema_id
        self._total_schemas_defined += 1
        self._prune()
        logger.info(
            "pipeline_step_validator.schema_defined",
            schema_id=schema_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
        )
        self._fire("schema_defined", {"schema_id": schema_id, "pipeline_id": pipeline_id, "step_name": step_name})
        return schema_id

    def get_schema(self, pipeline_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """Get a schema for a pipeline step. Returns None if not found."""
        key = f"{pipeline_id}::{step_name}"
        schema_id = self._key_index.get(key)
        if not schema_id:
            return None
        entry = self._schemas.get(schema_id)
        if not entry:
            return None
        return dict(entry)

    def list_schemas(self, pipeline_id: str = "") -> List[Dict[str, Any]]:
        """List all schemas, optionally filtered by pipeline_id."""
        results: List[Dict[str, Any]] = []
        for entry in self._schemas.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        return results

    def get_schema_count(self) -> int:
        """Return the total number of schemas."""
        return len(self._schemas)

    def list_pipelines(self) -> List[str]:
        """Return a list of unique pipeline IDs that have schemas."""
        seen: set[str] = set()
        result: List[str] = []
        for entry in self._schemas.values():
            pid = entry["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # -- validation ----------------------------------------------------------

    def _validate_fields(
        self, data: Dict[str, Any], field_spec: Dict[str, str], direction: str
    ) -> List[str]:
        """Validate data against a field specification. Returns list of errors."""
        errors: List[str] = []

        for field_name, field_type in field_spec.items():
            if field_name not in data:
                errors.append(f"Missing required {direction} field: {field_name}")
                continue

            value = data[field_name]

            if field_type not in TYPE_MAP:
                errors.append(f"Unknown type '{field_type}' for {direction} field '{field_name}'")
                continue

            expected = TYPE_MAP[field_type]
            if not isinstance(value, expected):
                # Special case: don't accept bool as int/float
                if field_type in ("int", "float") and isinstance(value, bool):
                    errors.append(
                        f"{direction.capitalize()} field '{field_name}': expected {field_type}, got {type(value).__name__}"
                    )
                elif not isinstance(value, expected):
                    errors.append(
                        f"{direction.capitalize()} field '{field_name}': expected {field_type}, got {type(value).__name__}"
                    )

        return errors

    def validate_input(
        self, pipeline_id: str, step_name: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate input data for a pipeline step.

        Returns {"valid": bool, "errors": list}.
        """
        key = f"{pipeline_id}::{step_name}"
        schema_id = self._key_index.get(key)
        if not schema_id or schema_id not in self._schemas:
            self._total_validations += 1
            self._total_failed += 1
            return {"valid": False, "errors": [f"No schema defined for pipeline '{pipeline_id}', step '{step_name}'"]}

        entry = self._schemas[schema_id]
        errors = self._validate_fields(data, entry["input_fields"], "input")
        valid = len(errors) == 0

        self._total_validations += 1
        if valid:
            self._total_passed += 1
        else:
            self._total_failed += 1

        logger.debug(
            "pipeline_step_validator.input_validated",
            pipeline_id=pipeline_id,
            step_name=step_name,
            valid=valid,
        )
        self._fire(
            "input_validated",
            {"pipeline_id": pipeline_id, "step_name": step_name, "valid": valid, "errors": errors},
        )
        return {"valid": valid, "errors": errors}

    def validate_output(
        self, pipeline_id: str, step_name: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate output data for a pipeline step.

        Returns {"valid": bool, "errors": list}.
        """
        key = f"{pipeline_id}::{step_name}"
        schema_id = self._key_index.get(key)
        if not schema_id or schema_id not in self._schemas:
            self._total_validations += 1
            self._total_failed += 1
            return {"valid": False, "errors": [f"No schema defined for pipeline '{pipeline_id}', step '{step_name}'"]}

        entry = self._schemas[schema_id]
        errors = self._validate_fields(data, entry["output_fields"], "output")
        valid = len(errors) == 0

        self._total_validations += 1
        if valid:
            self._total_passed += 1
        else:
            self._total_failed += 1

        logger.debug(
            "pipeline_step_validator.output_validated",
            pipeline_id=pipeline_id,
            step_name=step_name,
            valid=valid,
        )
        self._fire(
            "output_validated",
            {"pipeline_id": pipeline_id, "step_name": step_name, "valid": valid, "errors": errors},
        )
        return {"valid": valid, "errors": errors}

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback
        logger.debug("pipeline_step_validator.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if found, False otherwise."""
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("pipeline_step_validator.callback_removed", name=name)
            return True
        return False

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_schemas": len(self._schemas),
            "total_schemas_defined": self._total_schemas_defined,
            "total_validations": self._total_validations,
            "total_passed": self._total_passed,
            "total_failed": self._total_failed,
            "max_entries": self.max_entries,
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._schemas.clear()
        self._key_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_schemas_defined = 0
        self._total_validations = 0
        self._total_passed = 0
        self._total_failed = 0
        logger.info("pipeline_step_validator.reset")
