"""Pipeline error handler.

Handles and categorizes pipeline errors — registers error handlers,
records errors with categories, and provides error summaries.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """A single pipeline error record."""
    error_id: str = ""
    pipeline_id: str = ""
    step_name: str = ""
    error_type: str = ""
    message: str = ""
    severity: str = "error"
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline Error Handler
# ---------------------------------------------------------------------------

class PipelineErrorHandler:
    """Handles and categorizes pipeline errors with callbacks and summaries."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self.errors: Dict[str, ErrorEntry] = {}
        self.handlers: Dict[str, Callable] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_recorded": 0,
            "total_cleared": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'peh-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"peh-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self.errors) < self._max_entries:
            return
        sorted_entries = sorted(self.errors.values(), key=lambda e: e.timestamp)
        to_remove = len(self.errors) - self._max_entries + 1
        for entry in sorted_entries[:to_remove]:
            del self.errors[entry.error_id]
        logger.debug("pruned_errors", removed=to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # API — record_error
    # ------------------------------------------------------------------

    def record_error(self, pipeline_id: str, step_name: str,
                     error_type: str, message: str,
                     severity: str = "error") -> str:
        """Record a pipeline error. Returns error ID (peh-xxx)."""
        self._prune_if_needed()

        error_id = self._next_id(f"{pipeline_id}:{step_name}")
        now = time.time()

        entry = ErrorEntry(
            error_id=error_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
            error_type=error_type,
            message=message,
            severity=severity,
            timestamp=now,
        )
        self.errors[error_id] = entry
        self._stats["total_recorded"] += 1

        logger.info("error_recorded", error_id=error_id,
                     pipeline_id=pipeline_id, step_name=step_name,
                     error_type=error_type, severity=severity)

        self._fire("record_error", {
            "error_id": error_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "error_type": error_type,
            "severity": severity,
        })

        return error_id

    # ------------------------------------------------------------------
    # API — get_errors
    # ------------------------------------------------------------------

    def get_errors(self, pipeline_id: str, step_name: str = "",
                   error_type: str = "", severity: str = "") -> list:
        """Get errors with optional filters."""
        self._stats["total_lookups"] += 1
        result = []
        for entry in self.errors.values():
            if entry.pipeline_id != pipeline_id:
                continue
            if step_name and entry.step_name != step_name:
                continue
            if error_type and entry.error_type != error_type:
                continue
            if severity and entry.severity != severity:
                continue
            result.append({
                "error_id": entry.error_id,
                "pipeline_id": entry.pipeline_id,
                "step_name": entry.step_name,
                "error_type": entry.error_type,
                "message": entry.message,
                "severity": entry.severity,
                "timestamp": entry.timestamp,
            })
        return result

    # ------------------------------------------------------------------
    # API — get_error_summary
    # ------------------------------------------------------------------

    def get_error_summary(self, pipeline_id: str) -> dict:
        """Summary with counts by error_type and severity."""
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        total = 0

        for entry in self.errors.values():
            if entry.pipeline_id != pipeline_id:
                continue
            total += 1
            by_type[entry.error_type] = by_type.get(entry.error_type, 0) + 1
            by_severity[entry.severity] = by_severity.get(entry.severity, 0) + 1

        return {
            "pipeline_id": pipeline_id,
            "total": total,
            "by_type": by_type,
            "by_severity": by_severity,
        }

    # ------------------------------------------------------------------
    # API — clear_errors
    # ------------------------------------------------------------------

    def clear_errors(self, pipeline_id: str) -> int:
        """Clear errors for pipeline, return count removed."""
        to_remove = [eid for eid, e in self.errors.items()
                     if e.pipeline_id == pipeline_id]
        for eid in to_remove:
            del self.errors[eid]

        count = len(to_remove)
        self._stats["total_cleared"] += count

        if count:
            logger.info("errors_cleared", pipeline_id=pipeline_id, count=count)
            self._fire("clear_errors", {
                "pipeline_id": pipeline_id,
                "count": count,
            })

        return count

    # ------------------------------------------------------------------
    # API — get_error_count
    # ------------------------------------------------------------------

    def get_error_count(self, pipeline_id: str = "") -> int:
        """Count errors total or per pipeline."""
        if not pipeline_id:
            return len(self.errors)
        return sum(1 for e in self.errors.values()
                   if e.pipeline_id == pipeline_id)

    # ------------------------------------------------------------------
    # API — list_pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> list:
        """List pipelines with errors."""
        pipelines: set = set()
        for entry in self.errors.values():
            pipelines.add(entry.pipeline_id)
        return sorted(pipelines)

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        return {
            "total_recorded": self._stats["total_recorded"],
            "total_cleared": self._stats["total_cleared"],
            "total_lookups": self._stats["total_lookups"],
            "current_errors": len(self.errors),
            "current_handlers": len(self.handlers),
            "current_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state."""
        self.errors.clear()
        self.handlers.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {
            "total_recorded": 0,
            "total_cleared": 0,
            "total_lookups": 0,
        }
        logger.info("pipeline_error_handler_reset")
