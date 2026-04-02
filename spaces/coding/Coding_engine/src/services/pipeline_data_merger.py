"""Pipeline Data Merger – merges data from multiple pipeline sources.

Combines data sets from different pipeline sources using configurable
merge strategies including concatenation, zipping, and set union.
Supports tracking of merge definitions and execution counts.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _State:
    merges: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataMerger:
    """Merges data from multiple pipeline sources."""

    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = _State()

    # ------------------------------------------------------------------
    # Merges
    # ------------------------------------------------------------------

    def create_merge(
        self,
        pipeline_id: str,
        sources: list,
        strategy: str = "concat",
    ) -> str:
        if not pipeline_id:
            return ""
        if strategy not in ("concat", "zip", "union"):
            return ""
        if len(self._state.merges) >= self.MAX_ENTRIES:
            return ""

        self._state._seq += 1
        now = time.time()
        raw = f"{pipeline_id}-{sources}-{now}-{self._state._seq}"
        merge_id = "pdm-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        self._state.merges[merge_id] = {
            "merge_id": merge_id,
            "pipeline_id": pipeline_id,
            "sources": list(sources),
            "strategy": strategy,
            "created_at": now,
            "execution_count": 0,
        }
        self._fire("merge_created", merge_id=merge_id, pipeline_id=pipeline_id)
        logger.info("merge_created", merge_id=merge_id, pipeline_id=pipeline_id)
        return merge_id

    def execute_merge(self, merge_id: str, data_sets: list) -> dict:
        entry = self._state.merges.get(merge_id)
        if not entry:
            return {}

        strategy = entry["strategy"]

        if strategy == "concat":
            merged: Any = []
            for ds in data_sets:
                if isinstance(ds, list):
                    merged.extend(ds)
                else:
                    merged.append(ds)
        elif strategy == "zip":
            lists = [ds if isinstance(ds, list) else [ds] for ds in data_sets]
            merged = list(zip(*lists))
        elif strategy == "union":
            seen: set = set()
            for ds in data_sets:
                items = ds if isinstance(ds, list) else [ds]
                for item in items:
                    seen.add(item)
            merged = list(seen)
        else:
            merged = []

        entry["execution_count"] += 1
        self._fire("merge_executed", merge_id=merge_id, source_count=len(data_sets))
        logger.info("merge_executed", merge_id=merge_id)

        return {
            "merge_id": merge_id,
            "result": merged,
            "source_count": len(data_sets),
        }

    def get_merge(self, merge_id: str) -> Optional[dict]:
        entry = self._state.merges.get(merge_id)
        if not entry:
            return None
        return dict(entry)

    def get_merges(self, pipeline_id: str) -> list:
        results = []
        for entry in self._state.merges.values():
            if entry["pipeline_id"] == pipeline_id:
                results.append(dict(entry))
        return results

    def get_merge_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.merges)
        count = 0
        for entry in self._state.merges.values():
            if entry["pipeline_id"] == pipeline_id:
                count += 1
        return count

    def list_pipelines(self) -> list:
        seen: set = set()
        for entry in self._state.merges.values():
            seen.add(entry["pipeline_id"])
        return sorted(seen)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        total_executions = sum(
            e["execution_count"] for e in self._state.merges.values()
        )
        return {
            "total_merges": len(self._state.merges),
            "total_executions": total_executions,
            "pipeline_count": len(self.list_pipelines()),
        }

    def reset(self) -> None:
        self._state.merges.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
