"""Pipeline workflow engine - define and execute multi-step workflows."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WorkflowStep:
    """A step within a workflow."""
    step_id: str = ""
    name: str = ""
    step_type: str = "task"
    status: str = "pending"
    dependencies: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    result: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class Workflow:
    """A workflow definition."""
    workflow_id: str = ""
    name: str = ""
    steps: dict = field(default_factory=dict)
    step_order: list = field(default_factory=list)
    status: str = "draft"
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0


class PipelineWorkflowEngine:
    """Define and execute multi-step workflows."""

    STEP_TYPES = ("task", "gate", "parallel", "conditional", "loop", "notify", "custom")
    STEP_STATUSES = ("pending", "running", "completed", "failed", "skipped", "blocked")
    WORKFLOW_STATUSES = ("draft", "ready", "running", "completed", "failed", "cancelled")

    def __init__(self, max_workflows: int = 5000, max_steps_per_workflow: int = 200):
        self._max_workflows = max(1, max_workflows)
        self._max_steps = max(1, max_steps_per_workflow)
        self._workflows: Dict[str, Workflow] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_workflows": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_steps_executed": 0,
        }

    # --- Workflow Management ---

    def create_workflow(
        self,
        name: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a new workflow."""
        if not name:
            return ""
        if len(self._workflows) >= self._max_workflows:
            return ""

        wid = f"wf-{uuid.uuid4().hex[:12]}"
        self._workflows[wid] = Workflow(
            workflow_id=wid,
            name=name,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            created_at=time.time(),
        )
        self._stats["total_workflows"] += 1
        return wid

    def get_workflow(self, workflow_id: str) -> Optional[Dict]:
        """Get workflow details."""
        w = self._workflows.get(workflow_id)
        if not w:
            return None
        return {
            "workflow_id": w.workflow_id,
            "name": w.name,
            "status": w.status,
            "step_count": len(w.steps),
            "tags": list(w.tags),
            "created_at": w.created_at,
        }

    def remove_workflow(self, workflow_id: str) -> bool:
        """Remove a workflow."""
        if workflow_id not in self._workflows:
            return False
        del self._workflows[workflow_id]
        return True

    # --- Step Management ---

    def add_step(
        self,
        workflow_id: str,
        name: str,
        step_type: str = "task",
        dependencies: Optional[List[str]] = None,
        config: Optional[Dict] = None,
    ) -> str:
        """Add a step to a workflow."""
        w = self._workflows.get(workflow_id)
        if not w or not name:
            return ""
        if w.status != "draft":
            return ""
        if step_type not in self.STEP_TYPES:
            return ""
        if len(w.steps) >= self._max_steps:
            return ""

        # Validate dependencies
        deps = list(dependencies or [])
        for dep in deps:
            if dep not in w.steps:
                return ""

        sid = f"step-{uuid.uuid4().hex[:12]}"
        w.steps[sid] = WorkflowStep(
            step_id=sid,
            name=name,
            step_type=step_type,
            dependencies=deps,
            config=dict(config or {}),
        )
        w.step_order.append(sid)
        return sid

    def get_step(self, workflow_id: str, step_id: str) -> Optional[Dict]:
        """Get step details."""
        w = self._workflows.get(workflow_id)
        if not w:
            return None
        s = w.steps.get(step_id)
        if not s:
            return None
        return {
            "step_id": s.step_id,
            "name": s.name,
            "step_type": s.step_type,
            "status": s.status,
            "dependencies": list(s.dependencies),
            "result": s.result,
        }

    def remove_step(self, workflow_id: str, step_id: str) -> bool:
        """Remove a step from a draft workflow."""
        w = self._workflows.get(workflow_id)
        if not w or w.status != "draft":
            return False
        if step_id not in w.steps:
            return False
        # Check no other steps depend on this
        for s in w.steps.values():
            if step_id in s.dependencies:
                return False
        del w.steps[step_id]
        w.step_order.remove(step_id)
        return True

    def get_steps(self, workflow_id: str) -> List[Dict]:
        """Get all steps in order."""
        w = self._workflows.get(workflow_id)
        if not w:
            return []
        results = []
        for sid in w.step_order:
            s = w.steps[sid]
            results.append({
                "step_id": s.step_id,
                "name": s.name,
                "step_type": s.step_type,
                "status": s.status,
            })
        return results

    # --- Execution ---

    def start_workflow(self, workflow_id: str) -> bool:
        """Start executing a workflow."""
        w = self._workflows.get(workflow_id)
        if not w or w.status not in ("draft", "ready"):
            return False
        if len(w.steps) == 0:
            return False

        w.status = "running"
        w.started_at = time.time()

        # Set initial step statuses
        for s in w.steps.values():
            if s.dependencies:
                s.status = "blocked"
            else:
                s.status = "pending"

        self._fire("workflow_started", {"workflow_id": workflow_id})
        return True

    def complete_step(self, workflow_id: str, step_id: str, result: str = "") -> bool:
        """Mark a step as completed."""
        w = self._workflows.get(workflow_id)
        if not w or w.status != "running":
            return False
        s = w.steps.get(step_id)
        if not s or s.status not in ("pending", "running"):
            return False

        s.status = "completed"
        s.result = result
        s.completed_at = time.time()
        self._stats["total_steps_executed"] += 1

        # Unblock dependent steps
        for other in w.steps.values():
            if step_id in other.dependencies and other.status == "blocked":
                all_done = all(
                    w.steps[dep].status == "completed"
                    for dep in other.dependencies
                )
                if all_done:
                    other.status = "pending"

        # Check if workflow is complete
        all_complete = all(
            s.status in ("completed", "skipped")
            for s in w.steps.values()
        )
        if all_complete:
            w.status = "completed"
            w.completed_at = time.time()
            self._stats["total_completed"] += 1
            self._fire("workflow_completed", {"workflow_id": workflow_id})

        return True

    def fail_step(self, workflow_id: str, step_id: str, reason: str = "") -> bool:
        """Mark a step as failed."""
        w = self._workflows.get(workflow_id)
        if not w or w.status != "running":
            return False
        s = w.steps.get(step_id)
        if not s or s.status not in ("pending", "running"):
            return False

        s.status = "failed"
        s.result = reason
        w.status = "failed"
        self._stats["total_failed"] += 1
        self._fire("workflow_failed", {"workflow_id": workflow_id, "step_id": step_id})
        return True

    def skip_step(self, workflow_id: str, step_id: str) -> bool:
        """Skip a pending step."""
        w = self._workflows.get(workflow_id)
        if not w or w.status != "running":
            return False
        s = w.steps.get(step_id)
        if not s or s.status != "pending":
            return False
        s.status = "skipped"
        return True

    def start_step(self, workflow_id: str, step_id: str) -> bool:
        """Mark a step as running."""
        w = self._workflows.get(workflow_id)
        if not w or w.status != "running":
            return False
        s = w.steps.get(step_id)
        if not s or s.status != "pending":
            return False
        s.status = "running"
        s.started_at = time.time()
        return True

    def get_next_steps(self, workflow_id: str) -> List[Dict]:
        """Get steps that are ready to execute (pending, no blocked deps)."""
        w = self._workflows.get(workflow_id)
        if not w or w.status != "running":
            return []
        return [
            {"step_id": s.step_id, "name": s.name, "step_type": s.step_type}
            for s in w.steps.values()
            if s.status == "pending"
        ]

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a workflow."""
        w = self._workflows.get(workflow_id)
        if not w or w.status in ("completed", "cancelled"):
            return False
        w.status = "cancelled"
        return True

    # --- Queries ---

    def list_workflows(self, status: str = "", tag: str = "") -> List[Dict]:
        """List workflows with filters."""
        results = []
        for w in self._workflows.values():
            if status and w.status != status:
                continue
            if tag and tag not in w.tags:
                continue
            results.append({
                "workflow_id": w.workflow_id,
                "name": w.name,
                "status": w.status,
                "step_count": len(w.steps),
            })
        return results

    def get_workflow_progress(self, workflow_id: str) -> Dict:
        """Get progress percentage of a workflow."""
        w = self._workflows.get(workflow_id)
        if not w or len(w.steps) == 0:
            return {}
        done = sum(1 for s in w.steps.values() if s.status in ("completed", "skipped"))
        return {
            "workflow_id": workflow_id,
            "total_steps": len(w.steps),
            "completed_steps": done,
            "progress": round(done / len(w.steps), 4),
        }

    # --- Callbacks ---

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # --- Stats ---

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_workflows": len(self._workflows),
            "running_workflows": sum(1 for w in self._workflows.values() if w.status == "running"),
        }

    def reset(self) -> None:
        self._workflows.clear()
        self._callbacks.clear()
        self._stats = {
            "total_workflows": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_steps_executed": 0,
        }

    # --- Internal ---

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
