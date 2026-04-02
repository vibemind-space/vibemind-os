"""Pipeline step logger — logs pipeline step execution details.

Records input/output data, duration, and status for each pipeline step
execution. Supports filtering by pipeline, step name, and status.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepLoggerState:
    """Internal state for the PipelineStepLogger service."""

    logs: Dict[str, Dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepLogger:
    """Logs pipeline step execution details.

    Captures input/output data, duration, and status for each step
    execution, supporting queries and filtering across pipelines.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepLoggerState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psl-{self._state._seq}-{id(self)}"
        return "psl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

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
        if len(self._state.logs) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._state.logs.keys(),
            key=lambda k: self._state.logs[k].get("timestamp", 0),
        )
        remove_count = len(self._state.logs) - self._max_entries
        for log_id in sorted_ids[:remove_count]:
            del self._state.logs[log_id]

    # ------------------------------------------------------------------
    # Log step
    # ------------------------------------------------------------------

    def log_step(
        self,
        pipeline_id: str,
        step_name: str,
        status: str = "success",
        input_data: Optional[Dict] = None,
        output_data: Optional[Dict] = None,
        duration_ms: float = 0.0,
    ) -> str:
        """Log a step execution. Returns a log ID (psl-xxx)."""
        self._prune_if_needed()

        log_id = self._generate_id()
        entry = {
            "log_id": log_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "status": status,
            "input_data": input_data or {},
            "output_data": output_data or {},
            "duration_ms": duration_ms,
            "timestamp": time.time(),
            "_seq_num": self._state._seq,
        }
        self._state.logs[log_id] = entry

        self._fire("step_logged", {
            "log_id": log_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "status": status,
        })
        return log_id

    # ------------------------------------------------------------------
    # Get logs
    # ------------------------------------------------------------------

    def get_logs(
        self,
        pipeline_id: str,
        step_name: str = "",
        status: str = "",
    ) -> List[Dict]:
        """Get logs for a pipeline, optionally filtered by step_name and status."""
        results = []
        for entry in self._state.logs.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: e["timestamp"])
        return results

    # ------------------------------------------------------------------
    # Get latest log
    # ------------------------------------------------------------------

    def get_latest_log(self, pipeline_id: str) -> Optional[Dict]:
        """Return the most recent log entry for a pipeline, or None."""
        candidates = [
            e for e in self._state.logs.values()
            if e["pipeline_id"] == pipeline_id
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda e: (e["timestamp"], e.get("_seq_num", 0)))
        return dict(latest)

    # ------------------------------------------------------------------
    # Get log count
    # ------------------------------------------------------------------

    def get_log_count(self, pipeline_id: str = "") -> int:
        """Get total number of log entries, optionally for a specific pipeline."""
        if pipeline_id:
            return sum(
                1 for e in self._state.logs.values()
                if e["pipeline_id"] == pipeline_id
            )
        return len(self._state.logs)

    # ------------------------------------------------------------------
    # Clear logs
    # ------------------------------------------------------------------

    def clear_logs(self, pipeline_id: str) -> int:
        """Clear all logs for a pipeline. Returns count of removed entries."""
        to_remove = [
            log_id for log_id, e in self._state.logs.items()
            if e["pipeline_id"] == pipeline_id
        ]
        for log_id in to_remove:
            del self._state.logs[log_id]

        if to_remove:
            self._fire("logs_cleared", {
                "pipeline_id": pipeline_id,
                "count": len(to_remove),
            })
        return len(to_remove)

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have log entries."""
        seen: Dict[str, bool] = {}
        for entry in self._state.logs.values():
            seen[entry["pipeline_id"]] = True
        return list(seen.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        pipelines = set(e["pipeline_id"] for e in self._state.logs.values())
        return {
            "total_logs": len(self._state.logs),
            "max_entries": self._max_entries,
            "pipelines": len(pipelines),
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored logs, callbacks, and reset sequence."""
        self._state.logs.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
