"""Pipeline Stage Tracker – tracks execution progress through pipeline stages.

Monitors pipeline execution with timing, status tracking, and dependency
management. Each stage execution records start/end times, status, and
results for full observability of pipeline progress.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _Pipeline:
    pipeline_id: str
    name: str
    stages: List[str]
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _StageExecution:
    execution_id: str
    pipeline_id: str
    stage_name: str
    status: str  # running, success, failed
    result: Any
    error: str
    started_at: float
    completed_at: float
    duration_ms: float


class PipelineStageTracker:
    """Tracks execution progress through pipeline stages with timing."""

    STAGE_STATUSES = ("running", "success", "failed")

    def __init__(self, max_entries: int = 10000):
        self._pipelines: Dict[str, _Pipeline] = {}
        self._executions: Dict[str, _StageExecution] = {}
        self._name_index: Dict[str, str] = {}
        # pipeline_id -> stage_name -> list of execution_ids
        self._stage_executions: Dict[str, Dict[str, List[str]]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # stats
        self._total_pipelines = 0
        self._total_executions = 0
        self._total_completed = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return "pst-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        total = len(self._pipelines) + len(self._executions)
        if total <= self._max_entries:
            return
        # Remove oldest pipelines until under limit
        sorted_pids = sorted(
            self._pipelines,
            key=lambda pid: self._pipelines[pid].created_at,
        )
        while len(self._pipelines) + len(self._executions) > self._max_entries and sorted_pids:
            pid = sorted_pids.pop(0)
            self._remove_pipeline_internal(pid)
        logger.debug("pruned_entries", remaining=len(self._pipelines) + len(self._executions))

    def _remove_pipeline_internal(self, pipeline_id: str) -> None:
        p = self._pipelines.pop(pipeline_id, None)
        if not p:
            return
        self._name_index.pop(p.name, None)
        stage_map = self._stage_executions.pop(pipeline_id, {})
        for exec_ids in stage_map.values():
            for eid in exec_ids:
                self._executions.pop(eid, None)

    # ------------------------------------------------------------------
    # Pipelines
    # ------------------------------------------------------------------

    def create_pipeline(
        self,
        name: str,
        stages: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new pipeline. Returns pipeline_id or '' on duplicate name."""
        if not name:
            return ""
        if name in self._name_index:
            logger.warning("duplicate_pipeline_name", name=name)
            return ""

        self._prune_if_needed()

        pid = self._make_id(name)
        now = time.time()
        p = _Pipeline(
            pipeline_id=pid,
            name=name,
            stages=list(stages or []),
            tags=list(tags or []),
            created_at=now,
            updated_at=now,
        )
        self._pipelines[pid] = p
        self._name_index[name] = pid
        self._stage_executions[pid] = {}
        self._total_pipelines += 1

        logger.info("pipeline_created", pipeline_id=pid, name=name)
        self._fire("pipeline_created", {"pipeline_id": pid, "name": name})
        return pid

    def get_pipeline(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline details as dict, or None if not found."""
        p = self._pipelines.get(pipeline_id)
        if not p:
            return None
        return {
            "pipeline_id": p.pipeline_id,
            "name": p.name,
            "stages": list(p.stages),
            "tags": list(p.tags),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

    def list_pipelines(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all pipelines, optionally filtered by tag."""
        results = []
        for p in self._pipelines.values():
            if tag and tag not in p.tags:
                continue
            results.append(self.get_pipeline(p.pipeline_id))
        return results

    def remove_pipeline(self, pipeline_id: str) -> bool:
        """Remove a pipeline and all its executions."""
        if pipeline_id not in self._pipelines:
            return False
        self._remove_pipeline_internal(pipeline_id)
        logger.info("pipeline_removed", pipeline_id=pipeline_id)
        self._fire("pipeline_removed", {"pipeline_id": pipeline_id})
        return True

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------

    def start_stage(self, pipeline_id: str, stage_name: str) -> str:
        """Start tracking a stage execution. Returns execution_id or ''."""
        p = self._pipelines.get(pipeline_id)
        if not p:
            logger.warning("start_stage_unknown_pipeline", pipeline_id=pipeline_id)
            return ""
        if not stage_name:
            return ""

        # Register stage in pipeline if not already present
        if stage_name not in p.stages:
            p.stages.append(stage_name)

        self._prune_if_needed()

        eid = self._make_id(f"{pipeline_id}-{stage_name}")
        now = time.time()
        exe = _StageExecution(
            execution_id=eid,
            pipeline_id=pipeline_id,
            stage_name=stage_name,
            status="running",
            result=None,
            error="",
            started_at=now,
            completed_at=0.0,
            duration_ms=0.0,
        )
        self._executions[eid] = exe

        # Track in stage_executions index
        if pipeline_id not in self._stage_executions:
            self._stage_executions[pipeline_id] = {}
        stage_map = self._stage_executions[pipeline_id]
        if stage_name not in stage_map:
            stage_map[stage_name] = []
        stage_map[stage_name].append(eid)

        p.updated_at = now
        self._total_executions += 1

        logger.info("stage_started", execution_id=eid, pipeline_id=pipeline_id, stage=stage_name)
        self._fire("stage_started", {
            "execution_id": eid,
            "pipeline_id": pipeline_id,
            "stage_name": stage_name,
        })
        return eid

    def complete_stage(
        self,
        execution_id: str,
        status: str = "success",
        result: Any = None,
    ) -> bool:
        """Complete a stage execution. Returns True on success."""
        exe = self._executions.get(execution_id)
        if not exe:
            logger.warning("complete_unknown_execution", execution_id=execution_id)
            return False
        if exe.status != "running":
            logger.warning("complete_not_running", execution_id=execution_id, status=exe.status)
            return False
        if status not in ("success", "failed"):
            status = "success"

        now = time.time()
        exe.status = status
        exe.result = result
        exe.completed_at = now
        exe.duration_ms = (now - exe.started_at) * 1000.0

        p = self._pipelines.get(exe.pipeline_id)
        if p:
            p.updated_at = now

        if status == "success":
            self._total_completed += 1
        else:
            self._total_failed += 1

        logger.info(
            "stage_completed",
            execution_id=execution_id,
            status=status,
            duration_ms=round(exe.duration_ms, 2),
        )
        self._fire("stage_completed", {
            "execution_id": execution_id,
            "pipeline_id": exe.pipeline_id,
            "stage_name": exe.stage_name,
            "status": status,
            "duration_ms": exe.duration_ms,
        })
        return True

    def fail_stage(self, execution_id: str, error: str = "") -> bool:
        """Mark a stage execution as failed."""
        exe = self._executions.get(execution_id)
        if not exe:
            logger.warning("fail_unknown_execution", execution_id=execution_id)
            return False
        if exe.status != "running":
            logger.warning("fail_not_running", execution_id=execution_id, status=exe.status)
            return False

        now = time.time()
        exe.status = "failed"
        exe.error = error
        exe.completed_at = now
        exe.duration_ms = (now - exe.started_at) * 1000.0

        p = self._pipelines.get(exe.pipeline_id)
        if p:
            p.updated_at = now

        self._total_failed += 1

        logger.info(
            "stage_failed",
            execution_id=execution_id,
            error=error,
            duration_ms=round(exe.duration_ms, 2),
        )
        self._fire("stage_failed", {
            "execution_id": execution_id,
            "pipeline_id": exe.pipeline_id,
            "stage_name": exe.stage_name,
            "error": error,
            "duration_ms": exe.duration_ms,
        })
        return True

    # ------------------------------------------------------------------
    # Status & progress queries
    # ------------------------------------------------------------------

    def get_stage_status(
        self,
        pipeline_id: str,
        stage_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the latest execution status for a stage in a pipeline."""
        stage_map = self._stage_executions.get(pipeline_id, {})
        exec_ids = stage_map.get(stage_name, [])
        if not exec_ids:
            return None

        # Return info from the most recent execution
        latest_eid = exec_ids[-1]
        exe = self._executions.get(latest_eid)
        if not exe:
            return None

        return {
            "execution_id": exe.execution_id,
            "pipeline_id": exe.pipeline_id,
            "stage_name": exe.stage_name,
            "status": exe.status,
            "result": exe.result,
            "error": exe.error,
            "started_at": exe.started_at,
            "completed_at": exe.completed_at,
            "duration_ms": exe.duration_ms,
            "total_runs": len(exec_ids),
        }

    def get_pipeline_progress(self, pipeline_id: str) -> Dict[str, Any]:
        """Get progress summary for a pipeline."""
        p = self._pipelines.get(pipeline_id)
        if not p:
            return {
                "total_stages": 0,
                "completed": 0,
                "failed": 0,
                "progress_pct": 0.0,
            }

        total = len(p.stages)
        if total == 0:
            return {
                "total_stages": 0,
                "completed": 0,
                "failed": 0,
                "progress_pct": 0.0,
            }

        completed = 0
        failed = 0
        stage_map = self._stage_executions.get(pipeline_id, {})

        for stage_name in p.stages:
            exec_ids = stage_map.get(stage_name, [])
            if not exec_ids:
                continue
            latest_eid = exec_ids[-1]
            exe = self._executions.get(latest_eid)
            if not exe:
                continue
            if exe.status == "success":
                completed += 1
            elif exe.status == "failed":
                failed += 1

        progress_pct = round(completed / total * 100.0, 1)

        return {
            "total_stages": total,
            "completed": completed,
            "failed": failed,
            "progress_pct": progress_pct,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        return {
            "current_pipelines": len(self._pipelines),
            "current_executions": len(self._executions),
            "total_pipelines": self._total_pipelines,
            "total_executions": self._total_executions,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._pipelines.clear()
        self._executions.clear()
        self._name_index.clear()
        self._stage_executions.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_pipelines = 0
        self._total_executions = 0
        self._total_completed = 0
        self._total_failed = 0
        logger.info("tracker_reset")
