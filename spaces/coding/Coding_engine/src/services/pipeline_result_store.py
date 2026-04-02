"""Pipeline Result Store -- stores pipeline execution results.

Provides an in-memory store for pipeline step execution results with
SHA256-based IDs, per-pipeline and per-step querying, ordering by
(created_at, seq) for latest-result lookups, and change-notification
callbacks.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineResult:
    """A single pipeline step execution result."""
    result_id: str
    pipeline_id: str
    step_name: str
    result_data: Dict[str, Any]
    status: str
    created_at: float
    seq: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineResultStore:
    """Stores pipeline execution results in memory."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._results: Dict[str, PipelineResult] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_stored = 0
        self._total_retrieved = 0
        self._total_pruned = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"prs-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"prs-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def store_result(
        self,
        pipeline_id: str,
        step_name: str,
        result_data: Dict[str, Any],
        status: str = "success",
    ) -> str:
        """Store a pipeline execution result. Returns result_id."""
        result_id = self._gen_id(f"{pipeline_id}:{step_name}")

        entry = PipelineResult(
            result_id=result_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
            result_data=result_data,
            status=status,
            created_at=time.time(),
            seq=self._seq,
        )
        self._results[result_id] = entry
        self._total_stored += 1

        logger.info(
            "result_stored",
            result_id=result_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
            status=status,
        )

        self._fire("result_stored", {
            "result_id": result_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "status": status,
        })

        self._prune_if_needed()
        return result_id

    def get_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        """Get a single result by ID. Returns dict or None."""
        entry = self._results.get(result_id)
        if entry is None:
            return None
        self._total_retrieved += 1
        return self._to_dict(entry)

    def get_results(
        self,
        pipeline_id: str,
        step_name: str = "",
    ) -> List[Dict[str, Any]]:
        """Get results for a pipeline, optionally filtered by step name."""
        matches = [
            r for r in self._results.values()
            if r.pipeline_id == pipeline_id
            and (not step_name or r.step_name == step_name)
        ]
        matches.sort(key=lambda r: (r.created_at, r.seq))
        self._total_retrieved += len(matches)
        return [self._to_dict(r) for r in matches]

    def get_latest_result(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent result for a pipeline using (created_at, seq) ordering."""
        candidates = [
            r for r in self._results.values()
            if r.pipeline_id == pipeline_id
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda r: (r.created_at, r.seq))
        self._total_retrieved += 1
        return self._to_dict(latest)

    def get_result_count(self) -> int:
        """Return total number of stored results."""
        return len(self._results)

    def list_pipelines(self) -> List[str]:
        """Return sorted list of unique pipeline IDs."""
        return sorted({r.pipeline_id for r in self._results.values()})

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_stored": self._total_stored,
            "total_retrieved": self._total_retrieved,
            "total_pruned": self._total_pruned,
            "current_entries": len(self._results),
            "max_entries": self._max_entries,
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._results.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_stored = 0
        self._total_retrieved = 0
        self._total_pruned = 0
        logger.info("pipeline_result_store_reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(entry: PipelineResult) -> Dict[str, Any]:
        return {
            "result_id": entry.result_id,
            "pipeline_id": entry.pipeline_id,
            "step_name": entry.step_name,
            "result_data": entry.result_data,
            "status": entry.status,
            "created_at": entry.created_at,
            "seq": entry.seq,
            "metadata": entry.metadata,
        }

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when max_entries is exceeded."""
        if len(self._results) <= self._max_entries:
            return

        by_time = sorted(self._results.values(), key=lambda r: (r.created_at, r.seq))
        to_remove = len(self._results) - self._max_entries
        for entry in by_time[:to_remove]:
            del self._results[entry.result_id]
            self._total_pruned += 1
            logger.debug("result_pruned", result_id=entry.result_id)

        self._fire("results_pruned", {"count": to_remove})
