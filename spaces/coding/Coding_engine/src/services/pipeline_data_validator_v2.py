"""Pipeline data validator v2.

Validates data flowing through pipelines and tracks validation records.
"""

from __future__ import annotations

import copy
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

PREFIX = "pdvv-"
MAX_ENTRIES = 10000


@dataclass
class PipelineDataValidatorV2State:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineDataValidatorV2:
    """Validates pipeline data and tracks validation records."""

    def __init__(self) -> None:
        self._state = PipelineDataValidatorV2State()
        self._callbacks: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self) -> None:
        while len(self._state.entries) > MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]

    # ------------------------------------------------------------------
    # Callback machinery
    # ------------------------------------------------------------------

    def on_change(self, callback: Callable) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self._callbacks:
            del self._callbacks[cb_id]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        self._on_change(action, data)

    def _on_change(self, action: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def validate_v2(
        self,
        pipeline_id: str,
        data_key: str,
        rules: str = "default",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a validation record. Returns '' if pipeline_id or data_key empty."""
        if not pipeline_id or not data_key:
            return ""

        record_id = self._generate_id(f"val-{pipeline_id}-{data_key}-{time.time()}")
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "rules": rules,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("validation_created", record_id=record_id, pipeline_id=pipeline_id)
        logger.info("Created validation %s for pipeline %s", record_id, pipeline_id)
        return record_id

    def get_validation(self, record_id: str) -> Optional[dict]:
        """Return a single validation record or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_validations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return validations, optionally filtered by pipeline_id.

        Results are sorted by (created_at, _seq) in descending order.
        """
        items = list(self._state.entries.values())
        if pipeline_id:
            items = [e for e in items if e.get("pipeline_id") == pipeline_id]
        items.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return [dict(e) for e in items[:limit]]

    def get_validation_count(self, pipeline_id: str = "") -> int:
        """Return the number of validation records, optionally filtered."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_pipelines = set()
        for e in self._state.entries.values():
            pid = e.get("pipeline_id")
            if pid:
                unique_pipelines.add(pid)
        return {
            "total_validations": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Clear all state and callbacks."""
        self._state = PipelineDataValidatorV2State()
        self._callbacks.clear()
        logger.info("PipelineDataValidatorV2 reset")
