"""Pipeline step logger v2 — enhanced logging for pipeline step executions.

Provides structured log entries with level-based filtering, per-pipeline
querying, and summary statistics for pipeline step executions.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepLoggerV2State:
    """Internal state for the PipelineStepLoggerV2 service."""

    entries: Dict[str, Dict] = field(default_factory=dict)
    _seq: int = 0


class PipelineStepLoggerV2:
    """Enhanced logger for pipeline step executions.

    Records structured log entries with level, message, and metadata
    for each pipeline step. Supports filtering by pipeline, step name,
    and log level, plus summary statistics.
    """

    PREFIX = "pslv2-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepLoggerV2State()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID from data + internal sequence counter."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding MAX_ENTRIES."""
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_ids = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for eid in sorted_ids[:to_remove]:
                del self._state.entries[eid]

    # ------------------------------------------------------------------
    # Event firing
    # ------------------------------------------------------------------

    def _fire(self, event: str, data: Any) -> None:
        """Fire change notifications to on_change and all callbacks."""
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.error("on_change callback failed for event %s", event)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.error("Callback %s failed for event %s", name, event)

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def register_callback(self, name: str, callback: Callable) -> None:
        """Register a named callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def log(
        self,
        pipeline_id: str,
        step_name: str,
        level: str = "info",
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a log entry for a pipeline step execution.

        Args:
            pipeline_id: Identifier of the pipeline.
            step_name: Name of the step being logged.
            level: Log level — one of "debug", "info", "warning", "error".
            message: Human-readable log message.
            metadata: Optional dict of additional structured data.

        Returns:
            The generated log entry ID.
        """
        log_id = self._generate_id(f"{pipeline_id}{step_name}{level}")
        entry = {
            "id": log_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "level": level,
            "message": message,
            "metadata": metadata or {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[log_id] = entry
        self._prune()
        self._fire("log_created", entry)
        return log_id

    def get_log(self, log_id: str) -> Optional[Dict]:
        """Return a single log entry by ID, or None if not found."""
        return self._state.entries.get(log_id)

    def get_logs(
        self,
        pipeline_id: str,
        step_name: str = "",
        level: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """Query log entries with optional filters, sorted newest first.

        Args:
            pipeline_id: Required pipeline identifier to filter on.
            step_name: Optional step name filter.
            level: Optional level filter.
            limit: Maximum number of entries to return.

        Returns:
            List of matching log entry dicts, newest first.
        """
        results = []
        for entry in self._state.entries.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            if level and entry["level"] != level:
                continue
            results.append(entry)
        results.sort(key=lambda e: e["_seq"], reverse=True)
        return results[:limit]

    def get_log_count(self, pipeline_id: str = "", level: str = "") -> int:
        """Return the count of log entries matching optional filters."""
        count = 0
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            if level and entry["level"] != level:
                continue
            count += 1
        return count

    def clear_logs(self, pipeline_id: str) -> int:
        """Remove all log entries for a pipeline. Returns count removed."""
        to_remove = [
            eid
            for eid, entry in self._state.entries.items()
            if entry["pipeline_id"] == pipeline_id
        ]
        for eid in to_remove:
            del self._state.entries[eid]
        if to_remove:
            self._fire("logs_cleared", {"pipeline_id": pipeline_id, "count": len(to_remove)})
        return len(to_remove)

    def get_levels_summary(self, pipeline_id: str) -> Dict[str, int]:
        """Return counts per level for a given pipeline.

        Returns:
            Dict with keys "debug", "info", "warning", "error" and integer counts.
        """
        summary: Dict[str, int] = {"debug": 0, "info": 0, "warning": 0, "error": 0}
        for entry in self._state.entries.values():
            if entry["pipeline_id"] == pipeline_id:
                lvl = entry["level"]
                if lvl in summary:
                    summary[lvl] += 1
        return summary

    def get_stats(self) -> Dict[str, Any]:
        """Return overall statistics.

        Returns:
            Dict with total_logs, total_pipelines, and logs_by_level.
        """
        pipelines = set()
        by_level: Dict[str, int] = {"debug": 0, "info": 0, "warning": 0, "error": 0}
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
            lvl = entry["level"]
            if lvl in by_level:
                by_level[lvl] += 1
        return {
            "total_logs": len(self._state.entries),
            "total_pipelines": len(pipelines),
            "logs_by_level": by_level,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineStepLoggerV2State()
        self._fire("reset", {})
