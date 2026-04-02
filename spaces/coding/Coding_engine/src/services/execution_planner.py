"""
Execution Planner — plans, schedules, and optimizes task execution
across available agents based on dependencies and resource constraints.

Features:
- Plan creation from task lists with dependencies
- Resource-aware scheduling (agent capacity)
- Parallel execution optimization
- Plan versioning and comparison
- Execution timeline estimation
- Constraint validation
- Plan export/visualization
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class PlanStatus(str):
    DRAFT = "draft"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PlanTask:
    """A task within an execution plan."""
    task_id: str
    name: str
    duration_estimate: float = 0.0
    assigned_agent: str = ""
    dependencies: Set[str] = field(default_factory=set)  # task_ids
    status: str = "pending"
    started_at: float = 0.0
    ended_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)


@dataclass
class ExecutionPlan:
    """A complete execution plan."""
    plan_id: str
    name: str
    version: int
    status: str = PlanStatus.DRAFT
    created_at: float = 0.0
    tasks: Dict[str, PlanTask] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSlot:
    """Available agent for scheduling."""
    agent_name: str
    capacity: int = 1  # max concurrent tasks
    current_load: int = 0
    capabilities: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Execution Planner
# ---------------------------------------------------------------------------

class ExecutionPlanner:
    """Plans and optimizes task execution."""

    def __init__(self, max_plans: int = 100):
        self._max_plans = max_plans
        self._plans: Dict[str, ExecutionPlan] = {}
        self._agents: Dict[str, AgentSlot] = {}

        self._stats = {
            "total_plans_created": 0,
            "total_tasks_planned": 0,
            "total_plans_completed": 0,
            "total_plans_failed": 0,
        }

    # ------------------------------------------------------------------
    # Agent slots
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_name: str,
        capacity: int = 1,
        capabilities: Optional[Set[str]] = None,
    ) -> bool:
        """Register an agent for scheduling."""
        if agent_name in self._agents:
            return False
        self._agents[agent_name] = AgentSlot(
            agent_name=agent_name,
            capacity=capacity,
            capabilities=capabilities or set(),
        )
        return True

    def unregister_agent(self, agent_name: str) -> bool:
        """Unregister an agent."""
        if agent_name not in self._agents:
            return False
        del self._agents[agent_name]
        return True

    def list_agents(self) -> List[Dict]:
        """List registered agents."""
        return sorted([{
            "agent_name": a.agent_name,
            "capacity": a.capacity,
            "current_load": a.current_load,
            "available": a.current_load < a.capacity,
            "capabilities": sorted(a.capabilities),
        } for a in self._agents.values()], key=lambda x: x["agent_name"])

    # ------------------------------------------------------------------
    # Plan creation
    # ------------------------------------------------------------------

    def create_plan(
        self,
        name: str,
        constraints: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a new execution plan. Returns plan_id."""
        pid = f"plan-{uuid.uuid4().hex[:8]}"
        version = 1

        # Check for existing plan with same name, bump version
        for p in self._plans.values():
            if p.name == name:
                version = max(version, p.version + 1)

        self._plans[pid] = ExecutionPlan(
            plan_id=pid,
            name=name,
            version=version,
            created_at=time.time(),
            constraints=constraints or {},
            metadata=metadata or {},
        )
        self._stats["total_plans_created"] += 1
        self._prune_plans()
        return pid

    def get_plan(self, plan_id: str) -> Optional[Dict]:
        """Get plan details."""
        p = self._plans.get(plan_id)
        if not p:
            return None
        return self._plan_to_dict(p)

    def list_plans(
        self,
        status: Optional[str] = None,
        name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List plans with filters."""
        results = []
        for p in sorted(self._plans.values(),
                        key=lambda x: x.created_at, reverse=True):
            if status and p.status != status:
                continue
            if name and p.name != name:
                continue
            results.append(self._plan_to_dict(p))
            if len(results) >= limit:
                break
        return results

    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan."""
        if plan_id not in self._plans:
            return False
        del self._plans[plan_id]
        return True

    # ------------------------------------------------------------------
    # Task management within plans
    # ------------------------------------------------------------------

    def add_task(
        self,
        plan_id: str,
        name: str,
        duration_estimate: float = 0.0,
        dependencies: Optional[Set[str]] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """Add a task to a plan. Returns task_id."""
        p = self._plans.get(plan_id)
        if not p or p.status not in (PlanStatus.DRAFT, PlanStatus.READY):
            return None

        tid = f"ptask-{uuid.uuid4().hex[:6]}"
        p.tasks[tid] = PlanTask(
            task_id=tid,
            name=name,
            duration_estimate=duration_estimate,
            dependencies=dependencies or set(),
            tags=tags or set(),
            metadata=metadata or {},
        )
        self._stats["total_tasks_planned"] += 1
        return tid

    def remove_task(self, plan_id: str, task_id: str) -> bool:
        """Remove a task from a plan."""
        p = self._plans.get(plan_id)
        if not p or task_id not in p.tasks:
            return False
        # Remove from other tasks' dependencies
        for t in p.tasks.values():
            t.dependencies.discard(task_id)
        del p.tasks[task_id]
        return True

    def get_task(self, plan_id: str, task_id: str) -> Optional[Dict]:
        """Get task details."""
        p = self._plans.get(plan_id)
        if not p:
            return None
        t = p.tasks.get(task_id)
        if not t:
            return None
        return self._task_to_dict(t)

    # ------------------------------------------------------------------
    # Scheduling & optimization
    # ------------------------------------------------------------------

    def validate_plan(self, plan_id: str) -> Dict:
        """Validate a plan for completeness and correctness."""
        p = self._plans.get(plan_id)
        if not p:
            return {"valid": False, "errors": ["Plan not found"]}

        errors = []
        warnings = []

        if not p.tasks:
            errors.append("Plan has no tasks")

        # Check for missing dependencies
        task_ids = set(p.tasks.keys())
        for t in p.tasks.values():
            for dep in t.dependencies:
                if dep not in task_ids:
                    errors.append(f"Task '{t.name}' depends on missing task '{dep}'")

        # Check for cycles
        if self._has_cycle(p):
            errors.append("Plan has circular dependencies")

        # Check for unassigned tasks
        unassigned = [t.name for t in p.tasks.values() if not t.assigned_agent]
        if unassigned:
            warnings.append(f"{len(unassigned)} tasks have no assigned agent")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "task_count": len(p.tasks),
        }

    def compute_schedule(self, plan_id: str) -> Optional[List[List[Dict]]]:
        """Compute parallel execution groups. Returns layers of tasks."""
        p = self._plans.get(plan_id)
        if not p or self._has_cycle(p):
            return None

        in_degree = {tid: 0 for tid in p.tasks}
        for t in p.tasks.values():
            in_degree[t.task_id] = len(t.dependencies)

        queue = deque(tid for tid, d in in_degree.items() if d == 0)
        layers = []

        while queue:
            layer = []
            next_queue = deque()
            for tid in queue:
                t = p.tasks[tid]
                layer.append(self._task_to_dict(t))
            layers.append(layer)

            for tid in queue:
                for other in p.tasks.values():
                    if tid in other.dependencies:
                        in_degree[other.task_id] -= 1
                        if in_degree[other.task_id] == 0:
                            next_queue.append(other.task_id)
            queue = next_queue

        return layers

    def estimate_duration(self, plan_id: str) -> Optional[Dict]:
        """Estimate total plan duration (critical path)."""
        layers = self.compute_schedule(plan_id)
        if layers is None:
            return None

        total = 0.0
        layer_times = []
        for layer in layers:
            max_dur = max((t["duration_estimate"] for t in layer), default=0)
            layer_times.append(round(max_dur, 2))
            total += max_dur

        return {
            "estimated_total_seconds": round(total, 2),
            "num_layers": len(layers),
            "layer_durations": layer_times,
            "total_tasks": sum(len(l) for l in layers),
        }

    def auto_assign(self, plan_id: str) -> int:
        """Auto-assign tasks to available agents. Returns count assigned."""
        p = self._plans.get(plan_id)
        if not p:
            return 0

        agents = sorted(self._agents.values(),
                        key=lambda a: a.current_load)
        assigned = 0

        for t in p.tasks.values():
            if t.assigned_agent:
                continue
            # Find best agent (least loaded, matching capabilities)
            for agent in agents:
                if agent.current_load < agent.capacity:
                    if t.tags and agent.capabilities:
                        if not t.tags.intersection(agent.capabilities):
                            continue
                    t.assigned_agent = agent.agent_name
                    assigned += 1
                    break

        return assigned

    # ------------------------------------------------------------------
    # Execution tracking
    # ------------------------------------------------------------------

    def start_plan(self, plan_id: str) -> bool:
        """Start executing a plan."""
        p = self._plans.get(plan_id)
        if not p or p.status not in (PlanStatus.DRAFT, PlanStatus.READY):
            return False
        p.status = PlanStatus.EXECUTING
        return True

    def complete_task(self, plan_id: str, task_id: str) -> bool:
        """Mark a task as completed."""
        p = self._plans.get(plan_id)
        if not p:
            return False
        t = p.tasks.get(task_id)
        if not t or t.status != "pending":
            return False
        t.status = "completed"
        t.ended_at = time.time()

        # Check if all tasks done
        if all(tk.status == "completed" for tk in p.tasks.values()):
            p.status = PlanStatus.COMPLETED
            self._stats["total_plans_completed"] += 1

        return True

    def fail_task(self, plan_id: str, task_id: str, error: str = "") -> bool:
        """Mark a task as failed."""
        p = self._plans.get(plan_id)
        if not p:
            return False
        t = p.tasks.get(task_id)
        if not t:
            return False
        t.status = "failed"
        t.ended_at = time.time()
        t.metadata["error"] = error
        p.status = PlanStatus.FAILED
        self._stats["total_plans_failed"] += 1
        return True

    def get_ready_tasks(self, plan_id: str) -> List[Dict]:
        """Get tasks whose dependencies are all completed."""
        p = self._plans.get(plan_id)
        if not p:
            return []

        ready = []
        for t in p.tasks.values():
            if t.status != "pending":
                continue
            deps_met = all(
                p.tasks[d].status == "completed"
                for d in t.dependencies if d in p.tasks
            )
            if deps_met:
                ready.append(self._task_to_dict(t))
        return ready

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _has_cycle(self, plan: ExecutionPlan) -> bool:
        in_degree = {tid: 0 for tid in plan.tasks}
        for t in plan.tasks.values():
            in_degree[t.task_id] = len(
                [d for d in t.dependencies if d in plan.tasks]
            )

        queue = deque(tid for tid, d in in_degree.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for t in plan.tasks.values():
                if node in t.dependencies:
                    in_degree[t.task_id] -= 1
                    if in_degree[t.task_id] == 0:
                        queue.append(t.task_id)

        return visited != len(plan.tasks)

    def _plan_to_dict(self, p: ExecutionPlan) -> Dict:
        task_statuses = defaultdict(int)
        for t in p.tasks.values():
            task_statuses[t.status] += 1

        return {
            "plan_id": p.plan_id,
            "name": p.name,
            "version": p.version,
            "status": p.status,
            "created_at": p.created_at,
            "task_count": len(p.tasks),
            "task_statuses": dict(task_statuses),
            "constraints": p.constraints,
            "metadata": p.metadata,
        }

    def _task_to_dict(self, t: PlanTask) -> Dict:
        return {
            "task_id": t.task_id,
            "name": t.name,
            "duration_estimate": t.duration_estimate,
            "assigned_agent": t.assigned_agent,
            "dependencies": sorted(t.dependencies),
            "status": t.status,
            "tags": sorted(t.tags),
            "metadata": t.metadata,
        }

    def _prune_plans(self) -> None:
        if len(self._plans) <= self._max_plans:
            return
        completed = sorted(
            [p for p in self._plans.values()
             if p.status in (PlanStatus.COMPLETED, PlanStatus.FAILED, PlanStatus.CANCELLED)],
            key=lambda x: x.created_at,
        )
        to_remove = len(self._plans) - self._max_plans
        for p in completed[:to_remove]:
            del self._plans[p.plan_id]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_plans": len(self._plans),
            "total_agents": len(self._agents),
        }

    def reset(self) -> None:
        self._plans.clear()
        self._agents.clear()
        self._stats = {k: 0 for k in self._stats}
