"""
Workflow Engine — Multi-step agent workflow orchestration.

Provides:
- Declarative workflow definitions with steps and transitions
- Sequential, parallel, and conditional execution
- Step dependencies and DAG-based ordering
- Workflow instance tracking with state
- Step retry and failure handling
- Event emission at each lifecycle point
- Workflow templates and reuse

Usage:
    engine = WorkflowEngine(event_bus=event_bus)

    # Define a workflow
    wf_id = engine.define_workflow("build-deploy", steps=[
        {"name": "lint", "agent_type": "linter"},
        {"name": "test", "agent_type": "tester", "depends_on": ["lint"]},
        {"name": "build", "agent_type": "builder", "depends_on": ["test"]},
        {"name": "deploy", "agent_type": "deployer", "depends_on": ["build"]},
    ])

    # Start an instance
    inst_id = engine.start_workflow("build-deploy", context={"project": "myapp"})

    # Advance steps
    engine.complete_step(inst_id, "lint", result={"passed": True})
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"       # Dependencies met, can be executed
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(str, Enum):
    DEFINED = "defined"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class StepDefinition:
    """Definition of a workflow step."""
    name: str
    agent_type: str = "general"
    depends_on: List[str] = field(default_factory=list)
    timeout_seconds: float = 300.0
    max_retries: int = 0
    condition: str = ""  # Optional condition expression
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StepInstance:
    """Runtime instance of a workflow step."""
    name: str
    agent_type: str
    status: StepStatus = StepStatus.PENDING
    depends_on: List[str] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Any = None
    error: str = ""
    retries: int = 0
    max_retries: int = 0
    assigned_to: str = ""

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "agent_type": self.agent_type,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "duration_ms": round(self.duration_ms, 1) if self.duration_ms else None,
            "result": self.result,
            "error": self.error,
            "retries": self.retries,
            "assigned_to": self.assigned_to,
        }


@dataclass
class WorkflowDefinition:
    """Definition of a reusable workflow template."""
    workflow_id: str
    name: str
    steps: List[StepDefinition] = field(default_factory=list)
    description: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowInstance:
    """Runtime instance of a workflow."""
    instance_id: str
    workflow_id: str
    workflow_name: str
    status: WorkflowStatus = WorkflowStatus.RUNNING
    steps: Dict[str, StepInstance] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: str = ""

    @property
    def duration_ms(self) -> Optional[float]:
        if self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(
            1 for s in self.steps.values()
            if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
        )
        return completed / len(self.steps) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status.value,
            "progress": round(self.progress, 1),
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "context": self.context,
            "duration_ms": round(self.duration_ms, 1) if self.duration_ms else None,
            "error": self.error,
        }


class WorkflowEngine:
    """Orchestrates multi-step agent workflows."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus

        # Workflow definitions (templates)
        self._definitions: Dict[str, WorkflowDefinition] = {}

        # Running instances
        self._instances: Dict[str, WorkflowInstance] = {}

        # Callbacks
        self._on_step_complete: Dict[str, List[Callable]] = {}
        self._on_workflow_complete: List[Callable] = []

        # Stats
        self._total_defined = 0
        self._total_started = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_steps_completed = 0

    # ── Workflow Definition ────────────────────────────────────────────

    def define_workflow(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Define a reusable workflow template."""
        workflow_id = f"wf-{uuid.uuid4().hex[:8]}"

        step_defs = []
        for s in steps:
            step_defs.append(StepDefinition(
                name=s["name"],
                agent_type=s.get("agent_type", "general"),
                depends_on=s.get("depends_on", []),
                timeout_seconds=s.get("timeout_seconds", 300.0),
                max_retries=s.get("max_retries", 0),
                condition=s.get("condition", ""),
                metadata=s.get("metadata", {}),
            ))

        definition = WorkflowDefinition(
            workflow_id=workflow_id,
            name=name,
            steps=step_defs,
            description=description,
            metadata=metadata or {},
        )

        self._definitions[name] = definition
        self._total_defined += 1

        logger.info(
            "workflow_defined",
            component="workflow_engine",
            name=name,
            workflow_id=workflow_id,
            step_count=len(step_defs),
        )

        return workflow_id

    def get_definition(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a workflow definition."""
        defn = self._definitions.get(name)
        if not defn:
            return None
        return {
            "workflow_id": defn.workflow_id,
            "name": defn.name,
            "description": defn.description,
            "steps": [
                {
                    "name": s.name,
                    "agent_type": s.agent_type,
                    "depends_on": s.depends_on,
                }
                for s in defn.steps
            ],
        }

    def list_definitions(self) -> List[Dict[str, Any]]:
        """List all workflow definitions."""
        return [
            {
                "name": d.name,
                "workflow_id": d.workflow_id,
                "step_count": len(d.steps),
                "description": d.description,
            }
            for d in self._definitions.values()
        ]

    # ── Workflow Execution ─────────────────────────────────────────────

    def start_workflow(
        self,
        name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Start a new workflow instance from a definition."""
        defn = self._definitions.get(name)
        if not defn:
            logger.warning(
                "workflow_not_found",
                component="workflow_engine",
                name=name,
            )
            return None

        instance_id = f"wfi-{uuid.uuid4().hex[:8]}"

        # Create step instances
        steps = {}
        for step_def in defn.steps:
            steps[step_def.name] = StepInstance(
                name=step_def.name,
                agent_type=step_def.agent_type,
                depends_on=list(step_def.depends_on),
                max_retries=step_def.max_retries,
            )

        instance = WorkflowInstance(
            instance_id=instance_id,
            workflow_id=defn.workflow_id,
            workflow_name=name,
            steps=steps,
            context=context or {},
        )

        # Mark steps with no dependencies as ready
        self._update_ready_steps(instance)

        self._instances[instance_id] = instance
        self._total_started += 1

        logger.info(
            "workflow_started",
            component="workflow_engine",
            instance_id=instance_id,
            workflow=name,
            step_count=len(steps),
        )

        return instance_id

    def get_ready_steps(self, instance_id: str) -> List[Dict[str, Any]]:
        """Get steps that are ready to be executed."""
        inst = self._instances.get(instance_id)
        if not inst:
            return []

        return [
            s.to_dict()
            for s in inst.steps.values()
            if s.status == StepStatus.READY
        ]

    def assign_step(self, instance_id: str, step_name: str, agent_name: str) -> bool:
        """Assign a step to an agent for execution."""
        inst = self._instances.get(instance_id)
        if not inst:
            return False

        step = inst.steps.get(step_name)
        if not step or step.status != StepStatus.READY:
            return False

        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        step.assigned_to = agent_name

        logger.debug(
            "step_assigned",
            component="workflow_engine",
            instance_id=instance_id,
            step=step_name,
            agent=agent_name,
        )
        return True

    def complete_step(
        self,
        instance_id: str,
        step_name: str,
        result: Any = None,
    ) -> bool:
        """Mark a step as completed."""
        inst = self._instances.get(instance_id)
        if not inst:
            return False

        step = inst.steps.get(step_name)
        if not step or step.status not in (StepStatus.RUNNING, StepStatus.READY):
            return False

        step.status = StepStatus.COMPLETED
        step.completed_at = time.time()
        step.result = result
        self._total_steps_completed += 1

        # Store result in workflow context
        inst.context[f"step_result:{step_name}"] = result

        logger.info(
            "step_completed",
            component="workflow_engine",
            instance_id=instance_id,
            step=step_name,
            duration_ms=round(step.duration_ms, 1) if step.duration_ms else 0,
        )

        # Fire step callbacks
        callbacks = self._on_step_complete.get(step_name, [])
        for cb in callbacks:
            try:
                cb(instance_id, step_name, result)
            except Exception:
                pass

        # Update ready steps
        self._update_ready_steps(inst)

        # Check if workflow is complete
        self._check_workflow_completion(inst)

        return True

    def fail_step(
        self,
        instance_id: str,
        step_name: str,
        error: str = "",
    ) -> bool:
        """Mark a step as failed."""
        inst = self._instances.get(instance_id)
        if not inst:
            return False

        step = inst.steps.get(step_name)
        if not step:
            return False

        # Check for retries
        if step.retries < step.max_retries:
            step.retries += 1
            step.status = StepStatus.READY
            step.started_at = None
            step.assigned_to = ""
            logger.info(
                "step_retrying",
                component="workflow_engine",
                instance_id=instance_id,
                step=step_name,
                retry=step.retries,
            )
            return True

        step.status = StepStatus.FAILED
        step.completed_at = time.time()
        step.error = error

        logger.warning(
            "step_failed",
            component="workflow_engine",
            instance_id=instance_id,
            step=step_name,
            error=error,
        )

        # Fail the workflow
        inst.status = WorkflowStatus.FAILED
        inst.completed_at = time.time()
        inst.error = f"Step '{step_name}' failed: {error}"
        self._total_failed += 1

        return True

    def skip_step(self, instance_id: str, step_name: str) -> bool:
        """Skip a step."""
        inst = self._instances.get(instance_id)
        if not inst:
            return False

        step = inst.steps.get(step_name)
        if not step or step.status not in (StepStatus.PENDING, StepStatus.READY):
            return False

        step.status = StepStatus.SKIPPED
        step.completed_at = time.time()

        self._update_ready_steps(inst)
        self._check_workflow_completion(inst)
        return True

    # ── Workflow Control ──────────────────────────────────────────────

    def pause_workflow(self, instance_id: str) -> bool:
        """Pause a running workflow."""
        inst = self._instances.get(instance_id)
        if not inst or inst.status != WorkflowStatus.RUNNING:
            return False
        inst.status = WorkflowStatus.PAUSED
        return True

    def resume_workflow(self, instance_id: str) -> bool:
        """Resume a paused workflow."""
        inst = self._instances.get(instance_id)
        if not inst or inst.status != WorkflowStatus.PAUSED:
            return False
        inst.status = WorkflowStatus.RUNNING
        self._update_ready_steps(inst)
        return True

    def cancel_workflow(self, instance_id: str) -> bool:
        """Cancel a workflow."""
        inst = self._instances.get(instance_id)
        if not inst or inst.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED):
            return False
        inst.status = WorkflowStatus.CANCELLED
        inst.completed_at = time.time()
        return True

    # ── Queries ───────────────────────────────────────────────────────

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow instance details."""
        inst = self._instances.get(instance_id)
        return inst.to_dict() if inst else None

    def list_instances(
        self,
        status: Optional[str] = None,
        workflow_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List workflow instances."""
        results = list(self._instances.values())

        if status:
            results = [i for i in results if i.status.value == status]
        if workflow_name:
            results = [i for i in results if i.workflow_name == workflow_name]

        results.sort(key=lambda i: -i.started_at)
        return [i.to_dict() for i in results[:limit]]

    def get_step(self, instance_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific step's details."""
        inst = self._instances.get(instance_id)
        if not inst:
            return None
        step = inst.steps.get(step_name)
        return step.to_dict() if step else None

    # ── Callbacks ─────────────────────────────────────────────────────

    def on_step_complete(self, step_name: str, callback: Callable):
        """Register callback for when a specific step completes."""
        if step_name not in self._on_step_complete:
            self._on_step_complete[step_name] = []
        self._on_step_complete[step_name].append(callback)

    def on_workflow_complete(self, callback: Callable):
        """Register callback for workflow completion."""
        self._on_workflow_complete.append(callback)

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get workflow engine statistics."""
        status_counts = {}
        for inst in self._instances.values():
            s = inst.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total_defined": self._total_defined,
            "total_started": self._total_started,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_steps_completed": self._total_steps_completed,
            "active_instances": sum(
                1 for i in self._instances.values()
                if i.status == WorkflowStatus.RUNNING
            ),
            "status_counts": status_counts,
            "definitions": len(self._definitions),
        }

    def reset(self):
        """Reset all state."""
        self._definitions.clear()
        self._instances.clear()
        self._on_step_complete.clear()
        self._on_workflow_complete.clear()
        self._total_defined = 0
        self._total_started = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_steps_completed = 0

    # ── Internal ──────────────────────────────────────────────────────

    def _update_ready_steps(self, inst: WorkflowInstance):
        """Update step statuses based on dependency completion."""
        if inst.status != WorkflowStatus.RUNNING:
            return

        completed_steps = {
            name for name, step in inst.steps.items()
            if step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
        }

        for name, step in inst.steps.items():
            if step.status == StepStatus.PENDING:
                deps_met = all(dep in completed_steps for dep in step.depends_on)
                if deps_met:
                    step.status = StepStatus.READY

    def _check_workflow_completion(self, inst: WorkflowInstance):
        """Check if all steps are done."""
        all_done = all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED)
            for s in inst.steps.values()
        )

        if all_done and inst.status == WorkflowStatus.RUNNING:
            has_failures = any(
                s.status == StepStatus.FAILED for s in inst.steps.values()
            )
            if has_failures:
                inst.status = WorkflowStatus.FAILED
                self._total_failed += 1
            else:
                inst.status = WorkflowStatus.COMPLETED
                self._total_completed += 1

            inst.completed_at = time.time()

            logger.info(
                "workflow_completed",
                component="workflow_engine",
                instance_id=inst.instance_id,
                workflow=inst.workflow_name,
                status=inst.status.value,
                progress=inst.progress,
                duration_ms=round(inst.duration_ms, 1) if inst.duration_ms else 0,
            )

            for cb in self._on_workflow_complete:
                try:
                    cb(inst.instance_id, inst.status.value)
                except Exception:
                    pass
