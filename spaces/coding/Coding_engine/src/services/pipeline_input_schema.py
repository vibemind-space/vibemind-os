"""Pipeline Input Schema -- defines, validates, and transforms pipeline stage inputs.

Provides input definition with typed fields, validation with type coercion,
merging of input definitions, and tag-based organization. Distinct from
pipeline_schema_registry -- this focuses on input transformation and coercion.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# Supported field types and their Python type mappings
_TYPE_MAP: Dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

def _coerce_value(value: Any, target_type: str) -> tuple:
    """Attempt to coerce a value to the target type.

    Returns:
        Tuple of (success: bool, coerced_value: Any).
    """
    python_type = _TYPE_MAP.get(target_type)
    if python_type is None:
        return False, value

    if isinstance(value, python_type):
        return True, value

    # Allow int where float is expected without coercion
    if target_type == "float" and isinstance(value, int):
        return True, float(value)

    try:
        if target_type == "str":
            return True, str(value)
        if target_type == "int":
            return True, int(value)
        if target_type == "float":
            return True, float(value)
        if target_type == "bool":
            if isinstance(value, str):
                if value.lower() in ("true", "1", "yes"):
                    return True, True
                if value.lower() in ("false", "0", "no"):
                    return True, False
                return False, value
            return True, bool(value)
        if target_type == "list":
            if isinstance(value, (tuple, set)):
                return True, list(value)
            return False, value
        if target_type == "dict":
            return False, value
    except (ValueError, TypeError):
        return False, value

    return False, value


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _InputEntry:
    """Internal representation of a registered input definition."""
    input_id: str
    stage_name: str
    fields: Dict[str, Dict[str, Any]]
    description: str
    tags: List[str]
    created_at: float
    updated_at: float


# ---------------------------------------------------------------------------
# Pipeline Input Schema
# ---------------------------------------------------------------------------

class PipelineInputSchema:
    """Defines, validates, and transforms pipeline stage inputs.

    Each input definition declares a set of typed fields with required/optional
    flags and default values. Validation includes automatic type coercion where
    possible, returning both the validation result and the coerced data.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._inputs: Dict[str, _InputEntry] = {}       # input_id -> entry
        self._by_stage: Dict[str, str] = {}              # stage_name -> input_id
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # counters
        self._total_defined = 0
        self._total_validations = 0
        self._total_removed = 0
        self._total_merges = 0
        self._total_coercions = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, stage_name: str) -> str:
        """Generate a collision-free ID with prefix pis-."""
        self._seq += 1
        raw = f"{stage_name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pis-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding max_entries."""
        while len(self._inputs) > self._max_entries:
            oldest_id = min(self._inputs, key=lambda k: self._inputs[k].created_at)
            entry = self._inputs.pop(oldest_id)
            if entry.stage_name in self._by_stage:
                del self._by_stage[entry.stage_name]

    # ------------------------------------------------------------------
    # define_input
    # ------------------------------------------------------------------

    def define_input(
        self,
        stage_name: str,
        fields: Dict[str, Dict[str, Any]],
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Define an input schema for a pipeline stage.

        Args:
            stage_name: Unique name for the pipeline stage.
            fields: Field definitions, e.g.
                {"field_name": {"type": "str", "required": True, "default": ""}}.
            description: Optional human-readable description.
            tags: Optional list of tags for categorization.

        Returns:
            Input ID string (pis-...), or "" if stage_name already exists.
        """
        if stage_name in self._by_stage:
            logger.warning("input_duplicate_stage", stage_name=stage_name)
            return ""

        input_id = self._generate_id(stage_name)
        now = time.time()

        # Normalize field specs: ensure each field has type, required, default
        normalized: Dict[str, Dict[str, Any]] = {}
        for fname, fspec in fields.items():
            normalized[fname] = {
                "type": fspec.get("type", "str"),
                "required": fspec.get("required", False),
                "default": fspec.get("default", None),
            }

        entry = _InputEntry(
            input_id=input_id,
            stage_name=stage_name,
            fields=normalized,
            description=description,
            tags=list(tags) if tags else [],
            created_at=now,
            updated_at=now,
        )

        self._inputs[input_id] = entry
        self._by_stage[stage_name] = input_id
        self._total_defined += 1

        self._prune()

        logger.info("input_defined", input_id=input_id, stage_name=stage_name)
        self._fire("define", {"input_id": input_id, "stage_name": stage_name})

        return input_id

    # ------------------------------------------------------------------
    # validate_input
    # ------------------------------------------------------------------

    def validate_input(
        self, stage_name: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and coerce data against a stage's input definition.

        Performs type checking and attempts automatic coercion where the
        raw value does not match the declared type. Missing optional fields
        are filled with their declared defaults.

        Args:
            stage_name: Name of the stage whose input def to validate against.
            data: Data dictionary to validate.

        Returns:
            Dict with keys:
                valid (bool): Whether data passes validation.
                errors (list[str]): List of error messages.
                coerced (dict): Data with type-coerced values and defaults applied.
        """
        self._total_validations += 1

        input_id = self._by_stage.get(stage_name)
        if input_id is None:
            return {
                "valid": False,
                "errors": [f"Input definition for stage '{stage_name}' not found"],
                "coerced": {},
            }

        entry = self._inputs.get(input_id)
        if entry is None:
            return {
                "valid": False,
                "errors": [f"Input definition for stage '{stage_name}' not found"],
                "coerced": {},
            }

        errors: List[str] = []
        coerced: Dict[str, Any] = {}

        for field_name, field_spec in entry.fields.items():
            required = field_spec.get("required", False)
            expected_type = field_spec.get("type", "str")
            default = field_spec.get("default", None)

            if field_name not in data:
                if required:
                    errors.append(f"Missing required field: '{field_name}'")
                elif default is not None:
                    coerced[field_name] = default
                continue

            value = data[field_name]
            success, coerced_val = _coerce_value(value, expected_type)

            if success:
                if coerced_val is not value:
                    self._total_coercions += 1
                coerced[field_name] = coerced_val
            else:
                errors.append(
                    f"Field '{field_name}' expected type '{expected_type}', "
                    f"got '{type(value).__name__}' and coercion failed"
                )
                coerced[field_name] = value

        # Pass through extra fields not in the definition
        for key, val in data.items():
            if key not in entry.fields:
                coerced[key] = val

        is_valid = len(errors) == 0

        self._fire("validate", {"stage_name": stage_name, "valid": is_valid})

        return {"valid": is_valid, "errors": errors, "coerced": coerced}

    # ------------------------------------------------------------------
    # get_input_def
    # ------------------------------------------------------------------

    def get_input_def(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve an input definition by stage name.

        Args:
            stage_name: Name of the pipeline stage.

        Returns:
            Input definition dict or None if not found.
        """
        input_id = self._by_stage.get(stage_name)
        if input_id is None:
            return None

        entry = self._inputs.get(input_id)
        if entry is None:
            return None

        return self._to_dict(entry)

    # ------------------------------------------------------------------
    # list_inputs
    # ------------------------------------------------------------------

    def list_inputs(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all registered input definitions, optionally filtered by tag.

        Args:
            tag: If provided, only return definitions containing this tag.

        Returns:
            List of input definition dicts sorted by creation time (newest first).
        """
        results: List[Dict[str, Any]] = []
        for entry in sorted(
            self._inputs.values(), key=lambda e: e.created_at, reverse=True
        ):
            if tag is not None and tag not in entry.tags:
                continue
            results.append(self._to_dict(entry))
        return results

    # ------------------------------------------------------------------
    # remove_input
    # ------------------------------------------------------------------

    def remove_input(self, stage_name: str) -> bool:
        """Remove an input definition by stage name.

        Args:
            stage_name: Name of the pipeline stage.

        Returns:
            True if removed, False if not found.
        """
        input_id = self._by_stage.pop(stage_name, None)
        if input_id is None:
            return False

        entry = self._inputs.pop(input_id, None)
        if entry is None:
            return False

        self._total_removed += 1

        logger.info("input_removed", input_id=input_id, stage_name=stage_name)
        self._fire("remove", {"input_id": input_id, "stage_name": stage_name})

        return True

    # ------------------------------------------------------------------
    # merge_inputs
    # ------------------------------------------------------------------

    def merge_inputs(
        self, stage_name1: str, stage_name2: str, new_name: str
    ) -> str:
        """Merge two input definitions into a new one.

        Combines fields from both definitions. If both define the same field,
        the definition from stage_name1 takes precedence. Tags are combined
        and deduplicated.

        Args:
            stage_name1: First stage name (takes precedence on conflicts).
            stage_name2: Second stage name.
            new_name: Name for the merged input definition.

        Returns:
            Input ID of the merged definition, or "" if any source is not
            found or new_name already exists.
        """
        if new_name in self._by_stage:
            logger.warning("merge_duplicate_name", new_name=new_name)
            return ""

        id1 = self._by_stage.get(stage_name1)
        id2 = self._by_stage.get(stage_name2)

        if id1 is None or id2 is None:
            missing = []
            if id1 is None:
                missing.append(stage_name1)
            if id2 is None:
                missing.append(stage_name2)
            logger.warning("merge_source_not_found", missing=missing)
            return ""

        entry1 = self._inputs.get(id1)
        entry2 = self._inputs.get(id2)

        if entry1 is None or entry2 is None:
            return ""

        # Merge fields: start with stage2, then overlay stage1
        merged_fields: Dict[str, Dict[str, Any]] = {}
        for fname, fspec in entry2.fields.items():
            merged_fields[fname] = dict(fspec)
        for fname, fspec in entry1.fields.items():
            merged_fields[fname] = dict(fspec)

        # Combine tags, deduplicated
        combined_tags = list(dict.fromkeys(entry1.tags + entry2.tags))

        # Combine descriptions
        parts = []
        if entry1.description:
            parts.append(entry1.description)
        if entry2.description:
            parts.append(entry2.description)
        merged_desc = " | ".join(parts)

        self._total_merges += 1

        input_id = self.define_input(
            stage_name=new_name,
            fields=merged_fields,
            description=merged_desc,
            tags=combined_tags,
        )

        if input_id:
            logger.info(
                "inputs_merged",
                source1=stage_name1,
                source2=stage_name2,
                new_name=new_name,
                input_id=input_id,
            )
            self._fire(
                "merge",
                {
                    "input_id": input_id,
                    "source1": stage_name1,
                    "source2": stage_name2,
                    "new_name": new_name,
                },
            )

        return input_id

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics.

        Returns:
            Dict with counters for definitions, validations, removals,
            merges, coercions, current entry count, callbacks, etc.
        """
        return {
            "total_defined": self._total_defined,
            "total_validations": self._total_validations,
            "total_removed": self._total_removed,
            "total_merges": self._total_merges,
            "total_coercions": self._total_coercions,
            "current_inputs": len(self._inputs),
            "unique_stages": len(self._by_stage),
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all input definitions, callbacks, and counters."""
        self._inputs.clear()
        self._by_stage.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_defined = 0
        self._total_validations = 0
        self._total_removed = 0
        self._total_merges = 0
        self._total_coercions = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(entry: _InputEntry) -> Dict[str, Any]:
        """Convert an input entry to a plain dict for external consumption."""
        return {
            "input_id": entry.input_id,
            "stage_name": entry.stage_name,
            "fields": {k: dict(v) for k, v in entry.fields.items()},
            "description": entry.description,
            "tags": list(entry.tags),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
