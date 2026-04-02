"""Sliding/tumbling window operations on pipeline data streams."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclass
class PipelineDataWindowState:
    entries: dict
    _seq: int = 0


class PipelineDataWindow:
    """Manages sliding and tumbling windows over pipeline data streams."""

    def __init__(self):
        self._state = PipelineDataWindowState(entries={})
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        self._state._seq += 1
        return f"pdw-{h}"

    def on_change(self, name: str, cb):
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail_dict: dict):
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail_dict)
            except Exception as e:
                logger.error("Callback %s failed: %s", name, e)

    def _prune(self):
        while len(self._state.entries) > MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]
            logger.debug("Pruned entry %s to stay within max entries", oldest_key)

    def create_window(self, pipeline_id: str, window_type: str = "sliding", size: int = 10, slide: int = 1) -> str:
        """Create a window for a pipeline.

        Args:
            pipeline_id: The pipeline identifier.
            window_type: "sliding" or "tumbling".
            size: Window size (number of records).
            slide: Slide amount for sliding windows.

        Returns:
            The window ID.
        """
        window_id = self._generate_id(f"{pipeline_id}:{window_type}:{size}:{slide}")
        self._state.entries[window_id] = {
            "window_id": window_id,
            "pipeline_id": pipeline_id,
            "window_type": window_type,
            "size": size,
            "slide": slide,
            "records": [],
            "created_at": time.time(),
        }
        self._prune()
        self._fire("create_window", {"window_id": window_id, "pipeline_id": pipeline_id})
        logger.info("Created %s window %s for pipeline %s (size=%d, slide=%d)",
                     window_type, window_id, pipeline_id, size, slide)
        return window_id

    def add_record(self, window_id: str, record) -> list:
        """Add a record to a window. Returns completed windows (lists of records) if any fill up.

        For tumbling windows: when records reach size, the full window is returned and records reset.
        For sliding windows: when records reach size, a window of 'size' records is returned and
        the oldest 'slide' records are removed.
        """
        entry = self._state.entries.get(window_id)
        if entry is None:
            logger.warning("Window %s not found", window_id)
            return []

        entry["records"].append(record)
        completed = []

        if entry["window_type"] == "tumbling":
            if len(entry["records"]) >= entry["size"]:
                completed.append(list(entry["records"]))
                entry["records"] = []
        elif entry["window_type"] == "sliding":
            while len(entry["records"]) >= entry["size"]:
                completed.append(list(entry["records"][:entry["size"]]))
                entry["records"] = entry["records"][entry["slide"]:]

        if completed:
            self._fire("window_completed", {"window_id": window_id, "count": len(completed)})

        return completed

    def get_current(self, window_id: str) -> list:
        """Get the current records in a window."""
        entry = self._state.entries.get(window_id)
        if entry is None:
            return []
        return list(entry["records"])

    def get_window(self, window_id: str) -> dict | None:
        """Get full window info dict, or None if not found."""
        return self._state.entries.get(window_id)

    def get_windows(self, pipeline_id: str) -> list:
        """Get all windows for a pipeline."""
        return [
            entry for entry in self._state.entries.values()
            if entry["pipeline_id"] == pipeline_id
        ]

    def get_window_count(self, pipeline_id: str = "") -> int:
        """Get count of windows, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for entry in self._state.entries.values()
            if entry["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> list:
        """List distinct pipeline IDs."""
        seen = set()
        result = []
        for entry in self._state.entries.values():
            pid = entry["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    def get_stats(self) -> dict:
        """Return stats about the current state."""
        return {
            "total_windows": len(self._state.entries),
            "total_pipelines": len(self.list_pipelines()),
            "seq": self._state._seq,
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        """Reset all state."""
        self._state = PipelineDataWindowState(entries={})
        self._callbacks = {}
        logger.info("PipelineDataWindow reset")
