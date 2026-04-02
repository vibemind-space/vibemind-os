"""Pipeline step swapper - swaps pipeline steps.

Manages swapping of steps within pipelines, tracking which steps were
swapped and maintaining a history of all swap operations.
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
class PipelineStepSwapperState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepSwapper:
    """Swaps pipeline steps and tracks swap history."""

    PREFIX = "pssw-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepSwapperState()
        self._on_change: Optional[Callable] = None
        logger.info("PipelineStepSwapper initialized")

    def _generate_id(self, data: str) -> str:
        self._state._seq += 1
        raw = f"{data}{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            remove_count = len(self._state.entries) // 4
            for i in range(remove_count):
                del self._state.entries[sorted_keys[i]]

    def _fire(self, action: str, data: dict):
        if self._on_change:
            try:
                self._on_change(action, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, callback):
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Swap
    # ------------------------------------------------------------------

    def swap(
        self,
        pipeline_id: str,
        step_a: str,
        step_b: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Swap two steps within a pipeline.

        Returns a record_id (pssw-xxx) or empty string on invalid input.
        """
        if not pipeline_id or not step_a or not step_b:
            return ""

        self._prune()
        record_id = self._generate_id(f"{pipeline_id}{step_a}{step_b}")
        now = time.time()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_a": step_a,
            "step_b": step_b,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("swapped", {"record_id": record_id, "pipeline_id": pipeline_id})
        return record_id

    # ------------------------------------------------------------------
    # Get swap
    # ------------------------------------------------------------------

    def get_swap(self, record_id: str) -> Optional[dict]:
        """Get a swap record by ID. Returns dict copy or None."""
        entry = self._state.entries.get(record_id)
        if not entry:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get swaps
    # ------------------------------------------------------------------

    def get_swaps(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return swap records, newest first by (created_at, _seq).

        Optionally filter by pipeline_id. Limited to `limit` results.
        """
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # Get swap count
    # ------------------------------------------------------------------

    def get_swap_count(self, pipeline_id: str = "") -> int:
        """Return count of swap records, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        unique_pipelines = set(
            e.get("pipeline_id") for e in self._state.entries.values()
        )
        return {
            "total_swaps": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self):
        """Clear all stored swaps, callbacks, and reset sequence counter."""
        self._state = PipelineStepSwapperState()
        self._on_change = None
