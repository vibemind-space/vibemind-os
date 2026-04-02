"""Service module for replicating pipeline data entries to multiple targets."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataReplicatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataReplicator:
    """Replicates pipeline data entries to multiple targets."""

    PREFIX = "pdrp-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataReplicatorState()

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{digest}"

    # -- Callbacks -----------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        if cb is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: Any) -> None:
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_order", 0),
                ),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    # -- Core methods --------------------------------------------------------

    def replicate(
        self,
        pipeline_id: str,
        data_key: str,
        targets: List[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Replicate a pipeline data entry to the given targets and return the record ID."""
        record_id = self._generate_id()
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "targets": list(targets) if targets else [],
            "metadata": dict(metadata) if metadata else {},
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("replicate", record)
        return record_id

    def get_replication(self, record_id: str) -> Optional[dict]:
        """Return the replication record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_replications(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return replication records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_order", 0)), reverse=True
        )
        return [dict(r) for r in results[:limit]]

    def get_replication_count(self, pipeline_id: str = "") -> int:
        """Return the number of replications, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics about stored replications."""
        pipelines = {e.get("pipeline_id", "") for e in self._state.entries.values()}
        return {
            "total_replications": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        """Clear all replication records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
