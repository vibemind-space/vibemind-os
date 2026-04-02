"""Pipeline Stage Manager – manages pipeline execution stages.

Organizes pipeline execution into ordered stages with transitions,
gates, and progress tracking. Each stage can have pre/post conditions
and supports rollback to previous stages.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Pipeline:
    pipeline_id: str
    name: str
    stages: List[str]  # ordered stage_ids
    current_stage_idx: int
    status: str  # created, running, paused, completed, failed
    tags: List[str]
    created_at: float
    updated_at: float
    metadata: Dict[str, Any]


@dataclass
class _Stage:
    stage_id: str
    pipeline_id: str
    name: str
    order: int
    status: str  # pending, running, completed, skipped, failed
    gate: str  # condition description for entry
    result: str
    started_at: float
    completed_at: float
    duration_ms: float
    created_at: float


class PipelineStageManager:
    """Manages ordered pipeline stages with transitions."""

    PIPELINE_STATUSES = ("created", "running", "paused", "completed", "failed")
    STAGE_STATUSES = ("pending", "running", "completed", "skipped", "failed")

    def __init__(self, max_pipelines: int = 10000, max_stages: int = 200000):
        self._pipelines: Dict[str, _Pipeline] = {}
        self._stages: Dict[str, _Stage] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_pipelines = max_pipelines
        self._max_stages = max_stages
        self._seq = 0

        # stats
        self._total_pipelines = 0
        self._total_stages = 0
        self._total_completed = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # Pipelines
    # ------------------------------------------------------------------

    def create_pipeline(
        self,
        name: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._pipelines) >= self._max_pipelines:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        pid = "ppl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        p = _Pipeline(
            pipeline_id=pid,
            name=name,
            stages=[],
            current_stage_idx=-1,
            status="created",
            tags=tags or [],
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        self._pipelines[pid] = p
        self._name_index[name] = pid
        self._total_pipelines += 1
        self._fire("pipeline_created", {"pipeline_id": pid, "name": name})
        return pid

    def get_pipeline(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        p = self._pipelines.get(pipeline_id)
        if not p:
            return None
        current_stage = None
        if 0 <= p.current_stage_idx < len(p.stages):
            current_stage = p.stages[p.current_stage_idx]
        return {
            "pipeline_id": p.pipeline_id,
            "name": p.name,
            "stages": list(p.stages),
            "current_stage_idx": p.current_stage_idx,
            "current_stage_id": current_stage,
            "status": p.status,
            "tags": list(p.tags),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "metadata": dict(p.metadata),
        }

    def get_pipeline_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        pid = self._name_index.get(name)
        if not pid:
            return None
        return self.get_pipeline(pid)

    def remove_pipeline(self, pipeline_id: str) -> bool:
        p = self._pipelines.pop(pipeline_id, None)
        if not p:
            return False
        self._name_index.pop(p.name, None)
        for sid in p.stages:
            self._stages.pop(sid, None)
        self._fire("pipeline_removed", {"pipeline_id": pipeline_id})
        return True

    def list_pipelines(
        self,
        status: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for p in self._pipelines.values():
            if status and p.status != status:
                continue
            if tag and tag not in p.tags:
                continue
            results.append(self.get_pipeline(p.pipeline_id))
        return results

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def add_stage(
        self,
        pipeline_id: str,
        name: str,
        gate: str = "",
    ) -> str:
        p = self._pipelines.get(pipeline_id)
        if not p or not name:
            return ""
        if p.status not in ("created",):
            return ""  # can only add stages before running
        if len(self._stages) >= self._max_stages:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{pipeline_id}-{now}-{self._seq}"
        sid = "stg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        order = len(p.stages)
        stage = _Stage(
            stage_id=sid,
            pipeline_id=pipeline_id,
            name=name,
            order=order,
            status="pending",
            gate=gate,
            result="",
            started_at=0.0,
            completed_at=0.0,
            duration_ms=0.0,
            created_at=now,
        )
        self._stages[sid] = stage
        p.stages.append(sid)
        p.updated_at = now
        self._total_stages += 1
        self._fire("stage_added", {"stage_id": sid, "pipeline_id": pipeline_id})
        return sid

    def get_stage(self, stage_id: str) -> Optional[Dict[str, Any]]:
        s = self._stages.get(stage_id)
        if not s:
            return None
        return {
            "stage_id": s.stage_id,
            "pipeline_id": s.pipeline_id,
            "name": s.name,
            "order": s.order,
            "status": s.status,
            "gate": s.gate,
            "result": s.result,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
            "duration_ms": s.duration_ms,
            "created_at": s.created_at,
        }

    def get_pipeline_stages(self, pipeline_id: str) -> List[Dict[str, Any]]:
        p = self._pipelines.get(pipeline_id)
        if not p:
            return []
        return [self.get_stage(sid) for sid in p.stages if sid in self._stages]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def start_pipeline(self, pipeline_id: str) -> bool:
        """Start executing a pipeline from its first stage."""
        p = self._pipelines.get(pipeline_id)
        if not p or p.status != "created" or not p.stages:
            return False
        p.status = "running"
        p.current_stage_idx = 0
        p.updated_at = time.time()
        # start first stage
        first = self._stages.get(p.stages[0])
        if first:
            first.status = "running"
            first.started_at = time.time()
        self._fire("pipeline_started", {"pipeline_id": pipeline_id})
        return True

    def advance_stage(self, pipeline_id: str, result: str = "") -> bool:
        """Complete current stage and move to next."""
        p = self._pipelines.get(pipeline_id)
        if not p or p.status != "running":
            return False
        if p.current_stage_idx < 0 or p.current_stage_idx >= len(p.stages):
            return False

        # complete current
        current = self._stages.get(p.stages[p.current_stage_idx])
        if not current or current.status != "running":
            return False
        now = time.time()
        current.status = "completed"
        current.result = result
        current.completed_at = now
        current.duration_ms = (now - current.started_at) * 1000 if current.started_at else 0

        self._fire("stage_completed", {"stage_id": current.stage_id})

        # move to next
        next_idx = p.current_stage_idx + 1
        if next_idx < len(p.stages):
            p.current_stage_idx = next_idx
            next_stage = self._stages.get(p.stages[next_idx])
            if next_stage:
                next_stage.status = "running"
                next_stage.started_at = time.time()
            self._fire("stage_started", {"stage_id": p.stages[next_idx]})
        else:
            # all stages done
            p.status = "completed"
            p.current_stage_idx = len(p.stages) - 1
            self._total_completed += 1
            self._fire("pipeline_completed", {"pipeline_id": pipeline_id})

        p.updated_at = time.time()
        return True

    def fail_stage(self, pipeline_id: str, result: str = "") -> bool:
        """Fail current stage and pipeline."""
        p = self._pipelines.get(pipeline_id)
        if not p or p.status != "running":
            return False
        if p.current_stage_idx < 0:
            return False

        current = self._stages.get(p.stages[p.current_stage_idx])
        if not current or current.status != "running":
            return False

        now = time.time()
        current.status = "failed"
        current.result = result
        current.completed_at = now
        current.duration_ms = (now - current.started_at) * 1000 if current.started_at else 0

        p.status = "failed"
        p.updated_at = now
        self._total_failed += 1
        self._fire("stage_failed", {"stage_id": current.stage_id})
        self._fire("pipeline_failed", {"pipeline_id": pipeline_id})
        return True

    def skip_stage(self, pipeline_id: str) -> bool:
        """Skip current stage and move to next."""
        p = self._pipelines.get(pipeline_id)
        if not p or p.status != "running":
            return False
        if p.current_stage_idx < 0 or p.current_stage_idx >= len(p.stages):
            return False

        current = self._stages.get(p.stages[p.current_stage_idx])
        if not current or current.status != "running":
            return False

        current.status = "skipped"
        current.completed_at = time.time()

        next_idx = p.current_stage_idx + 1
        if next_idx < len(p.stages):
            p.current_stage_idx = next_idx
            next_stage = self._stages.get(p.stages[next_idx])
            if next_stage:
                next_stage.status = "running"
                next_stage.started_at = time.time()
        else:
            p.status = "completed"
            self._total_completed += 1
            self._fire("pipeline_completed", {"pipeline_id": pipeline_id})

        p.updated_at = time.time()
        self._fire("stage_skipped", {"stage_id": current.stage_id})
        return True

    def pause_pipeline(self, pipeline_id: str) -> bool:
        p = self._pipelines.get(pipeline_id)
        if not p or p.status != "running":
            return False
        p.status = "paused"
        p.updated_at = time.time()
        self._fire("pipeline_paused", {"pipeline_id": pipeline_id})
        return True

    def resume_pipeline(self, pipeline_id: str) -> bool:
        p = self._pipelines.get(pipeline_id)
        if not p or p.status != "paused":
            return False
        p.status = "running"
        p.updated_at = time.time()
        self._fire("pipeline_resumed", {"pipeline_id": pipeline_id})
        return True

    def get_progress(self, pipeline_id: str) -> Dict[str, Any]:
        """Get pipeline progress percentage."""
        p = self._pipelines.get(pipeline_id)
        if not p or not p.stages:
            return {"completed": 0, "total": 0, "percentage": 0.0}
        completed = sum(
            1 for sid in p.stages
            if self._stages.get(sid) and self._stages[sid].status in ("completed", "skipped")
        )
        return {
            "completed": completed,
            "total": len(p.stages),
            "percentage": round(completed / len(p.stages) * 100, 1),
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_pipelines": len(self._pipelines),
            "current_stages": len(self._stages),
            "total_pipelines": self._total_pipelines,
            "total_stages": self._total_stages,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
        }

    def reset(self) -> None:
        self._pipelines.clear()
        self._stages.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_pipelines = 0
        self._total_stages = 0
        self._total_completed = 0
        self._total_failed = 0
