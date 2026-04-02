"""Service module for converting pipeline data between formats."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataConverterState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataConverter:
    """Converts pipeline data between formats (dict<->list, flat<->nested, etc)."""

    PREFIX = "pdcv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataConverterState()
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
            quarter = self.MAX_ENTRIES // 4
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            for key in sorted_keys[:quarter]:
                del self._state.entries[key]

    # -- Callbacks -----------------------------------------------------------

    def _fire(self, action: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

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

    # -- Format conversion helpers -------------------------------------------

    def _dict_to_list(self, data: dict) -> list:
        """Convert a dict to a list of {key, value} pairs."""
        return [{"key": k, "value": v} for k, v in data.items()]

    def _list_to_dict(self, data: list) -> dict:
        """Convert a list of {key, value} pairs to a dict."""
        result = {}
        for item in data:
            if isinstance(item, dict) and "key" in item and "value" in item:
                result[item["key"]] = item["value"]
        return result

    def _flatten(self, data: dict, prefix: str = "", sep: str = ".") -> dict:
        """Flatten a nested dict into a single-level dict with dotted keys."""
        result = {}
        for k, v in data.items():
            new_key = f"{prefix}{sep}{k}" if prefix else k
            if isinstance(v, dict):
                result.update(self._flatten(v, new_key, sep))
            else:
                result[new_key] = v
        return result

    def _unflatten(self, data: dict, sep: str = ".") -> dict:
        """Unflatten a dotted-key dict into a nested dict."""
        result: dict = {}
        for compound_key, value in data.items():
            parts = compound_key.split(sep)
            current = result
            for part in parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result

    def _do_convert(self, data: Any, from_format: str, to_format: str) -> Any:
        """Perform the actual format conversion."""
        if from_format == "dict" and to_format == "list":
            if not isinstance(data, dict):
                raise ValueError("Data must be a dict for dict->list conversion")
            return self._dict_to_list(data)
        elif from_format == "list" and to_format == "dict":
            if not isinstance(data, list):
                raise ValueError("Data must be a list for list->dict conversion")
            return self._list_to_dict(data)
        elif from_format == "nested" and to_format == "flat":
            if not isinstance(data, dict):
                raise ValueError("Data must be a dict for nested->flat conversion")
            return self._flatten(data)
        elif from_format == "flat" and to_format == "nested":
            if not isinstance(data, dict):
                raise ValueError("Data must be a dict for flat->nested conversion")
            return self._unflatten(data)
        else:
            raise ValueError(f"Unsupported conversion: {from_format} -> {to_format}")

    # -- Core methods --------------------------------------------------------

    def convert(
        self,
        pipeline_id: str,
        data: Any,
        from_format: str,
        to_format: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Convert data between formats and store the record. Returns record ID."""
        converted = self._do_convert(data, from_format, to_format)
        record_id = self._generate_id(f"{pipeline_id}{from_format}{to_format}")
        seq_val = self._state._seq - 1
        self._state.entries[record_id] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "from_format": from_format,
            "to_format": to_format,
            "input": copy.deepcopy(data),
            "output": converted,
            "metadata": metadata,
            "created_at": time.time(),
            "_seq": seq_val,
        }
        self._prune()
        self._fire("convert", {"record_id": record_id, "pipeline_id": pipeline_id})
        return record_id

    def get_conversion(self, record_id: str) -> Optional[dict]:
        """Get a single conversion record by ID."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_conversions(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """List conversion records, optionally filtered by pipeline_id, newest first."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    def get_conversion_count(self, pipeline_id: str = "") -> int:
        """Return number of conversion records, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return statistics about conversions."""
        formats = {}
        for entry in self._state.entries.values():
            key = f"{entry['from_format']}->{entry['to_format']}"
            formats[key] = formats.get(key, 0) + 1
        return {
            "total_conversions": len(self._state.entries),
            "format_counts": formats,
        }

    def reset(self) -> None:
        """Clear all state, callbacks, and on_change."""
        self._state = PipelineDataConverterState()
        self._callbacks = {}
        self._on_change = None
