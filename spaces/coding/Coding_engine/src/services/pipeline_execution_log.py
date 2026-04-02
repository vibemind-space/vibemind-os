"""Pipeline Execution Log -- records and queries pipeline execution events.

Provides a central, in-memory log for pipeline execution events such as
step started, step completed, errors, and skips.  Every logged entry
captures the pipeline, step name, event type, message, and timestamp.
The log supports filtering by step name and event type, per-pipeline
queries, and automatic pruning when the entry limit is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the execution log."""

    entries: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class PipelineExecutionLog:
    """In-memory execution log for pipelines.

    Parameters
    ----------
    max_entries:
        Maximum total number of log entries to keep.  When the limit
        is reached the oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = _State()

        # stats counters
        self._stats: Dict[str, int] = {
            "total_logged": 0,
            "total_pruned": 0,
            "total_cleared": 0,
            "total_queries": 0,
        }

        logger.debug("pipeline_execution_log.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, pipeline_id: str, step_name: str, now: float) -> str:
        """Create a collision-free entry ID using SHA-256 + _seq."""
        raw = f"{pipeline_id}-{step_name}-{now}-{self._state._seq}"
        return "pel-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Total entry count (internal)
    # ------------------------------------------------------------------

    def _total_entries(self) -> int:
        """Return the total number of log entries across all pipelines."""
        return sum(len(v) for v in self._state.entries.values())

    # ------------------------------------------------------------------
    # Logging entries
    # ------------------------------------------------------------------

    def log_entry(
        self,
        pipeline_id: str,
        step_name: str,
        event_type: str,
        message: str = "",
        metadata: dict = None,
    ) -> str:
        """Log a pipeline execution event and return its ``entry_id``.

        Parameters
        ----------
        pipeline_id:
            Identifier for the pipeline.
        step_name:
            Name of the pipeline step.
        event_type:
            One of ``"start"``, ``"complete"``, ``"error"``, ``"skip"``.
        message:
            Optional human-readable message.
        metadata:
            Optional dict of additional metadata.

        Returns the generated ``pel-...`` identifier for the new entry.
        """
        with self._lock:
            # prune if at capacity
            if self._total_entries() >= self._max_entries:
                self._prune()

            self._state._seq += 1
            now = time.time()
            entry_id = self._generate_id(pipeline_id, step_name, now)

            entry: Dict[str, Any] = {
                "entry_id": entry_id,
                "pipeline_id": pipeline_id,
                "step_name": step_name,
                "event_type": event_type,
                "message": message,
                "metadata": metadata or {},
                "timestamp": now,
            }

            self._state.entries.setdefault(pipeline_id, []).append(entry)
            self._stats["total_logged"] += 1

        logger.debug(
            "pipeline_execution_log.log_entry",
            entry_id=entry_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
            event_type=event_type,
        )
        self._fire("entry_logged", {
            "entry_id": entry_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "event_type": event_type,
            "message": message,
        })
        return entry_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_entries(
        self,
        pipeline_id: str,
        step_name: str = "",
        event_type: str = "",
    ) -> List[Dict[str, Any]]:
        """Return entries for *pipeline_id*, optionally filtered by *step_name* and/or *event_type*."""
        with self._lock:
            self._stats["total_queries"] += 1
            entries = list(self._state.entries.get(pipeline_id, []))
            if step_name:
                entries = [e for e in entries if e["step_name"] == step_name]
            if event_type:
                entries = [e for e in entries if e["event_type"] == event_type]
            return entries

    def get_latest_entry(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent log entry for *pipeline_id*, or ``None``."""
        with self._lock:
            self._stats["total_queries"] += 1
            entries = self._state.entries.get(pipeline_id, [])
            if not entries:
                return None
            return dict(entries[-1])

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_entry_count(self, pipeline_id: str = "") -> int:
        """Count entries, optionally filtered to a single pipeline."""
        with self._lock:
            if not pipeline_id:
                return self._total_entries()
            return len(self._state.entries.get(pipeline_id, []))

    # ------------------------------------------------------------------
    # Clearing
    # ------------------------------------------------------------------

    def clear_entries(self, pipeline_id: str) -> int:
        """Remove all entries for *pipeline_id*.

        Returns the number of entries removed.
        """
        with self._lock:
            entries = self._state.entries.pop(pipeline_id, [])
            count = len(entries)
            self._stats["total_cleared"] += count

        if count:
            logger.debug(
                "pipeline_execution_log.clear_entries",
                pipeline_id=pipeline_id,
                removed=count,
            )
            self._fire("entries_cleared", {
                "pipeline_id": pipeline_id,
                "count": count,
            })

        return count

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return all unique pipeline IDs that have at least one entry."""
        with self._lock:
            return [
                pid
                for pid, entries in self._state.entries.items()
                if entries
            ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._state.callbacks:
                del self._state.callbacks[name]
                return True
            return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._state.callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            return {
                **self._stats,
                "current_entries": self._total_entries(),
                "unique_pipelines": len([
                    pid for pid, entries in self._state.entries.items()
                    if entries
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.entries.clear()
            self._state._seq = 0
            self._state.callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
        logger.debug("pipeline_execution_log.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        all_entries: List[tuple] = []
        for pid, entries in self._state.entries.items():
            for entry in entries:
                all_entries.append((pid, entry))

        all_entries.sort(key=lambda x: x[1]["timestamp"])
        to_remove = max(len(all_entries) // 4, 1)

        for pid, entry in all_entries[:to_remove]:
            pipeline_list = self._state.entries.get(pid, [])
            try:
                pipeline_list.remove(entry)
            except ValueError:
                pass

        self._stats["total_pruned"] += to_remove
        logger.debug("pipeline_execution_log.prune", removed=to_remove)
