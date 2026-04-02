"""Pipeline step namer — names and renames pipeline steps.

Assigns and manages names for individual pipeline steps, enabling
clear identification and renaming of steps within pipeline workflows.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepNamerState:
    """Internal state for the PipelineStepNamer service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepNamer:
    """Names and renames pipeline steps.

    Records naming assignments on pipeline steps, allowing steps to be
    identified, searched, and renamed within pipeline workflows.
    """

    PREFIX = "psnm-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepNamerState()

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
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        if callback is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

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
    # name_step
    # ------------------------------------------------------------------

    def name_step(
        self,
        pipeline_id: str,
        step_name: str,
        new_name: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Name or rename a pipeline step. Returns record ID.

        Args:
            pipeline_id: Non-empty pipeline identifier.
            step_name: Non-empty original step name.
            new_name: Optional new name for the step.
            metadata: Optional metadata dict (deep-copied).

        Raises:
            ValueError: If pipeline_id or step_name is empty.
        """
        if not pipeline_id or not step_name:
            return ""

        self._prune()
        record_id = self._generate_id()
        now = time.time()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "new_name": new_name,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._fire("named", dict(entry))
        return record_id

    # ------------------------------------------------------------------
    # get_naming
    # ------------------------------------------------------------------

    def get_naming(self, record_id: str) -> Optional[dict]:
        """Get a single naming record by ID. Returns None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # get_namings
    # ------------------------------------------------------------------

    def get_namings(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Get naming records, newest first. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_naming_count
    # ------------------------------------------------------------------

    def get_naming_count(self, pipeline_id: str = "") -> int:
        """Count naming records, optionally filtering by pipeline_id."""
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
            "total_namings": total,
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
