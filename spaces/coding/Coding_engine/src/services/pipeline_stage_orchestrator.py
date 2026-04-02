"""Pipeline Stage Orchestrator – orchestrates multi-stage pipeline execution.

Manages DAG-style stage dependencies with topological ordering, parallel
stage execution tracking, and stage-level result aggregation.  Unlike
PipelineIntegrationBus (which chains sequential steps), this module handles
dependency graphs where stages in the same "wave" can execute in parallel.

Capabilities:
  - Create named pipelines with tags
  - Add stages with optional handler callables
  - Define inter-stage dependencies (DAG edges)
  - Compute execution order via Kahn's algorithm (waves of independent stages)
  - Execute pipelines respecting dependency order
  - Track per-stage results from the last execution
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
    tags: List[str]
    execution_count: int
    last_execution_time: float
    created_at: float


@dataclass
class _Stage:
    stage_id: str
    pipeline_name: str
    stage_name: str
    tags: List[str]
    created_at: float


@dataclass
class _StageDependency:
    dep_id: str
    pipeline_name: str
    stage_name: str
    depends_on: str
    created_at: float


@dataclass
class _StageResult:
    result_id: str
    pipeline_name: str
    stage_name: str
    success: bool
    result: Any
    error: str
    duration: float
    timestamp: float


@dataclass
class _OrchestratorEvent:
    event_id: str
    pipeline_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class PipelineStageOrchestrator:
    """Orchestrates multi-stage pipeline execution with DAG dependencies."""

    def __init__(self, max_pipelines: int = 5000, max_history: int = 100000):
        self._pipelines: Dict[str, _Pipeline] = {}
        self._name_index: Dict[str, str] = {}  # name -> pipeline_id
        self._stages: Dict[str, List[_Stage]] = {}  # pipeline_name -> stages
        self._handlers: Dict[str, Callable] = {}  # "pipeline_name::stage_name" -> handler
        self._dependencies: Dict[str, List[_StageDependency]] = {}  # pipeline_name -> deps
        self._results: Dict[str, Dict[str, _StageResult]] = {}  # pipeline_name -> {stage_name -> result}
        self._history: List[_OrchestratorEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_pipelines = max_pipelines
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_stages_added = 0
        self._total_executions = 0
        self._total_stage_executions = 0
        self._total_failures = 0

    # ------------------------------------------------------------------
    # Pipeline management
    # ------------------------------------------------------------------

    def create_pipeline(self, name: str, tags: Optional[List[str]] = None) -> str:
        if not name or name in self._name_index:
            return ""
        if len(self._pipelines) >= self._max_pipelines:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        pid = "opl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        pipeline = _Pipeline(
            pipeline_id=pid,
            name=name,
            tags=tags or [],
            execution_count=0,
            last_execution_time=0.0,
            created_at=now,
        )
        self._pipelines[pid] = pipeline
        self._name_index[name] = pid
        self._stages[name] = []
        self._dependencies[name] = []
        self._results[name] = {}
        self._total_created += 1
        self._record_event(name, "pipeline_created", {"pipeline_id": pid})
        self._fire("pipeline_created", {"pipeline_id": pid, "name": name})
        return pid

    def remove_pipeline(self, name: str) -> bool:
        pid = self._name_index.pop(name, None)
        if not pid:
            return False
        self._pipelines.pop(pid, None)
        # Clean up handler references for this pipeline's stages
        for stage in self._stages.get(name, []):
            key = f"{name}::{stage.stage_name}"
            self._handlers.pop(key, None)
        self._stages.pop(name, None)
        self._dependencies.pop(name, None)
        self._results.pop(name, None)
        self._record_event(name, "pipeline_removed", {"pipeline_id": pid})
        self._fire("pipeline_removed", {"pipeline_id": pid, "name": name})
        return True

    def get_pipeline(self, name: str) -> Optional[Dict[str, Any]]:
        pid = self._name_index.get(name)
        if not pid:
            return None
        p = self._pipelines[pid]
        stages = self._stages.get(name, [])
        deps = self._dependencies.get(name, [])
        return {
            "pipeline_id": p.pipeline_id,
            "name": p.name,
            "tags": list(p.tags),
            "stage_count": len(stages),
            "dependency_count": len(deps),
            "execution_count": p.execution_count,
            "last_execution_time": p.last_execution_time,
            "created_at": p.created_at,
        }

    def list_pipelines(self, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for p in self._pipelines.values():
            if tag and tag not in p.tags:
                continue
            results.append(self.get_pipeline(p.name))
        return results

    # ------------------------------------------------------------------
    # Stage management
    # ------------------------------------------------------------------

    def add_stage(
        self,
        pipeline_name: str,
        stage_name: str,
        handler: Optional[Callable] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not pipeline_name or not stage_name:
            return ""
        if pipeline_name not in self._name_index:
            return ""

        # Check for duplicate stage name
        for s in self._stages.get(pipeline_name, []):
            if s.stage_name == stage_name:
                return ""

        self._seq += 1
        now = time.time()
        raw = f"{pipeline_name}-{stage_name}-{now}-{self._seq}"
        sid = "ost-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        stage = _Stage(
            stage_id=sid,
            pipeline_name=pipeline_name,
            stage_name=stage_name,
            tags=tags or [],
            created_at=now,
        )
        self._stages[pipeline_name].append(stage)

        if handler is not None:
            self._handlers[f"{pipeline_name}::{stage_name}"] = handler

        self._total_stages_added += 1
        self._record_event(pipeline_name, "stage_added", {
            "stage_id": sid, "stage_name": stage_name,
        })
        self._fire("stage_added", {
            "pipeline_name": pipeline_name, "stage_id": sid,
            "stage_name": stage_name,
        })
        return sid

    def get_stage(self, pipeline_name: str, stage_name: str) -> Optional[Dict[str, Any]]:
        stages = self._stages.get(pipeline_name)
        if stages is None:
            return None
        for s in stages:
            if s.stage_name == stage_name:
                key = f"{pipeline_name}::{stage_name}"
                has_handler = key in self._handlers
                # Collect dependencies for this stage
                deps_on = [
                    d.depends_on for d in self._dependencies.get(pipeline_name, [])
                    if d.stage_name == stage_name
                ]
                dependents = [
                    d.stage_name for d in self._dependencies.get(pipeline_name, [])
                    if d.depends_on == stage_name
                ]
                return {
                    "stage_id": s.stage_id,
                    "pipeline_name": s.pipeline_name,
                    "stage_name": s.stage_name,
                    "has_handler": has_handler,
                    "tags": list(s.tags),
                    "depends_on": deps_on,
                    "dependents": dependents,
                    "created_at": s.created_at,
                }
        return None

    def list_stages(self, pipeline_name: str) -> List[Dict[str, Any]]:
        stages = self._stages.get(pipeline_name)
        if stages is None:
            return []
        results = []
        for s in stages:
            info = self.get_stage(pipeline_name, s.stage_name)
            if info:
                results.append(info)
        return results

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def add_dependency(self, pipeline_name: str, stage_name: str, depends_on: str) -> bool:
        if pipeline_name not in self._name_index:
            return False

        stages = self._stages.get(pipeline_name, [])
        stage_names = {s.stage_name for s in stages}

        if stage_name not in stage_names or depends_on not in stage_names:
            return False
        if stage_name == depends_on:
            return False

        # Check for duplicate dependency
        for d in self._dependencies.get(pipeline_name, []):
            if d.stage_name == stage_name and d.depends_on == depends_on:
                return False

        # Check that adding this dependency would not create a cycle
        if self._would_create_cycle(pipeline_name, stage_name, depends_on):
            return False

        self._seq += 1
        now = time.time()
        raw = f"{pipeline_name}-{stage_name}-{depends_on}-{now}-{self._seq}"
        did = "odp-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        dep = _StageDependency(
            dep_id=did,
            pipeline_name=pipeline_name,
            stage_name=stage_name,
            depends_on=depends_on,
            created_at=now,
        )
        self._dependencies[pipeline_name].append(dep)
        self._record_event(pipeline_name, "dependency_added", {
            "stage_name": stage_name, "depends_on": depends_on,
        })
        self._fire("dependency_added", {
            "pipeline_name": pipeline_name,
            "stage_name": stage_name, "depends_on": depends_on,
        })
        return True

    def _would_create_cycle(self, pipeline_name: str, stage_name: str, depends_on: str) -> bool:
        """Check if adding stage_name -> depends_on would create a cycle."""
        # Build adjacency: stage -> list of stages it depends on
        adj: Dict[str, List[str]] = {}
        for d in self._dependencies.get(pipeline_name, []):
            adj.setdefault(d.stage_name, []).append(d.depends_on)

        # Add the proposed edge
        adj.setdefault(stage_name, []).append(depends_on)

        # DFS from depends_on following reverse direction won't help;
        # instead check if stage_name is reachable from depends_on
        # following the dependency edges (depends_on -> its deps -> ...)
        # Actually: if depends_on transitively depends on stage_name, cycle.
        visited: set = set()
        stack = [depends_on]
        while stack:
            current = stack.pop()
            if current == stage_name:
                return True
            if current in visited:
                continue
            visited.add(current)
            for dep in adj.get(current, []):
                stack.append(dep)
        return False

    # ------------------------------------------------------------------
    # Execution order (Kahn's algorithm)
    # ------------------------------------------------------------------

    def get_execution_order(self, pipeline_name: str) -> List[List[str]]:
        """Return waves of stage names using Kahn's topological sort.

        Each wave is a list of stages that can execute in parallel (no
        dependencies between them within the same wave).
        """
        stages = self._stages.get(pipeline_name)
        if stages is None:
            return []

        stage_names = [s.stage_name for s in stages]
        if not stage_names:
            return []

        # Build in-degree map and adjacency (depends_on -> dependents)
        in_degree: Dict[str, int] = {name: 0 for name in stage_names}
        dependents: Dict[str, List[str]] = {name: [] for name in stage_names}

        for d in self._dependencies.get(pipeline_name, []):
            if d.stage_name in in_degree and d.depends_on in in_degree:
                in_degree[d.stage_name] += 1
                dependents[d.depends_on].append(d.stage_name)

        waves: List[List[str]] = []
        queue = [name for name in stage_names if in_degree[name] == 0]
        queue.sort()  # deterministic order

        processed = 0
        while queue:
            waves.append(list(queue))
            next_queue: List[str] = []
            for name in queue:
                processed += 1
                for dep in dependents[name]:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        next_queue.append(dep)
            next_queue.sort()
            queue = next_queue

        # If not all stages processed, there is a cycle (should not happen
        # if add_dependency cycle check works, but guard anyway)
        if processed < len(stage_names):
            return []

        return waves

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    def execute(self, pipeline_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute pipeline stages in topological order.

        Returns {success, stages_completed, results: {stage: result}, duration}.
        """
        pid = self._name_index.get(pipeline_name)
        if not pid:
            return {"success": False, "error": "pipeline_not_found", "stages_completed": 0}

        waves = self.get_execution_order(pipeline_name)
        if not waves:
            return {"success": False, "error": "no_stages_or_cycle", "stages_completed": 0}

        pipeline = self._pipelines[pid]
        ctx = dict(context or {})
        ctx["_pipeline"] = pipeline_name
        ctx["_started_at"] = time.time()

        pipeline_start = time.time()
        stages_completed = 0
        stage_results: Dict[str, Any] = {}

        self._fire("pipeline_started", {
            "pipeline": pipeline_name, "waves": len(waves),
        })

        for wave in waves:
            for stage_name in wave:
                key = f"{pipeline_name}::{stage_name}"
                handler = self._handlers.get(key)

                stage_start = time.time()
                if handler is None:
                    # No handler: treat as pass-through success
                    stage_duration = time.time() - stage_start
                    stages_completed += 1
                    self._total_stage_executions += 1
                    stage_results[stage_name] = None
                    self._store_stage_result(
                        pipeline_name, stage_name, True, None, "", stage_duration,
                    )
                    continue

                try:
                    result = handler(ctx)
                    stage_duration = time.time() - stage_start
                    stages_completed += 1
                    self._total_stage_executions += 1
                    stage_results[stage_name] = result

                    # If handler returns a dict, merge into context
                    if isinstance(result, dict):
                        ctx.update(result)

                    self._store_stage_result(
                        pipeline_name, stage_name, True, result, "", stage_duration,
                    )
                    self._record_event(pipeline_name, "stage_completed", {
                        "stage_name": stage_name, "duration": stage_duration,
                    })
                    self._fire("stage_completed", {
                        "pipeline": pipeline_name, "stage": stage_name,
                        "duration": stage_duration,
                    })
                except Exception as exc:
                    stage_duration = time.time() - stage_start
                    pipeline_duration = time.time() - pipeline_start
                    self._total_failures += 1
                    stage_results[stage_name] = None

                    self._store_stage_result(
                        pipeline_name, stage_name, False, None, str(exc), stage_duration,
                    )
                    self._record_event(pipeline_name, "stage_failed", {
                        "stage_name": stage_name, "error": str(exc),
                    })
                    self._fire("pipeline_failed", {
                        "pipeline": pipeline_name, "stage": stage_name,
                        "error": str(exc), "stages_completed": stages_completed,
                    })

                    pipeline.execution_count += 1
                    pipeline.last_execution_time = pipeline_duration
                    self._total_executions += 1

                    return {
                        "success": False,
                        "stages_completed": stages_completed,
                        "failed_stage": stage_name,
                        "error": str(exc),
                        "results": stage_results,
                        "duration": pipeline_duration,
                    }

        pipeline_duration = time.time() - pipeline_start
        pipeline.execution_count += 1
        pipeline.last_execution_time = pipeline_duration
        self._total_executions += 1

        self._record_event(pipeline_name, "pipeline_completed", {
            "stages_completed": stages_completed, "duration": pipeline_duration,
        })
        self._fire("pipeline_completed", {
            "pipeline": pipeline_name, "stages_completed": stages_completed,
            "duration": pipeline_duration,
        })

        return {
            "success": True,
            "stages_completed": stages_completed,
            "results": stage_results,
            "duration": pipeline_duration,
        }

    def _store_stage_result(
        self,
        pipeline_name: str,
        stage_name: str,
        success: bool,
        result: Any,
        error: str,
        duration: float,
    ) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{pipeline_name}-{stage_name}-result-{now}-{self._seq}"
        rid = "osr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        sr = _StageResult(
            result_id=rid,
            pipeline_name=pipeline_name,
            stage_name=stage_name,
            success=success,
            result=result,
            error=error,
            duration=duration,
            timestamp=now,
        )
        if pipeline_name not in self._results:
            self._results[pipeline_name] = {}
        self._results[pipeline_name][stage_name] = sr

    def get_stage_results(self, pipeline_name: str) -> Dict[str, Any]:
        """Return last execution results per stage for a pipeline."""
        results_map = self._results.get(pipeline_name)
        if not results_map:
            return {}
        out: Dict[str, Any] = {}
        for stage_name, sr in results_map.items():
            out[stage_name] = {
                "result_id": sr.result_id,
                "success": sr.success,
                "result": sr.result,
                "error": sr.error,
                "duration": sr.duration,
                "timestamp": sr.timestamp,
            }
        return out

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        pipeline_name: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if pipeline_name and ev.pipeline_name != pipeline_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "pipeline_name": ev.pipeline_name,
                "action": ev.action,
                "data": dict(ev.data),
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, pipeline_name: str, action: str, data: Dict[str, Any]) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{pipeline_name}-{action}-{now}-{self._seq}"
        evid = "oev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _OrchestratorEvent(
            event_id=evid, pipeline_name=pipeline_name,
            action=action, data=data, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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
            "total_pipelines": len(self._pipelines),
            "total_created": self._total_created,
            "total_stages_added": self._total_stages_added,
            "total_executions": self._total_executions,
            "total_stage_executions": self._total_stage_executions,
            "total_failures": self._total_failures,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._pipelines.clear()
        self._name_index.clear()
        self._stages.clear()
        self._handlers.clear()
        self._dependencies.clear()
        self._results.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_stages_added = 0
        self._total_executions = 0
        self._total_stage_executions = 0
        self._total_failures = 0
