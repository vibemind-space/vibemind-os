"""Pipeline data zipper - zips/merges multiple data streams together by key or index position."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class PipelineDataZipperState:
    """Internal state for PipelineDataZipper."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    zip_count: int = 0


class PipelineDataZipper:
    """Zips/merges multiple data streams together by key or index position.

    Supports inner, outer, and positional zip modes.
    """

    PREFIX = "pdz-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataZipperState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID from data string using SHA256."""
        raw = hashlib.sha256(f"{data}{self._state._seq}".encode()).hexdigest()
        self._state._seq += 1
        return self.PREFIX + raw[:16]

    def _prune(self) -> None:
        """If entries exceed MAX_ENTRIES, remove oldest by created_at."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: self._state.entries[k].get("created_at", 0),
        )
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, event: str, data: Any) -> None:
        """Fire event to on_change handler and all registered callbacks."""
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                pass
        for _name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                pass

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the on_change handler."""
        return self._on_change

    @on_change.setter
    def on_change(self, handler: Optional[Callable]) -> None:
        """Set the on_change handler."""
        self._on_change = handler

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def register_stream(self, stream_name: str, keys: Optional[List[str]] = None) -> str:
        """Register a data stream to be zipped.

        Args:
            stream_name: Name of the data stream.
            keys: List of key fields for key-based zipping.

        Returns:
            The stream ID (prefixed with 'pdz-').
        """
        stream_id = self._generate_id(stream_name)
        now = time.time()
        self._state.entries[stream_id] = {
            "stream_id": stream_id,
            "stream_name": stream_name,
            "keys": keys or [],
            "records": [],
            "created_at": now,
        }
        self._prune()
        self._fire("stream_registered", {"stream_id": stream_id, "stream_name": stream_name})
        return stream_id

    def add_records(self, stream_id: str, records: List[Dict[str, Any]]) -> None:
        """Add records to a registered stream.

        Args:
            stream_id: The stream to add records to.
            records: List of record dicts to add.
        """
        if stream_id not in self._state.entries:
            return
        self._state.entries[stream_id]["records"].extend(records)
        self._fire("records_added", {"stream_id": stream_id, "count": len(records)})

    def zip_streams(self, stream_ids: List[str], mode: str = "inner") -> Dict[str, Any]:
        """Zip multiple streams together.

        Args:
            stream_ids: List of stream IDs to zip.
            mode: 'inner' (only matching keys), 'outer' (all keys), or 'positional' (by index).

        Returns:
            Dict with zip_id, records, mode, and stream_count.
        """
        if mode not in ("inner", "outer", "positional"):
            return {"zip_id": "", "records": [], "mode": mode, "stream_count": 0}

        valid_ids = [sid for sid in stream_ids if sid in self._state.entries]
        if not valid_ids:
            return {"zip_id": "", "records": [], "mode": mode, "stream_count": 0}

        streams = [self._state.entries[sid] for sid in valid_ids]

        if mode == "positional":
            records = self._zip_positional(streams)
        elif mode == "inner":
            records = self._zip_by_key(streams, inner=True)
        else:  # outer
            records = self._zip_by_key(streams, inner=False)

        zip_id = self._generate_id("zip")
        self._state.zip_count += 1

        result = {
            "zip_id": zip_id,
            "records": records,
            "mode": mode,
            "stream_count": len(valid_ids),
        }
        self._fire("streams_zipped", result)
        return result

    def _zip_positional(self, streams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Zip streams by index position."""
        max_len = max((len(s["records"]) for s in streams), default=0)
        records = []
        for i in range(max_len):
            merged: Dict[str, Any] = {}
            for s in streams:
                if i < len(s["records"]):
                    merged.update(s["records"][i])
            records.append(merged)
        return records

    def _zip_by_key(self, streams: List[Dict[str, Any]], inner: bool = True) -> List[Dict[str, Any]]:
        """Zip streams by key fields."""
        if not streams:
            return []

        # Collect all key fields across streams
        all_key_fields: List[str] = []
        for s in streams:
            for k in s.get("keys", []):
                if k not in all_key_fields:
                    all_key_fields.append(k)

        if not all_key_fields:
            # No keys defined, fall back to positional
            return self._zip_positional(streams)

        # Build index: composite key -> list of records per stream
        def make_key(record: Dict[str, Any]) -> tuple:
            return tuple(record.get(k, None) for k in all_key_fields)

        # Index each stream's records by composite key
        stream_indices: List[Dict[tuple, List[Dict[str, Any]]]] = []
        all_keys: List[tuple] = []
        for s in streams:
            idx: Dict[tuple, List[Dict[str, Any]]] = {}
            for rec in s["records"]:
                ck = make_key(rec)
                idx.setdefault(ck, []).append(rec)
                if ck not in all_keys:
                    all_keys.append(ck)
            stream_indices.append(idx)

        records: List[Dict[str, Any]] = []
        for ck in all_keys:
            if inner:
                # All streams must have this key
                if all(ck in si for si in stream_indices):
                    merged: Dict[str, Any] = {}
                    for si in stream_indices:
                        for rec in si[ck]:
                            merged.update(rec)
                    records.append(merged)
            else:
                # Outer: include even if some streams don't have the key
                merged = {}
                for si in stream_indices:
                    if ck in si:
                        for rec in si[ck]:
                            merged.update(rec)
                records.append(merged)

        return records

    def get_stream(self, stream_id: str) -> Dict[str, Any]:
        """Return stream info (without full records).

        Args:
            stream_id: The stream ID to look up.

        Returns:
            Dict with stream_name, keys, record_count, created_at.
        """
        if stream_id not in self._state.entries:
            return {}
        entry = self._state.entries[stream_id]
        return {
            "stream_id": stream_id,
            "stream_name": entry["stream_name"],
            "keys": entry["keys"],
            "record_count": len(entry["records"]),
            "created_at": entry["created_at"],
        }

    def get_streams(self) -> List[Dict[str, Any]]:
        """List all registered streams."""
        return [self.get_stream(sid) for sid in self._state.entries]

    def get_zip_count(self) -> int:
        """Return total number of zip operations performed."""
        return self._state.zip_count

    def remove_stream(self, stream_id: str) -> bool:
        """Remove a stream by ID.

        Returns:
            True if removed, False if not found.
        """
        if stream_id not in self._state.entries:
            return False
        del self._state.entries[stream_id]
        self._fire("stream_removed", {"stream_id": stream_id})
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the zipper.

        Returns:
            Dict with total_streams, total_zips, total_records.
        """
        total_records = sum(
            len(entry["records"]) for entry in self._state.entries.values()
        )
        return {
            "total_streams": len(self._state.entries),
            "total_zips": self._state.zip_count,
            "total_records": total_records,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataZipperState()
        self._callbacks.clear()
        self._on_change = None
        self._fire("reset", {})
