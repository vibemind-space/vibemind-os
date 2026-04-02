"""Pipeline Schema Registry -- manages and validates data schemas for pipeline stages.

Provides schema registration with versioning, data validation against schemas,
compatibility checking between schemas, and tag-based organization.
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
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _SchemaEntry:
    """Internal representation of a registered schema."""
    schema_id: str
    name: str
    version: str
    schema_def: Dict[str, Dict[str, Any]]
    tags: List[str]
    created_at: float
    updated_at: float


# ---------------------------------------------------------------------------
# Pipeline Schema Registry
# ---------------------------------------------------------------------------

class PipelineSchemaRegistry:
    """Manages and validates data schemas for pipeline stages.

    Each schema defines a set of typed fields with required/optional flags.
    Schemas are versioned by name and can be tagged for organization.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._schemas: Dict[str, _SchemaEntry] = {}
        self._by_name: Dict[str, List[str]] = {}  # name -> [schema_ids]
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # counters
        self._total_registered = 0
        self._total_validations = 0
        self._total_removed = 0
        self._total_updates = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        """Generate a collision-free ID with prefix psr-."""
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"psr-{digest}"

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
        while len(self._schemas) > self._max_entries:
            # Find the oldest entry
            oldest_id = min(self._schemas, key=lambda k: self._schemas[k].created_at)
            entry = self._schemas.pop(oldest_id)
            # Clean up name index
            ids = self._by_name.get(entry.name, [])
            if oldest_id in ids:
                ids.remove(oldest_id)
            if not ids and entry.name in self._by_name:
                del self._by_name[entry.name]

    # ------------------------------------------------------------------
    # register_schema
    # ------------------------------------------------------------------

    def register_schema(
        self,
        name: str,
        schema_def: Dict[str, Dict[str, Any]],
        version: str = "1.0",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a new schema definition.

        Args:
            name: Unique schema name.
            schema_def: Field definitions, e.g.
                {"field_name": {"type": "str", "required": True}}.
            version: Version string (default "1.0").
            tags: Optional list of tags for categorization.

        Returns:
            Schema ID string (psr-...), or "" if a schema with this name
            already exists.
        """
        if name in self._by_name and self._by_name[name]:
            logger.warning("schema_duplicate_name", name=name)
            return ""

        schema_id = self._generate_id(name)
        now = time.time()

        entry = _SchemaEntry(
            schema_id=schema_id,
            name=name,
            version=version,
            schema_def=dict(schema_def),
            tags=list(tags) if tags else [],
            created_at=now,
            updated_at=now,
        )

        self._schemas[schema_id] = entry
        self._by_name.setdefault(name, []).append(schema_id)
        self._total_registered += 1

        self._prune()

        logger.info("schema_registered", schema_id=schema_id, name=name, version=version)
        self._fire("register", {"schema_id": schema_id, "name": name, "version": version})

        return schema_id

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(self, schema_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data against a named schema.

        Args:
            schema_name: Name of the schema to validate against.
            data: Data dictionary to validate.

        Returns:
            Dict with keys:
                valid (bool): Whether data passes validation.
                errors (list[str]): List of error messages.
        """
        self._total_validations += 1

        # Resolve name to latest schema
        ids = self._by_name.get(schema_name, [])
        if not ids:
            return {"valid": False, "errors": [f"Schema '{schema_name}' not found"]}

        entry = self._schemas.get(ids[-1])
        if entry is None:
            return {"valid": False, "errors": [f"Schema '{schema_name}' not found"]}

        errors: List[str] = []

        for field_name, field_spec in entry.schema_def.items():
            required = field_spec.get("required", False)
            expected_type = field_spec.get("type", "str")

            if field_name not in data:
                if required:
                    errors.append(f"Missing required field: '{field_name}'")
                continue

            value = data[field_name]
            python_type = _TYPE_MAP.get(expected_type)
            if python_type is not None and not isinstance(value, python_type):
                # Allow int where float is expected
                if expected_type == "float" and isinstance(value, int):
                    continue
                errors.append(
                    f"Field '{field_name}' expected type '{expected_type}', "
                    f"got '{type(value).__name__}'"
                )

        self._fire("validate", {"schema_name": schema_name, "valid": len(errors) == 0})

        return {"valid": len(errors) == 0, "errors": errors}

    # ------------------------------------------------------------------
    # get_schema
    # ------------------------------------------------------------------

    def get_schema(self, schema_id_or_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a schema by ID or by name.

        Args:
            schema_id_or_name: Schema ID (psr-...) or schema name.

        Returns:
            Schema dict or None if not found.
        """
        # Try direct ID lookup first
        entry = self._schemas.get(schema_id_or_name)
        if entry is not None:
            return self._to_dict(entry)

        # Try name lookup (return latest)
        ids = self._by_name.get(schema_id_or_name, [])
        if ids:
            entry = self._schemas.get(ids[-1])
            if entry is not None:
                return self._to_dict(entry)

        return None

    # ------------------------------------------------------------------
    # update_schema
    # ------------------------------------------------------------------

    def update_schema(
        self,
        schema_id: str,
        schema_def: Optional[Dict[str, Dict[str, Any]]] = None,
        version: Optional[str] = None,
    ) -> bool:
        """Update an existing schema's definition and/or version.

        Args:
            schema_id: ID of the schema to update.
            schema_def: New field definitions (optional).
            version: New version string (optional).

        Returns:
            True if updated, False if schema_id not found.
        """
        entry = self._schemas.get(schema_id)
        if entry is None:
            return False

        if schema_def is not None:
            entry.schema_def = dict(schema_def)
        if version is not None:
            entry.version = version
        entry.updated_at = time.time()

        self._total_updates += 1

        logger.info("schema_updated", schema_id=schema_id, version=entry.version)
        self._fire("update", {"schema_id": schema_id, "version": entry.version})

        return True

    # ------------------------------------------------------------------
    # list_schemas
    # ------------------------------------------------------------------

    def list_schemas(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all registered schemas, optionally filtered by tag.

        Args:
            tag: If provided, only return schemas containing this tag.

        Returns:
            List of schema dicts sorted by creation time (newest first).
        """
        results: List[Dict[str, Any]] = []
        for entry in sorted(self._schemas.values(), key=lambda e: e.created_at, reverse=True):
            if tag is not None and tag not in entry.tags:
                continue
            results.append(self._to_dict(entry))
        return results

    # ------------------------------------------------------------------
    # remove_schema
    # ------------------------------------------------------------------

    def remove_schema(self, schema_id: str) -> bool:
        """Remove a schema by ID.

        Args:
            schema_id: ID of the schema to remove.

        Returns:
            True if removed, False if not found.
        """
        entry = self._schemas.pop(schema_id, None)
        if entry is None:
            return False

        # Clean up name index
        ids = self._by_name.get(entry.name, [])
        if schema_id in ids:
            ids.remove(schema_id)
        if not ids and entry.name in self._by_name:
            del self._by_name[entry.name]

        self._total_removed += 1

        logger.info("schema_removed", schema_id=schema_id, name=entry.name)
        self._fire("remove", {"schema_id": schema_id, "name": entry.name})

        return True

    # ------------------------------------------------------------------
    # get_compatibility
    # ------------------------------------------------------------------

    def get_compatibility(
        self, schema_id1: str, schema_id2: str
    ) -> Dict[str, Any]:
        """Check compatibility between two schemas.

        Two schemas are compatible if they share the same required fields
        with matching types. Extra optional fields do not break compatibility.

        Args:
            schema_id1: First schema ID.
            schema_id2: Second schema ID.

        Returns:
            Dict with keys:
                compatible (bool): Whether schemas are compatible.
                differences (list[str]): List of difference descriptions.
        """
        entry1 = self._schemas.get(schema_id1)
        entry2 = self._schemas.get(schema_id2)

        if entry1 is None or entry2 is None:
            missing = []
            if entry1 is None:
                missing.append(schema_id1)
            if entry2 is None:
                missing.append(schema_id2)
            return {
                "compatible": False,
                "differences": [f"Schema not found: {sid}" for sid in missing],
            }

        differences: List[str] = []
        all_fields = set(entry1.schema_def.keys()) | set(entry2.schema_def.keys())

        for field_name in sorted(all_fields):
            spec1 = entry1.schema_def.get(field_name)
            spec2 = entry2.schema_def.get(field_name)

            if spec1 is None:
                differences.append(
                    f"Field '{field_name}' only in schema '{entry2.name}'"
                )
                continue
            if spec2 is None:
                differences.append(
                    f"Field '{field_name}' only in schema '{entry1.name}'"
                )
                continue

            type1 = spec1.get("type", "str")
            type2 = spec2.get("type", "str")
            if type1 != type2:
                differences.append(
                    f"Field '{field_name}' type mismatch: "
                    f"'{type1}' vs '{type2}'"
                )

            req1 = spec1.get("required", False)
            req2 = spec2.get("required", False)
            if req1 != req2:
                differences.append(
                    f"Field '{field_name}' required mismatch: "
                    f"{req1} vs {req2}"
                )

        return {"compatible": len(differences) == 0, "differences": differences}

    # ------------------------------------------------------------------
    # get_versions
    # ------------------------------------------------------------------

    def get_versions(self, schema_name: str) -> List[str]:
        """Get all version strings registered under a schema name.

        Args:
            schema_name: Name of the schema.

        Returns:
            List of version strings in registration order.
        """
        ids = self._by_name.get(schema_name, [])
        versions: List[str] = []
        for sid in ids:
            entry = self._schemas.get(sid)
            if entry is not None:
                versions.append(entry.version)
        return versions

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics.

        Returns:
            Dict with counters for registrations, validations, updates,
            removals, current schema count, unique names, callbacks, etc.
        """
        return {
            "total_registered": self._total_registered,
            "total_validations": self._total_validations,
            "total_updates": self._total_updates,
            "total_removed": self._total_removed,
            "current_schemas": len(self._schemas),
            "unique_names": len(self._by_name),
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all schemas, callbacks, and counters."""
        self._schemas.clear()
        self._by_name.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_validations = 0
        self._total_removed = 0
        self._total_updates = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(entry: _SchemaEntry) -> Dict[str, Any]:
        """Convert a schema entry to a plain dict for external consumption."""
        return {
            "schema_id": entry.schema_id,
            "name": entry.name,
            "version": entry.version,
            "schema_def": dict(entry.schema_def),
            "tags": list(entry.tags),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
