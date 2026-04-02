"""Service module for formatting pipeline data fields using configurable format strings and patterns."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataFormatterState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataFormatter:
    """Formats pipeline data fields using configurable format strings and patterns."""

    PREFIX = "pdfo-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataFormatterState()
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

    def register_format(self, name: str, field: str, template_str: str) -> str:
        """Register a format rule. template_str uses {value} as placeholder. Returns format_id."""
        format_id = self._generate_id(name)
        self._state.entries[format_id] = {
            "format_id": format_id,
            "name": name,
            "field": field,
            "template_str": template_str,
            "created_at": time.time(),
            "usage_count": 0,
        }
        self._prune()
        self._fire("register", {"format_id": format_id, "name": name})
        return format_id

    def format_record(self, format_id: str, record: dict) -> dict:
        """Apply format to a record. Replace field value with formatted string. Returns new dict."""
        entry = self._state.entries.get(format_id)
        if entry is None:
            return dict(record)
        result = dict(record)
        target_field = entry["field"]
        if target_field in result:
            original = result[target_field]
            result[target_field] = entry["template_str"].format(value=original)
        entry["usage_count"] += 1
        return result

    def format_batch(self, format_id: str, records: list) -> list:
        """Apply format to a list of records."""
        return [self.format_record(format_id, r) for r in records]

    def format_all(self, record: dict, format_ids: list) -> dict:
        """Apply multiple formats sequentially to a single record."""
        result = dict(record)
        for fid in format_ids:
            result = self.format_record(fid, result)
        return result

    def get_format(self, format_id: str) -> dict:
        """Return format rule info."""
        entry = self._state.entries.get(format_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_formats(self) -> list:
        """List all registered format rules."""
        return [dict(e) for e in self._state.entries.values()]

    def get_format_count(self) -> int:
        """Return number of registered format rules."""
        return len(self._state.entries)

    def remove_format(self, format_id: str) -> bool:
        """Remove a format rule."""
        if format_id in self._state.entries:
            del self._state.entries[format_id]
            self._fire("remove", {"format_id": format_id})
            return True
        return False

    def get_stats(self) -> dict:
        """Return statistics."""
        total_operations = sum(e.get("usage_count", 0) for e in self._state.entries.values())
        return {
            "total_formats": len(self._state.entries),
            "total_operations": total_operations,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataFormatterState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
