"""Agent Workflow Engine -- manages multi-step workflows for agents.

Provides workflow creation with ordered steps, sequential execution with
context passing, execution history tracking, and tag-based filtering.
Each step receives a context dict and returns an updated context dict.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _StepEntry:
    """A single workflow step."""
    step_id: str
    step_name: str
    handler_fn: Callable[[Dict[str, Any]], Dict[str, Any]]
    order: int
    created_at: float


@dataclass
class _WorkflowEntry:
    """A workflow definition."""
    workflow_id: str
    name: str
    description: str
    tags: List[str]
    steps: List[_StepEntry]
    created_at: float
    updated_at: float


@dataclass
class _ExecutionRecord:
    """A single workflow execution result."""
    execution_id: str
    workflow_id: str
    workflow_name: str
    success: bool
    steps_completed: int
    total_steps: int
    context: Dict[str, Any]
    error: str
    started_at: float
    finished_at: float
    step_details: List[Dict[str, Any]]


class AgentWorkflowEngine:
    """Manages multi-step workflows for agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._workflows: Dict[str, _WorkflowEntry] = {}
        self._name_index: Dict[str, str] = {}
        self._executions: Dict[str, _ExecutionRecord] = {}
        self._workflow_executions: Dict[str, List[str]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._total_workflows_created = 0
        self._total_workflows_removed = 0
        self._total_steps_added = 0
        self._total_executions = 0
        self._total_executions_succeeded = 0
        self._total_executions_failed = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix awe- using SHA256 + seq."""
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return "awe-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Workflow management
    # ------------------------------------------------------------------

    def create_workflow(self, name: str, description: str = "",
                        tags: Optional[List[str]] = None) -> str:
        """Create a new workflow. Returns workflow_id or '' on duplicate/full."""
        if not name:
            return ""
        if name in self._name_index:
            logger.warning("duplicate_workflow_name", name=name)
            return ""
        if len(self._workflows) >= self._max_entries:
            logger.warning("max_workflows_reached", max=self._max_entries)
            return ""

        wid = self._generate_id(f"wf-{name}")
        now = time.time()
        wf = _WorkflowEntry(
            workflow_id=wid, name=name, description=description,
            tags=list(tags or []), steps=[], created_at=now, updated_at=now,
        )
        self._workflows[wid] = wf
        self._name_index[name] = wid
        self._workflow_executions[wid] = []
        self._total_workflows_created += 1
        logger.info("workflow_created", workflow_id=wid, name=name)
        self._fire("workflow_created", {"workflow_id": wid, "name": name})
        return wid

    def add_step(self, workflow_id: str, step_name: str,
                 handler_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
                 order: Optional[int] = None) -> str:
        """Add a step to a workflow. Auto-increments order when None.

        Returns the new step_id, or '' if the workflow does not exist.
        """
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return ""
        if order is None:
            order = len(wf.steps)

        sid = self._generate_id(f"st-{workflow_id}-{step_name}")
        step = _StepEntry(
            step_id=sid, step_name=step_name,
            handler_fn=handler_fn, order=order, created_at=time.time(),
        )
        wf.steps.append(step)
        wf.steps.sort(key=lambda s: s.order)
        wf.updated_at = time.time()
        self._total_steps_added += 1
        logger.info("step_added", workflow_id=workflow_id, step_id=sid)
        self._fire("step_added", {"workflow_id": workflow_id, "step_id": sid})
        return sid

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Return a workflow as a plain dict, or None if not found."""
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return None
        return self._wf_to_dict(wf)

    def list_workflows(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all workflows, optionally filtering by tag."""
        results: List[Dict[str, Any]] = []
        for wf in self._workflows.values():
            if tag and tag not in wf.tags:
                continue
            results.append(self._wf_to_dict(wf))
        results.sort(key=lambda w: w["created_at"])
        return results

    def remove_workflow(self, workflow_id: str) -> bool:
        """Remove a workflow and its execution history. Returns True on success."""
        wf = self._workflows.pop(workflow_id, None)
        if wf is None:
            return False
        self._name_index.pop(wf.name, None)
        exec_ids = self._workflow_executions.pop(workflow_id, [])
        for eid in exec_ids:
            self._executions.pop(eid, None)
        self._total_workflows_removed += 1
        logger.info("workflow_removed", workflow_id=workflow_id, name=wf.name)
        self._fire("workflow_removed", {"workflow_id": workflow_id, "name": wf.name})
        return True

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_workflow(self, workflow_id: str,
                         context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute all steps in order, passing context through each.

        Each handler_fn takes a ctx dict and returns a ctx dict.
        If a step fails, execution stops and success=False is returned.

        Returns dict with: success, steps_completed, context, error,
        execution_id.
        """
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"success": False, "steps_completed": 0,
                    "context": {}, "error": "workflow_not_found"}
        if not wf.steps:
            return {"success": False, "steps_completed": 0,
                    "context": {}, "error": "no_steps"}

        ctx = dict(context or {})
        started_at = time.time()
        steps_completed = 0
        step_details: List[Dict[str, Any]] = []
        error_msg = ""
        eid = self._generate_id(f"ex-{workflow_id}")
        self._total_executions += 1

        logger.info("execution_started", workflow_id=workflow_id, execution_id=eid)
        self._fire("execution_started", {"workflow_id": workflow_id, "execution_id": eid})

        for step in wf.steps:
            step_start = time.time()
            try:
                ctx = step.handler_fn(ctx)
                steps_completed += 1
                step_details.append({
                    "step_id": step.step_id, "step_name": step.step_name,
                    "order": step.order, "success": True,
                    "duration": round(time.time() - step_start, 6), "error": "",
                })
            except Exception as exc:
                error_msg = f"Step '{step.step_name}' failed: {exc}"
                step_details.append({
                    "step_id": step.step_id, "step_name": step.step_name,
                    "order": step.order, "success": False,
                    "duration": round(time.time() - step_start, 6),
                    "error": str(exc),
                })
                logger.error("step_failed", workflow_id=workflow_id,
                             step_name=step.step_name, error=str(exc))
                break

        finished_at = time.time()
        success = error_msg == ""
        if success:
            self._total_executions_succeeded += 1
        else:
            self._total_executions_failed += 1

        record = _ExecutionRecord(
            execution_id=eid, workflow_id=workflow_id,
            workflow_name=wf.name, success=success,
            steps_completed=steps_completed, total_steps=len(wf.steps),
            context=dict(ctx), error=error_msg,
            started_at=started_at, finished_at=finished_at,
            step_details=step_details,
        )
        self._executions[eid] = record
        if workflow_id in self._workflow_executions:
            self._workflow_executions[workflow_id].append(eid)

        if len(self._executions) > self._max_entries:
            self._prune_executions()

        logger.info("execution_finished", execution_id=eid, success=success,
                     steps_completed=steps_completed)
        self._fire("execution_finished", {
            "workflow_id": workflow_id, "execution_id": eid, "success": success,
        })
        return {
            "success": success, "steps_completed": steps_completed,
            "context": dict(ctx), "error": error_msg, "execution_id": eid,
        }

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Return an execution record as a plain dict, or None."""
        rec = self._executions.get(execution_id)
        if rec is None:
            return None
        return self._exec_to_dict(rec)

    def get_workflow_history(self, workflow_id: str) -> List[Dict[str, Any]]:
        """Return execution history for a workflow, newest first."""
        exec_ids = self._workflow_executions.get(workflow_id, [])
        results: List[Dict[str, Any]] = []
        for eid in exec_ids:
            rec = self._executions.get(eid)
            if rec is not None:
                results.append(self._exec_to_dict(rec))
        results.sort(key=lambda r: r["started_at"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics as a plain dict."""
        return {
            "total_workflows_created": self._total_workflows_created,
            "total_workflows_removed": self._total_workflows_removed,
            "total_steps_added": self._total_steps_added,
            "total_executions": self._total_executions,
            "total_executions_succeeded": self._total_executions_succeeded,
            "total_executions_failed": self._total_executions_failed,
            "current_workflows": len(self._workflows),
            "current_executions": len(self._executions),
        }

    def reset(self) -> None:
        """Clear all internal state and counters."""
        self._workflows.clear()
        self._name_index.clear()
        self._executions.clear()
        self._workflow_executions.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_workflows_created = 0
        self._total_workflows_removed = 0
        self._total_steps_added = 0
        self._total_executions = 0
        self._total_executions_succeeded = 0
        self._total_executions_failed = 0
        logger.info("agent_workflow_engine_reset")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wf_to_dict(wf: _WorkflowEntry) -> Dict[str, Any]:
        """Convert a workflow entry to a plain dict."""
        return {
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description,
            "tags": list(wf.tags),
            "steps": [
                {"step_id": s.step_id, "step_name": s.step_name,
                 "order": s.order, "created_at": s.created_at}
                for s in wf.steps
            ],
            "created_at": wf.created_at,
            "updated_at": wf.updated_at,
        }

    @staticmethod
    def _exec_to_dict(rec: _ExecutionRecord) -> Dict[str, Any]:
        """Convert an execution record to a plain dict."""
        return {
            "execution_id": rec.execution_id,
            "workflow_id": rec.workflow_id,
            "workflow_name": rec.workflow_name,
            "success": rec.success,
            "steps_completed": rec.steps_completed,
            "total_steps": rec.total_steps,
            "context": dict(rec.context),
            "error": rec.error,
            "started_at": rec.started_at,
            "finished_at": rec.finished_at,
            "duration": round(rec.finished_at - rec.started_at, 6),
            "step_details": list(rec.step_details),
        }

    def _prune_executions(self) -> None:
        """Remove oldest execution records when over the limit."""
        if len(self._executions) <= self._max_entries:
            return
        sorted_execs = sorted(self._executions.values(), key=lambda r: r.started_at)
        to_remove = len(self._executions) - self._max_entries
        for rec in sorted_execs[:to_remove]:
            self._executions.pop(rec.execution_id, None)
            wf_execs = self._workflow_executions.get(rec.workflow_id, [])
            if rec.execution_id in wf_execs:
                wf_execs.remove(rec.execution_id)
