"""Pipeline step retirer -- retires pipeline steps.

Stores retirement records that associate pipeline steps with a reason
and optional metadata.  Each record captures the pipeline, step name,
reason, and metadata.  Supports filtering by pipeline, newest-first
ordering, and automatic pruning when the entry limit is reached.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

@dataclass
class PipelineStepRetirerState:
    """Internal mutable state for the retirer service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class PipelineStepRetirer:
    """Retires pipeline steps.

    Each retirement record ties a pipeline step to a reason string
    and optional metadata.  Records are stored in memory and can
    be queried by pipeline ID.
    """

    PREFIX = "psrt-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepRetirerState()
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
        """Evict the oldest entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._state.entries,
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k]["_seq"],
            ),
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        for rid in sorted_ids[:remove_count]:
            del self._state.entries[rid]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        if self._on_change is not None:
            try:
                self._on_change(action, detail)
            except Exception:
                logger.exception("on_change callback error for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback error for action=%s", action)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Main: retire
    # ------------------------------------------------------------------

    def retire(
        self,
        pipeline_id: str,
        step_name: str,
        reason: str = "",
        metadata: Any = None,
    ) -> str:
        """Retire a pipeline step. Returns the record ID.

        Returns an empty string if *pipeline_id* or *step_name* is empty.
        """
        if not pipeline_id or not step_name:
            return ""

        self._prune()
        record_id = self._generate_id()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "reason": reason,
            "metadata": copy.deepcopy(metadata),
            "created_at": time.time(),
            "_seq": self._state._seq,
        }

        self._state.entries[record_id] = entry
        self._fire("retired", dict(entry))
        return record_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_retirement(self, record_id: str) -> Optional[dict]:
        """Return a copy of a single retirement record, or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_retirements(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return retirement records, newest first.

        If *pipeline_id* is provided, only records for that pipeline are
        returned.  Results are sorted by (created_at, _seq) descending
        and limited to *limit* entries.
        """
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_retirement_count(self, pipeline_id: str = "") -> int:
        """Return the number of retirement records.

        If *pipeline_id* is provided, only count records for that pipeline.
        """
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        unique_pipelines = len(
            {e["pipeline_id"] for e in self._state.entries.values()}
        )
        return {
            "total_retirements": len(self._state.entries),
            "unique_pipelines": unique_pipelines,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state and callbacks."""
        self._state = PipelineStepRetirerState()
        self._on_change = None
