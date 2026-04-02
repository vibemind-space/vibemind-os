"""Pipeline step rollforwarder — rolls forward pipeline steps to a target version.

Manages rollforward operations for pipeline steps, enabling controlled
advancement to newer versions with full audit trail.
"""

from __future__ import annotations

import copy
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepRollforwarderState:
    """Internal state for the PipelineStepRollforwarder service."""

    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepRollforwarder:
    """Rolls forward pipeline steps to a target version.

    Manages controlled advancement of pipeline steps to newer versions,
    tracking each rollforward operation for audit and analysis.
    """

    PREFIX = "psrf-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepRollforwarderState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

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
        """Invoke all registered callbacks; exceptions are logged, not raised."""
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
                logger.exception("Callback error")

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        if remove_count < 1:
            remove_count = 1
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # rollforward
    # ------------------------------------------------------------------

    def rollforward(
        self,
        pipeline_id: str,
        step_name: str,
        target_version: str = "latest",
        metadata: Optional[dict] = None,
    ) -> str:
        """Roll forward a pipeline step to target_version. Returns record_id or '' on bad input."""
        if not pipeline_id or not step_name:
            return ""
        record_id = self._generate_id()
        now = time.time()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "target_version": target_version,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("rollforward", record_id=record_id, pipeline_id=pipeline_id)
        return record_id

    # ------------------------------------------------------------------
    # get_rollforward
    # ------------------------------------------------------------------

    def get_rollforward(self, record_id: str) -> Optional[dict]:
        """Get a single rollforward record by ID. Returns None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # get_rollforwards
    # ------------------------------------------------------------------

    def get_rollforwards(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Get rollforward records, newest first. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_rollforward_count
    # ------------------------------------------------------------------

    def get_rollforward_count(self, pipeline_id: str = "") -> int:
        """Count rollforward records, optionally filtering by pipeline_id."""
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
        total = len(entries)
        pipelines = set(e.get("pipeline_id", "") for e in entries)
        return {
            "total_rollforwards": total,
            "unique_pipelines": len(pipelines),
        }

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all entries, callbacks, and reset sequence."""
        self._state = PipelineStepRollforwarderState()
        self._on_change = None
