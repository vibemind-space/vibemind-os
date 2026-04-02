"""Pipeline step disabler — disables pipeline steps.

Tracks which pipeline steps have been disabled, along with the reason and
optional metadata, enabling audit trails and disablement analytics.
"""

from __future__ import annotations

import copy, hashlib, logging, time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepDisablerState:
    """Internal state for the PipelineStepDisabler service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepDisabler:
    """Disables pipeline steps.

    Captures the pipeline ID, step name, reason, and optional metadata
    for every disabled step, supporting queries and statistics.
    """

    PREFIX = "psdi-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepDisablerState()
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

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke on_change and all registered callbacks; exceptions are logged, not raised."""
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback failed for action=%s", action)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("Callback %s failed for action=%s", name, action)

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
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = len(self._state.entries) // 4
        if remove_count < 1:
            remove_count = 1
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # disable
    # ------------------------------------------------------------------

    def disable(
        self,
        pipeline_id: str,
        step_name: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Disable a pipeline step. Returns record ID or '' on failure."""
        try:
            if not pipeline_id or not step_name:
                return ""
            self._prune()
            record_id = self._generate_id()
            now = time.time()
            entry = {
                "record_id": record_id,
                "pipeline_id": pipeline_id,
                "step_name": step_name,
                "reason": reason,
                "metadata": copy.deepcopy(metadata) if metadata else {},
                "created_at": now,
                "_seq": self._state._seq,
            }
            self._state.entries[record_id] = entry
            self._fire("disabled", dict(entry))
            return record_id
        except Exception:
            logger.exception("Failed to disable step")
            return ""

    # ------------------------------------------------------------------
    # get_disablement
    # ------------------------------------------------------------------

    def get_disablement(self, record_id: str) -> Optional[dict]:
        """Get a single disablement record by ID. Returns None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    # ------------------------------------------------------------------
    # get_disablements
    # ------------------------------------------------------------------

    def get_disablements(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Get disablement records, newest first. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_disablement_count
    # ------------------------------------------------------------------

    def get_disablement_count(self, pipeline_id: str = "") -> int:
        """Count disablement records, optionally filtering by pipeline_id."""
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
            "total_disablements": total,
            "unique_pipelines": len(pipelines),
        }

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all entries, callbacks, and reset sequence."""
        self._state.entries.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
        self._on_change = None
