"""Service module for serializing pipeline data into different formats."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataSerializerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataSerializer:
    """Serialize pipeline data into various formats (json, msgpack, csv, etc)."""

    PREFIX = "pdsr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataSerializerState()
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
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = len(sorted_keys) // 4
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

    # -- Serialization helpers -----------------------------------------------

    def _serialize_data(self, data: Any, fmt: str) -> bytes:
        """Serialize data into the specified format, returning raw bytes."""
        if fmt == "json":
            return json.dumps(data, default=str).encode("utf-8")
        elif fmt == "csv":
            buf = io.StringIO()
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                writer = csv.DictWriter(buf, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            elif isinstance(data, dict):
                writer = csv.DictWriter(buf, fieldnames=data.keys())
                writer.writeheader()
                writer.writerow(data)
            else:
                writer = csv.writer(buf)
                writer.writerow([str(data)])
            return buf.getvalue().encode("utf-8")
        elif fmt == "msgpack":
            # Lightweight msgpack-like serialization using json as fallback
            return json.dumps(data, default=str).encode("utf-8")
        elif fmt == "text":
            return str(data).encode("utf-8")
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    # -- Core methods --------------------------------------------------------

    def serialize(
        self,
        pipeline_id: str,
        data: Any,
        format: str = "json",
        metadata: Optional[dict] = None,
    ) -> str:
        """Serialize pipeline data into the given format. Returns the record ID."""
        serialized = self._serialize_data(data, format)
        record_id = self._generate_id(f"{pipeline_id}{format}{time.time()}")
        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "format": format,
            "data": copy.deepcopy(data),
            "serialized": serialized,
            "size_bytes": len(serialized),
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq - 1,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("serialize", {"record_id": record_id, "pipeline_id": pipeline_id, "format": format})
        return record_id

    def get_record(self, record_id: str) -> Optional[dict]:
        """Return a single record by ID, or None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_records(
        self, pipeline_id: str = "", format: str = "", limit: int = 50
    ) -> List[dict]:
        """Return records filtered by pipeline_id and/or format, sorted newest first."""
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry.get("pipeline_id") != pipeline_id:
                continue
            if format and entry.get("format") != format:
                continue
            results.append(entry)
        results.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in results[:limit]]

    def get_record_count(self, pipeline_id: str = "") -> int:
        """Return the count of records, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return statistics about serialization records."""
        total_size = sum(e.get("size_bytes", 0) for e in self._state.entries.values())
        formats: Dict[str, int] = {}
        pipelines: Dict[str, int] = {}
        for e in self._state.entries.values():
            fmt = e.get("format", "unknown")
            formats[fmt] = formats.get(fmt, 0) + 1
            pid = e.get("pipeline_id", "unknown")
            pipelines[pid] = pipelines.get(pid, 0) + 1
        return {
            "total_records": len(self._state.entries),
            "total_size_bytes": total_size,
            "formats": formats,
            "pipelines": pipelines,
        }

    def reset(self) -> None:
        """Clear all state, callbacks, and on_change handler."""
        self._state = PipelineDataSerializerState()
        self._callbacks = {}
        self._on_change = None
