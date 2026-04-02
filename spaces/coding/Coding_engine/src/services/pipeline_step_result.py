"""Pipeline step result — stores and queries step execution results.

Maintains per-pipeline, per-step execution results with status tracking.
Useful for auditing pipeline runs, querying outcomes, and filtering
by step name or status.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepResultState:
    """Internal state for the PipelineStepResult service."""

    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepResult:
    """Stores and queries step execution results.

    Tracks execution results per pipeline and step, supporting queries
    by pipeline, step name, status, and recency.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepResultState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psr3-{self._state._seq}-{id(self)}"
        return "psr3-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict oldest entries when the store exceeds max_entries."""
        if len(self._state.results) <= self._max_entries:
            return
        remove_count = len(self._state.results) - self._max_entries
        sorted_ids = sorted(
            self._state.results.keys(),
            key=lambda rid: self._state.results[rid].get("_seq_num", 0),
        )
        for rid in sorted_ids[:remove_count]:
            del self._state.results[rid]

    # ------------------------------------------------------------------
    # Store result
    # ------------------------------------------------------------------

    def store_result(
        self,
        pipeline_id: str,
        step_name: str,
        status: str,
        data: Optional[dict] = None,
    ) -> str:
        """Store a step execution result. Returns result ID (psr3-xxx)."""
        self._prune_if_needed()

        result_id = self._generate_id()
        entry: Dict[str, Any] = {
            "result_id": result_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "status": status,
            "data": data or {},
            "timestamp": time.time(),
            "_seq_num": self._state._seq,
        }
        self._state.results[result_id] = entry

        self._fire("result_stored", {
            "result_id": result_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "status": status,
        })
        return result_id

    # ------------------------------------------------------------------
    # Get result
    # ------------------------------------------------------------------

    def get_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        """Get a single result by ID. Returns None if not found."""
        entry = self._state.results.get(result_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get results
    # ------------------------------------------------------------------

    def get_results(
        self,
        pipeline_id: str,
        step_name: str = "",
        status: str = "",
    ) -> List[Dict[str, Any]]:
        """Get results with optional filters for step_name and status."""
        matched: List[Dict[str, Any]] = []
        for entry in self._state.results.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            if status and entry["status"] != status:
                continue
            matched.append(dict(entry))
        return matched

    # ------------------------------------------------------------------
    # Get latest result
    # ------------------------------------------------------------------

    def get_latest_result(
        self,
        pipeline_id: str,
        step_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Most recent result for a pipeline. Uses _seq_num for tiebreaking."""
        candidates = self.get_results(pipeline_id, step_name=step_name)
        if not candidates:
            return None
        return max(candidates, key=lambda e: e["_seq_num"])

    # ------------------------------------------------------------------
    # Get result count
    # ------------------------------------------------------------------

    def get_result_count(self, pipeline_id: str = "") -> int:
        """Get count of results, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.results)
        return sum(
            1 for entry in self._state.results.values()
            if entry["pipeline_id"] == pipeline_id
        )

    # ------------------------------------------------------------------
    # Clear results
    # ------------------------------------------------------------------

    def clear_results(self, pipeline_id: str) -> int:
        """Remove all results for a pipeline. Returns number removed."""
        to_remove = [
            rid for rid, entry in self._state.results.items()
            if entry["pipeline_id"] == pipeline_id
        ]
        for rid in to_remove:
            del self._state.results[rid]
        if to_remove:
            self._fire("results_cleared", {
                "pipeline_id": pipeline_id,
                "count": len(to_remove),
            })
        return len(to_remove)

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have results."""
        seen: Dict[str, bool] = {}
        for entry in self._state.results.values():
            seen[entry["pipeline_id"]] = True
        return list(seen.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        pipelines = set()
        statuses: Dict[str, int] = {}
        for entry in self._state.results.values():
            pipelines.add(entry["pipeline_id"])
            s = entry["status"]
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total_results": len(self._state.results),
            "max_entries": self._max_entries,
            "pipelines": len(pipelines),
            "statuses": dict(statuses),
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored results, callbacks, and reset sequence."""
        self._state.results.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
