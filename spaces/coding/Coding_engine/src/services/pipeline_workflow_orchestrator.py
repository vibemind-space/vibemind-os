"""Pipeline Workflow Orchestrator -- orchestrates multi-step pipeline workflows with step ordering.

Manages workflows composed of ordered steps that execute sequentially.
Each workflow tracks its steps, their completion status, and the current
position in the execution sequence.  Callbacks fire on state changes so
that external systems can react to workflow progress.
"""

from __future__ import annotations

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
class _WorkflowStep:
    step_name: str
    step_order: int
    completed: bool = False


@dataclass
class _WorkflowEntry:
    workflow_id: str
    pipeline_id: str
    name: str
    status: str  # pending, running, complete
    steps: List[_WorkflowStep] = field(default_factory=list)
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class PipelineWorkflowOrchestrator:
    """Orchestrates multi-step pipeline workflows with step ordering."""

    def __init__(self, max_entries: int = 10000):
        self._workflows: Dict[str, _WorkflowEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._max_entries = max_entries

        # stats
        self._total_created = 0
        self._total_started = 0
        self._total_completed = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return "pwo-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._workflows) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._workflows,
            key=lambda wid: self._workflows[wid].created_at,
        )
        while len(self._workflows) > self._max_entries and sorted_ids:
            wid = sorted_ids.pop(0)
            self._workflows.pop(wid, None)
        logger.debug("pruned_workflows", remaining=len(self._workflows))

    # ------------------------------------------------------------------
    # Workflow lifecycle
    # ------------------------------------------------------------------

    def create_workflow(self, pipeline_id: str, name: str = "") -> str:
        """Create a new workflow for *pipeline_id*.  Returns the workflow ID."""
        if not pipeline_id:
            return ""

        self._prune_if_needed()

        wid = self._make_id(pipeline_id)
        now = time.time()
        entry = _WorkflowEntry(
            workflow_id=wid,
            pipeline_id=pipeline_id,
            name=name,
            status="pending",
            steps=[],
            created_at=now,
            seq=self._seq,
        )
        self._workflows[wid] = entry
        self._total_created += 1

        logger.info("workflow_created", workflow_id=wid, pipeline_id=pipeline_id, name=name)
        self._fire("workflow_created", {
            "workflow_id": wid,
            "pipeline_id": pipeline_id,
            "name": name,
        })
        return wid

    def add_step(self, workflow_id: str, step_name: str, step_order: int = 0) -> bool:
        """Add a step to a workflow.  Steps are kept sorted by *step_order*."""
        entry = self._workflows.get(workflow_id)
        if not entry:
            logger.warning("add_step_unknown_workflow", workflow_id=workflow_id)
            return False
        if entry.status != "pending":
            logger.warning(
                "add_step_not_pending",
                workflow_id=workflow_id,
                status=entry.status,
            )
            return False
        if not step_name:
            return False

        entry.steps.append(_WorkflowStep(step_name=step_name, step_order=step_order))
        entry.steps.sort(key=lambda s: s.step_order)

        logger.info(
            "step_added",
            workflow_id=workflow_id,
            step_name=step_name,
            step_order=step_order,
            total_steps=len(entry.steps),
        )
        self._fire("step_added", {
            "workflow_id": workflow_id,
            "step_name": step_name,
            "step_order": step_order,
        })
        return True

    def start_workflow(self, workflow_id: str) -> bool:
        """Transition a workflow from *pending* to *running*."""
        entry = self._workflows.get(workflow_id)
        if not entry:
            logger.warning("start_unknown_workflow", workflow_id=workflow_id)
            return False
        if entry.status != "pending":
            logger.warning(
                "start_not_pending",
                workflow_id=workflow_id,
                status=entry.status,
            )
            return False
        if not entry.steps:
            logger.warning("start_no_steps", workflow_id=workflow_id)
            return False

        entry.status = "running"
        self._total_started += 1

        logger.info("workflow_started", workflow_id=workflow_id, total_steps=len(entry.steps))
        self._fire("workflow_started", {
            "workflow_id": workflow_id,
            "pipeline_id": entry.pipeline_id,
            "total_steps": len(entry.steps),
        })
        return True

    def complete_step(self, workflow_id: str, step_name: str) -> bool:
        """Mark a step as completed.  Auto-completes the workflow when all steps are done."""
        entry = self._workflows.get(workflow_id)
        if not entry:
            logger.warning("complete_step_unknown_workflow", workflow_id=workflow_id)
            return False
        if entry.status != "running":
            logger.warning(
                "complete_step_not_running",
                workflow_id=workflow_id,
                status=entry.status,
            )
            return False

        found = False
        for step in entry.steps:
            if step.step_name == step_name and not step.completed:
                step.completed = True
                found = True
                break

        if not found:
            logger.warning(
                "complete_step_not_found",
                workflow_id=workflow_id,
                step_name=step_name,
            )
            return False

        logger.info(
            "step_completed",
            workflow_id=workflow_id,
            step_name=step_name,
            steps_done=sum(1 for s in entry.steps if s.completed),
            total_steps=len(entry.steps),
        )
        self._fire("step_completed", {
            "workflow_id": workflow_id,
            "step_name": step_name,
        })

        # Check if all steps are now complete
        if all(s.completed for s in entry.steps):
            entry.status = "complete"
            self._total_completed += 1
            logger.info("workflow_completed", workflow_id=workflow_id)
            self._fire("workflow_completed", {
                "workflow_id": workflow_id,
                "pipeline_id": entry.pipeline_id,
            })

        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_current_step(self, workflow_id: str) -> Optional[str]:
        """Return the name of the next incomplete step, or None."""
        entry = self._workflows.get(workflow_id)
        if not entry:
            return None
        for step in entry.steps:
            if not step.completed:
                return step.step_name
        return None

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Return workflow details as a dict, or None if not found."""
        entry = self._workflows.get(workflow_id)
        if not entry:
            return None
        return {
            "workflow_id": entry.workflow_id,
            "pipeline_id": entry.pipeline_id,
            "name": entry.name,
            "status": entry.status,
            "steps": [
                {
                    "step_name": s.step_name,
                    "step_order": s.step_order,
                    "completed": s.completed,
                }
                for s in entry.steps
            ],
            "created_at": entry.created_at,
        }

    def is_workflow_complete(self, workflow_id: str) -> bool:
        """Return True if the workflow exists and has completed."""
        entry = self._workflows.get(workflow_id)
        if not entry:
            return False
        return entry.status == "complete"

    def list_pipelines(self) -> List[str]:
        """Return all unique pipeline IDs with registered workflows."""
        return list({e.pipeline_id for e in self._workflows.values()})

    def get_workflow_count(self) -> int:
        """Return the total number of tracked workflows."""
        return len(self._workflows)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns False if *name* already taken."""
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
            "current_workflows": len(self._workflows),
            "total_created": self._total_created,
            "total_started": self._total_started,
            "total_completed": self._total_completed,
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._workflows.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_started = 0
        self._total_completed = 0
        logger.info("orchestrator_reset")
