"""Agent Config Validator – validate agent configuration against defined schemas.

Provides schema definition, configuration validation, default extraction,
and change callbacks with pruning and statistics.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_TYPES = {"str", "int", "float", "bool", "list", "dict"}

TYPE_MAP = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


@dataclass
class AgentConfigValidatorState:
    entries: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0


class AgentConfigValidator:
    """Validate agent configuration against defined schemas.

    Schemas are stored keyed by agent_id. Each schema entry is also assigned
    a unique schema_id with prefix 'acv-'. Supports callbacks, pruning at
    10 000 entries, and statistics tracking.
    """

    def __init__(self) -> None:
        self._state = AgentConfigValidatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._total_defines: int = 0
        self._total_validations: int = 0
        self._total_removals: int = 0
        logger.info("agent_config_validator.initialized")

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, data: str) -> str:
        """Generate a unique ID using SHA256 and an incrementing sequence."""
        self._state._seq += 1
        raw = f"{data}{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"acv-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback by name."""
        self._callbacks[name] = callback
        logger.debug("agent_config_validator.callback_registered name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if found."""
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("agent_config_validator.callback_removed name=%s", name)
            return True
        return False

    def _fire(self, event: str, **kwargs: Any) -> None:
        """Fire all registered callbacks with the given event."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(event, **kwargs)
            except Exception:
                logger.exception("agent_config_validator.callback_error name=%s", cb_name)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding 10 000 limit."""
        max_entries = 10000
        if len(self._state.entries) <= max_entries:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: self._state.entries[k].get("created_at", 0),
        )
        excess = len(self._state.entries) - max_entries
        for key in sorted_keys[:excess]:
            del self._state.entries[key]
        logger.info("agent_config_validator.pruned count=%d", excess)

    # ------------------------------------------------------------------
    # Schema API
    # ------------------------------------------------------------------

    def define_schema(self, agent_id: str, schema: Dict[str, Any]) -> str:
        """Define a validation schema for *agent_id*.

        *schema* maps field names to dicts with keys ``type``, ``required``,
        and optionally ``default``.  Returns the generated schema_id.
        """
        schema_id = self._gen_id(f"{agent_id}{time.time()}")
        entry = {
            "schema_id": schema_id,
            "agent_id": agent_id,
            "schema": schema,
            "created_at": time.time(),
        }
        self._state.entries[agent_id] = entry
        self._total_defines += 1
        self._prune()
        self._fire("schema_defined", agent_id=agent_id, schema_id=schema_id)
        logger.info(
            "agent_config_validator.schema_defined agent_id=%s schema_id=%s",
            agent_id,
            schema_id,
        )
        return schema_id

    def get_schema(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the schema dict for *agent_id*, or ``None``."""
        entry = self._state.entries.get(agent_id)
        if entry is None:
            return None
        return entry["schema"]

    def remove_schema(self, schema_id: str) -> bool:
        """Remove a schema by its schema_id. Returns True if found."""
        for key, entry in list(self._state.entries.items()):
            if entry.get("schema_id") == schema_id:
                del self._state.entries[key]
                self._total_removals += 1
                self._fire("schema_removed", schema_id=schema_id, agent_id=key)
                logger.info("agent_config_validator.schema_removed schema_id=%s", schema_id)
                return True
        return False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, agent_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate *config* against the schema registered for *agent_id*.

        Returns ``{valid: bool, errors: list[str], warnings: list[str]}``.
        """
        self._total_validations += 1
        errors: List[str] = []
        warnings: List[str] = []

        entry = self._state.entries.get(agent_id)
        if entry is None:
            errors.append(f"No schema defined for agent '{agent_id}'")
            return {"valid": False, "errors": errors, "warnings": warnings}

        schema = entry["schema"]

        # Check required fields and types
        for field_name, field_spec in schema.items():
            required = field_spec.get("required", False)
            expected_type = field_spec.get("type", "str")

            if field_name not in config:
                if required:
                    errors.append(f"Missing required field '{field_name}'")
                elif "default" in field_spec:
                    warnings.append(
                        f"Field '{field_name}' not provided, will use default"
                    )
                continue

            value = config[field_name]
            if expected_type in TYPE_MAP:
                if not isinstance(value, TYPE_MAP[expected_type]):
                    errors.append(
                        f"Field '{field_name}' expected type '{expected_type}' "
                        f"but got '{type(value).__name__}'"
                    )

        # Warn about extra fields not in schema
        for key in config:
            if key not in schema:
                warnings.append(f"Unknown field '{key}' not in schema")

        valid = len(errors) == 0
        return {"valid": valid, "errors": errors, "warnings": warnings}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_defaults(self, agent_id: str) -> Dict[str, Any]:
        """Return a dict of default values from the schema for *agent_id*."""
        entry = self._state.entries.get(agent_id)
        if entry is None:
            return {}
        defaults: Dict[str, Any] = {}
        for field_name, field_spec in entry["schema"].items():
            if "default" in field_spec:
                defaults[field_name] = field_spec["default"]
        return defaults

    def get_schema_count(self) -> int:
        """Return the number of stored schemas."""
        return len(self._state.entries)

    def list_agents(self) -> List[str]:
        """Return a sorted list of agent IDs that have schemas defined."""
        return sorted(self._state.entries.keys())

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        return {
            "total_defines": self._total_defines,
            "total_validations": self._total_validations,
            "total_removals": self._total_removals,
            "schema_count": self.get_schema_count(),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        """Clear all schemas, callbacks, and statistics."""
        self._state = AgentConfigValidatorState()
        self._callbacks.clear()
        self._total_defines = 0
        self._total_validations = 0
        self._total_removals = 0
        logger.info("agent_config_validator.reset")
