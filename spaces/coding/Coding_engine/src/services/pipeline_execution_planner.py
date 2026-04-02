"""Pipeline execution planner.

Plans and schedules pipeline execution steps, managing step ordering,
resource allocation, estimated durations, and execution strategies.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Step:
    """Execution step."""
    step_id: str = ""
    name: str = ""
    action: str = ""
    priority: int = 0
    estimated_duration: float = 0.0
    actual_duration: float = 0.0
    status: str = "pending"  # pending, ready, running, completed, failed, skipped
    dependencies: List[str] = field(default_factory=list)
    assigned_agent: str = ""
    tags: List[str] = field(default_factory=list)
    result: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class _Plan:
    """Execution plan."""
    plan_id: str = ""
    name: str = ""
    description: str = ""
    strategy: str = "sequential"  # sequential, parallel, mixed
    status: str = "draft"  # draft, ready, running, completed, failed, cancelled
    steps: Dict[str, _Step] = field(default_factory=dict)
    step_order: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0


class PipelineExecutionPlanner:
    """Plans and manages pipeline execution."""

    STRATEGIES = ("sequential", "parallel", "mixed")
    PLAN_STATUSES = ("draft", "ready", "running", "completed", "failed", "cancelled")

    def __init__(self, max_plans: int = 5000, max_steps_per_plan: int = 500):
        self._max_plans = max_plans
        self._max_steps = max_steps_per_plan
        self._plans: Dict[str, _Plan] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_plans_created": 0,
            "total_plans_completed": 0,
            "total_plans_failed": 0,
            "total_steps_added": 0,
            "total_steps_completed": 0,
            "total_steps_failed": 0,
        }

    # ------------------------------------------------------------------
    # Plan management
    # ------------------------------------------------------------------

    def create_plan(self, name: str, description: str = "",
                    strategy: str = "sequential",
                    tags: Optional[List[str]] = None) -> str:
        """Create an execution plan."""
        if not name:
            return ""
        if strategy not in self.STRATEGIES:
            return ""
        if len(self._plans) >= self._max_plans:
            return ""

        pid = "plan-" + hashlib.md5(
            f"{name}{time.time()}{len(self._plans)}".encode()
        ).hexdigest()[:12]

        self._plans[pid] = _Plan(
            plan_id=pid,
            name=name,
            description=description,
            strategy=strategy,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_plans_created"] += 1
        self._fire("plan_created", {"plan_id": pid, "name": name})
        return pid

    def get_plan(self, plan_id: str) -> Optional[Dict]:
        """Get plan info."""
        p = self._plans.get(plan_id)
        if not p:
            return None
        return {
            "plan_id": p.plan_id,
            "name": p.name,
            "description": p.description,
            "strategy": p.strategy,
            "status": p.status,
            "step_count": len(p.steps),
            "tags": list(p.tags),
            "created_at": p.created_at,
            "started_at": p.started_at,
            "completed_at": p.completed_at,
        }

    def remove_plan(self, plan_id: str) -> bool:
        """Remove a plan (only if draft or completed/failed/cancelled)."""
        p = self._plans.get(plan_id)
        if not p:
            return False
        if p.status == "running":
            return False
        del self._plans[plan_id]
        return True

    def cancel_plan(self, plan_id: str) -> bool:
        """Cancel a plan."""
        p = self._plans.get(plan_id)
        if not p or p.status in ("completed", "failed", "cancelled"):
            return False
        p.status = "cancelled"
        p.completed_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    def add_step(self, plan_id: str, name: str, action: str = "",
                 priority: int = 0, estimated_duration: float = 0.0,
                 dependencies: Optional[List[str]] = None,
                 tags: Optional[List[str]] = None) -> str:
        """Add a step to a plan."""
        p = self._plans.get(plan_id)
        if not p or p.status not in ("draft",):
            return ""
        if not name:
            return ""
        if len(p.steps) >= self._max_steps:
            return ""

        sid = "step-" + hashlib.md5(
            f"{name}{time.time()}{len(p.steps)}".encode()
        ).hexdigest()[:12]

        p.steps[sid] = _Step(
            step_id=sid,
            name=name,
            action=action,
            priority=priority,
            estimated_duration=estimated_duration,
            dependencies=dependencies or [],
            tags=tags or [],
        )
        p.step_order.append(sid)
        self._stats["total_steps_added"] += 1
        return sid

    def get_step(self, plan_id: str, step_id: str) -> Optional[Dict]:
        """Get step info."""
        p = self._plans.get(plan_id)
        if not p:
            return None
        s = p.steps.get(step_id)
        if not s:
            return None
        return {
            "step_id": s.step_id,
            "name": s.name,
            "action": s.action,
            "priority": s.priority,
            "estimated_duration": s.estimated_duration,
            "actual_duration": s.actual_duration,
            "status": s.status,
            "dependencies": list(s.dependencies),
            "assigned_agent": s.assigned_agent,
            "tags": list(s.tags),
            "result": s.result,
        }

    def remove_step(self, plan_id: str, step_id: str) -> bool:
        """Remove a step (only in draft plans)."""
        p = self._plans.get(plan_id)
        if not p or p.status != "draft":
            return False
        if step_id not in p.steps:
            return False
        del p.steps[step_id]
        if step_id in p.step_order:
            p.step_order.remove(step_id)
        return True

    def assign_step(self, plan_id: str, step_id: str, agent: str) -> bool:
        """Assign a step to an agent."""
        p = self._plans.get(plan_id)
        if not p:
            return False
        s = p.steps.get(step_id)
        if not s or not agent:
            return False
        s.assigned_agent = agent
        return True

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def finalize_plan(self, plan_id: str) -> bool:
        """Mark plan as ready for execution."""
        p = self._plans.get(plan_id)
        if not p or p.status != "draft":
            return False
        if not p.steps:
            return False
        p.status = "ready"
        return True

    def start_plan(self, plan_id: str) -> bool:
        """Start plan execution."""
        p = self._plans.get(plan_id)
        if not p or p.status != "ready":
            return False
        p.status = "running"
        p.started_at = time.time()

        # Mark steps with no dependencies as ready
        for s in p.steps.values():
            if not s.dependencies:
                s.status = "ready"

        self._fire("plan_started", {"plan_id": plan_id})
        return True

    def start_step(self, plan_id: str, step_id: str) -> bool:
        """Start executing a step."""
        p = self._plans.get(plan_id)
        if not p or p.status != "running":
            return False
        s = p.steps.get(step_id)
        if not s or s.status != "ready":
            return False
        s.status = "running"
        s.started_at = time.time()
        return True

    def complete_step(self, plan_id: str, step_id: str,
                      result: str = "") -> bool:
        """Complete a step."""
        p = self._plans.get(plan_id)
        if not p or p.status != "running":
            return False
        s = p.steps.get(step_id)
        if not s or s.status != "running":
            return False

        s.status = "completed"
        s.completed_at = time.time()
        s.actual_duration = s.completed_at - s.started_at
        s.result = result
        self._stats["total_steps_completed"] += 1

        # Unblock dependents
        self._update_ready_steps(p)

        # Check if plan is complete
        if all(st.status in ("completed", "skipped")
               for st in p.steps.values()):
            p.status = "completed"
            p.completed_at = time.time()
            self._stats["total_plans_completed"] += 1
            self._fire("plan_completed", {"plan_id": plan_id})

        return True

    def fail_step(self, plan_id: str, step_id: str,
                  reason: str = "") -> bool:
        """Fail a step."""
        p = self._plans.get(plan_id)
        if not p or p.status != "running":
            return False
        s = p.steps.get(step_id)
        if not s or s.status != "running":
            return False

        s.status = "failed"
        s.completed_at = time.time()
        s.result = reason
        self._stats["total_steps_failed"] += 1

        p.status = "failed"
        p.completed_at = time.time()
        self._stats["total_plans_failed"] += 1
        self._fire("plan_failed", {"plan_id": plan_id, "step_id": step_id})
        return True

    def skip_step(self, plan_id: str, step_id: str) -> bool:
        """Skip a step."""
        p = self._plans.get(plan_id)
        if not p or p.status != "running":
            return False
        s = p.steps.get(step_id)
        if not s or s.status not in ("pending", "ready"):
            return False
        s.status = "skipped"
        self._update_ready_steps(p)

        if all(st.status in ("completed", "skipped")
               for st in p.steps.values()):
            p.status = "completed"
            p.completed_at = time.time()
            self._stats["total_plans_completed"] += 1

        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_ready_steps(self, plan_id: str) -> List[Dict]:
        """Get steps ready to execute."""
        p = self._plans.get(plan_id)
        if not p:
            return []
        result = []
        for s in p.steps.values():
            if s.status == "ready":
                result.append({
                    "step_id": s.step_id,
                    "name": s.name,
                    "priority": s.priority,
                    "assigned_agent": s.assigned_agent,
                })
        result.sort(key=lambda x: -x["priority"])
        return result

    def get_plan_progress(self, plan_id: str) -> Dict:
        """Get plan execution progress."""
        p = self._plans.get(plan_id)
        if not p:
            return {}
        total = len(p.steps)
        completed = sum(1 for s in p.steps.values()
                        if s.status == "completed")
        failed = sum(1 for s in p.steps.values() if s.status == "failed")
        skipped = sum(1 for s in p.steps.values() if s.status == "skipped")
        running = sum(1 for s in p.steps.values() if s.status == "running")
        ready = sum(1 for s in p.steps.values() if s.status == "ready")

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "running": running,
            "ready": ready,
            "pending": total - completed - failed - skipped - running - ready,
            "percent": round(
                (completed + skipped) / total * 100, 1
            ) if total > 0 else 0.0,
        }

    def get_estimated_duration(self, plan_id: str) -> float:
        """Get total estimated duration."""
        p = self._plans.get(plan_id)
        if not p:
            return 0.0
        if p.strategy == "sequential":
            return sum(s.estimated_duration for s in p.steps.values())
        elif p.strategy == "parallel":
            return max(
                (s.estimated_duration for s in p.steps.values()), default=0.0
            )
        else:  # mixed
            return sum(s.estimated_duration for s in p.steps.values()) / 2

    def list_plans(self, status: Optional[str] = None,
                   tag: Optional[str] = None) -> List[Dict]:
        """List plans with optional filters."""
        result = []
        for p in self._plans.values():
            if status and p.status != status:
                continue
            if tag and tag not in p.tags:
                continue
            result.append({
                "plan_id": p.plan_id,
                "name": p.name,
                "strategy": p.strategy,
                "status": p.status,
                "step_count": len(p.steps),
            })
        return result

    def get_plan_steps(self, plan_id: str) -> List[Dict]:
        """Get all steps in order."""
        p = self._plans.get(plan_id)
        if not p:
            return []
        result = []
        for sid in p.step_order:
            s = p.steps.get(sid)
            if s:
                result.append({
                    "step_id": s.step_id,
                    "name": s.name,
                    "status": s.status,
                    "priority": s.priority,
                    "assigned_agent": s.assigned_agent,
                })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_ready_steps(self, plan: _Plan) -> None:
        """Update step statuses based on dependency completion."""
        for s in plan.steps.values():
            if s.status != "pending":
                continue
            if not s.dependencies:
                continue
            all_done = all(
                plan.steps.get(dep, _Step()).status in ("completed", "skipped")
                for dep in s.dependencies
            )
            if all_done:
                s.status = "ready"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_plans": len(self._plans),
            "running_plans": sum(
                1 for p in self._plans.values() if p.status == "running"
            ),
        }

    def reset(self) -> None:
        self._plans.clear()
        self._stats = {k: 0 for k in self._stats}
