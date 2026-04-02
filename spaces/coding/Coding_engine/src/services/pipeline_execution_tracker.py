"""Pipeline execution tracker – track pipeline execution progress with step completion.

Provides execution lifecycle management (start, step completion, failure, finish)
with progress tracking, callbacks, and statistics collection.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _ExecutionEntry:
    """Internal record for a single pipeline execution."""

    execution_id: str = ""
    pipeline_id: str = ""
    total_steps: int = 0
    completed_steps: List[str] = field(default_factory=list)
    status: str = "running"  # running, completed, failed
    failure_reason: str = ""
    seq: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineExecutionTracker:
    """Tracks pipeline execution progress with step completion."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._executions: Dict[str, _ExecutionEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{uuid.uuid4().hex}{self._seq}"
        return "pet-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest finished entries when over capacity."""
        if len(self._executions) < self._max_entries:
            return
        finished = [
            (eid, e)
            for eid, e in self._executions.items()
            if e.status in ("completed", "failed")
        ]
        finished.sort(key=lambda x: x[1].created_at)
        to_remove = len(self._executions) - self._max_entries + 1
        for eid, _ in finished[:to_remove]:
            del self._executions[eid]
            logger.debug("pipeline_execution_tracker.pruned", execution_id=eid)

    # ------------------------------------------------------------------
    # Execution lifecycle
    # ------------------------------------------------------------------

    def start_execution(self, pipeline_id: str, total_steps: int = 0) -> str:
        """Start tracking a pipeline execution. Returns execution ID."""
        if not pipeline_id:
            logger.warning("pipeline_execution_tracker.start_empty_pipeline_id")
            return ""
        self._prune_if_needed()

        eid = self._generate_id(pipeline_id)
        self._executions[eid] = _ExecutionEntry(
            execution_id=eid,
            pipeline_id=pipeline_id,
            total_steps=max(0, total_steps),
            status="running",
            seq=self._seq,
        )
        logger.info(
            "pipeline_execution_tracker.started",
            execution_id=eid,
            pipeline_id=pipeline_id,
            total_steps=total_steps,
        )
        self._fire("execution_started", {"execution_id": eid, "pipeline_id": pipeline_id})
        return eid

    def complete_step(self, execution_id: str, step_name: str) -> bool:
        """Mark a step as complete. Returns True on success."""
        entry = self._executions.get(execution_id)
        if not entry:
            logger.warning("pipeline_execution_tracker.step_not_found", execution_id=execution_id)
            return False
        if entry.status != "running":
            logger.warning(
                "pipeline_execution_tracker.step_not_running",
                execution_id=execution_id,
                status=entry.status,
            )
            return False
        if not step_name:
            return False

        entry.completed_steps.append(step_name)
        logger.info(
            "pipeline_execution_tracker.step_completed",
            execution_id=execution_id,
            step_name=step_name,
            completed=len(entry.completed_steps),
            total=entry.total_steps,
        )
        self._fire("step_completed", {
            "execution_id": execution_id,
            "step_name": step_name,
            "progress": self.get_progress(execution_id),
        })
        return True

    def fail_execution(self, execution_id: str, reason: str = "") -> bool:
        """Mark an execution as failed. Returns True on success."""
        entry = self._executions.get(execution_id)
        if not entry:
            logger.warning("pipeline_execution_tracker.fail_not_found", execution_id=execution_id)
            return False
        if entry.status != "running":
            return False

        entry.status = "failed"
        entry.failure_reason = reason
        entry.finished_at = time.time()
        logger.info(
            "pipeline_execution_tracker.failed",
            execution_id=execution_id,
            reason=reason,
        )
        self._fire("execution_failed", {"execution_id": execution_id, "reason": reason})
        return True

    def finish_execution(self, execution_id: str) -> bool:
        """Mark an execution as completed. Returns True on success."""
        entry = self._executions.get(execution_id)
        if not entry:
            logger.warning("pipeline_execution_tracker.finish_not_found", execution_id=execution_id)
            return False
        if entry.status != "running":
            return False

        entry.status = "completed"
        entry.finished_at = time.time()
        logger.info(
            "pipeline_execution_tracker.finished",
            execution_id=execution_id,
            steps_completed=len(entry.completed_steps),
        )
        self._fire("execution_finished", {"execution_id": execution_id})
        return True

    # ------------------------------------------------------------------
    # Progress & queries
    # ------------------------------------------------------------------

    def get_progress(self, execution_id: str) -> float:
        """Get execution progress as a float from 0.0 to 1.0."""
        entry = self._executions.get(execution_id)
        if not entry:
            return 0.0
        if entry.status == "completed":
            return 1.0
        if entry.total_steps <= 0:
            return 0.0
        return min(1.0, len(entry.completed_steps) / entry.total_steps)

    def get_execution(self, execution_id: str) -> Optional[Dict]:
        """Get execution details as a dict."""
        entry = self._executions.get(execution_id)
        if not entry:
            return None
        return {
            "execution_id": entry.execution_id,
            "pipeline_id": entry.pipeline_id,
            "status": entry.status,
            "total_steps": entry.total_steps,
            "completed_steps": list(entry.completed_steps),
            "failure_reason": entry.failure_reason,
            "progress": self.get_progress(execution_id),
            "created_at": entry.created_at,
            "finished_at": entry.finished_at,
            "duration": (entry.finished_at or time.time()) - entry.created_at,
        }

    def get_active_executions(self) -> List[Dict]:
        """Get all currently running executions."""
        results = []
        for eid, entry in self._executions.items():
            if entry.status == "running":
                results.append({
                    "execution_id": entry.execution_id,
                    "pipeline_id": entry.pipeline_id,
                    "progress": self.get_progress(eid),
                    "completed_steps": len(entry.completed_steps),
                    "total_steps": entry.total_steps,
                    "created_at": entry.created_at,
                })
        results.sort(key=lambda x: x["created_at"])
        return results

    def list_pipelines(self) -> List[str]:
        """Get a list of unique pipeline IDs being tracked."""
        seen: Dict[str, None] = {}
        for entry in self._executions.values():
            seen[entry.pipeline_id] = None
        return list(seen.keys())

    def get_execution_count(self) -> int:
        """Get total number of tracked executions."""
        return len(self._executions)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback for execution events."""
        self._callbacks[name] = callback
        logger.debug("pipeline_execution_tracker.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback. Returns True if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("pipeline_execution_tracker.callback_removed", name=name)
        return True

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Get aggregate statistics about tracked executions."""
        running = 0
        completed = 0
        failed = 0
        for entry in self._executions.values():
            if entry.status == "running":
                running += 1
            elif entry.status == "completed":
                completed += 1
            elif entry.status == "failed":
                failed += 1
        return {
            "total_executions": len(self._executions),
            "running": running,
            "completed": completed,
            "failed": failed,
            "unique_pipelines": len(self.list_pipelines()),
            "callbacks_registered": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all executions, callbacks, and reset sequence counter."""
        self._executions.clear()
        self._callbacks.clear()
        self._seq = 0
        logger.info("pipeline_execution_tracker.reset")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("pipeline_execution_tracker.callback_error", action=action)
