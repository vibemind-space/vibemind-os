"""Service module for coercing/converting pipeline data field types."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataCoercerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataCoercer:
    """Coerces/converts pipeline data field types (string to int, int to float, etc)."""

    PREFIX = "pdco-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataCoercerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{digest}"

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    # -- Callbacks -----------------------------------------------------------

    def _fire(self, event: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.error("on_change callback error for event %s", event)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.error("callback %s error for event %s", name, event)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def register_coercion(self, name: str, field: str, target_type: str, default_value: Any = None) -> str:
        """Register a coercion rule. target_type: 'int', 'float', 'str', 'bool'. Returns coercion_id."""
        if target_type not in ("int", "float", "str", "bool"):
            raise ValueError(f"Unsupported target_type: {target_type}")
        coercion_id = self._generate_id(name)
        self._state.entries[coercion_id] = {
            "coercion_id": coercion_id,
            "name": name,
            "field": field,
            "target_type": target_type,
            "default_value": default_value,
            "created_at": time.time(),
            "usage_count": 0,
        }
        self._prune()
        self._fire("register", {"coercion_id": coercion_id, "name": name})
        return coercion_id

    def _convert_value(self, value: Any, target_type: str, default_value: Any) -> Any:
        """Convert a value to the target type, falling back to default_value on failure."""
        try:
            if target_type == "int":
                return int(value)
            elif target_type == "float":
                return float(value)
            elif target_type == "str":
                return str(value)
            elif target_type == "bool":
                if isinstance(value, str):
                    if value.lower() in ("true", "1", "yes"):
                        return True
                    elif value.lower() in ("false", "0", "no", ""):
                        return False
                    return default_value
                return bool(value)
        except (ValueError, TypeError):
            return default_value

    def coerce(self, coercion_id: str, record: dict) -> dict:
        """Apply coercion to a record. Returns a new dict with the field converted."""
        entry = self._state.entries.get(coercion_id)
        if entry is None:
            return dict(record)
        result = dict(record)
        field_name = entry["field"]
        if field_name in result:
            result[field_name] = self._convert_value(
                result[field_name], entry["target_type"], entry["default_value"]
            )
        entry["usage_count"] += 1
        return result

    def coerce_batch(self, coercion_id: str, records: list) -> list:
        """Apply coercion to a list of records."""
        return [self.coerce(coercion_id, r) for r in records]

    def coerce_all(self, record: dict, coercion_ids: list) -> dict:
        """Apply multiple coercions to one record sequentially."""
        result = dict(record)
        for cid in coercion_ids:
            result = self.coerce(cid, result)
        return result

    def get_coercion(self, coercion_id: str) -> dict:
        """Return coercion rule info."""
        entry = self._state.entries.get(coercion_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_coercions(self) -> list:
        """List all registered coercion rules."""
        return [dict(e) for e in self._state.entries.values()]

    def get_coercion_count(self) -> int:
        """Return number of registered coercion rules."""
        return len(self._state.entries)

    def remove_coercion(self, coercion_id: str) -> bool:
        """Remove a coercion rule."""
        if coercion_id in self._state.entries:
            del self._state.entries[coercion_id]
            self._fire("remove", {"coercion_id": coercion_id})
            return True
        return False

    def get_stats(self) -> dict:
        """Return statistics."""
        total_operations = sum(e.get("usage_count", 0) for e in self._state.entries.values())
        return {
            "total_coercions": len(self._state.entries),
            "total_operations": total_operations,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataCoercerState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
