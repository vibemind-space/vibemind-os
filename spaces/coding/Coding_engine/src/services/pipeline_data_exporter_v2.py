"""Service module for exporting pipeline data (v2)."""

from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataExporterV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataExporterV2:
    """Exports pipeline data to named destinations (v2)."""

    PREFIX = "pdxv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataExporterV2State()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", ""),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = len(sorted_keys) // 4
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]

    # -- Callbacks -----------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail) -> None:
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

    # -- Core methods --------------------------------------------------------

    def export_v2(
        self,
        pipeline_id: str,
        data_key: str,
        format: str = "csv",
        metadata: Optional[dict] = None,
    ) -> str:
        """Export pipeline data and return the export record ID."""
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        entry: dict = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "format": format,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("export_v2", pipeline_id=pipeline_id, record_id=record_id)
        return record_id

    def get_export(self, record_id: str) -> Optional[dict]:
        """Return the export record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return deepcopy(entry)

    def get_exports(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Return export records, newest first, optionally filtered."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", ""), r.get("_seq", 0)), reverse=True
        )
        return [deepcopy(r) for r in results[:limit]]

    def get_export_count(self, pipeline_id: str = "") -> int:
        """Return the number of export records, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics about stored exports."""
        pipeline_ids = {
            e.get("pipeline_id", "") for e in self._state.entries.values()
        }
        return {
            "total_exports": len(self._state.entries),
            "unique_pipelines": len(pipeline_ids),
        }

    def reset(self) -> None:
        """Clear all state and on_change."""
        self._state = PipelineDataExporterV2State()
        self._on_change = None
