"""Pipeline step recorder v2 — records pipeline step execution for replay/audit.

Enhanced version with format support, deep-copied metadata,
ISO-format timestamps, and refined callback dispatch.
"""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepRecorderV2State:
    """Internal state for the PipelineStepRecorderV2 service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepRecorderV2:
    """Records pipeline step execution history for replay and audit.

    Captures the context of each pipeline step execution with format
    and metadata support, allowing historical analysis and compliance auditing.
    """

    PREFIX = "psrv2-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepRecorderV2State()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest quarter of entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", ""),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = len(self._state.entries) // 4
        if remove_count < 1:
            remove_count = 1
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # record_v2
    # ------------------------------------------------------------------

    def record_v2(
        self,
        pipeline_id: str,
        step_name: str,
        format: str = "json",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a pipeline step execution. Returns record ID or '' if inputs empty."""
        if not pipeline_id or not step_name:
            return ""
        self._prune()
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "format": format,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._fire("record_v2", pipeline_id=pipeline_id, record_id=record_id)
        return record_id

    # ------------------------------------------------------------------
    # get_recording
    # ------------------------------------------------------------------

    def get_recording(self, record_id: str) -> Optional[dict]:
        """Get a single recording by ID. Returns deep copy or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    # ------------------------------------------------------------------
    # get_recordings
    # ------------------------------------------------------------------

    def get_recordings(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Get recordings sorted descending by creation. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)),
            reverse=True,
        )
        return [copy.deepcopy(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_recording_count
    # ------------------------------------------------------------------

    def get_recording_count(self, pipeline_id: str = "") -> int:
        """Count recordings, optionally filtering by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        entries = list(self._state.entries.values())
        pipelines = {e.get("pipeline_id", "") for e in entries}
        return {
            "total_recordings": len(entries),
            "unique_pipelines": len(pipelines),
        }

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all entries, callbacks, and reset sequence. Set on_change to None."""
        self._state = PipelineStepRecorderV2State()
        self._on_change = None
