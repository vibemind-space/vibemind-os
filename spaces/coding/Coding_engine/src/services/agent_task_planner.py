"""Agent Task Planner – creates and manages execution plans for agents.

Builds multi-step plans from goals, tracks step completion, supports
plan revision, and maintains plan history. Plans decompose complex
goals into ordered steps with dependencies.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _PlanStep:
    step_index: int
    description: str
    status: str  # pending, running, completed, failed, skipped
    depends_on: List[int]  # step indices
    result: Any
    started_at: float
    completed_at: float


@dataclass
class _PlanEntry:
    plan_id: str
    agent: str
    goal: str
    status: str  # draft, active, completed, failed, cancelled
    steps: List[_PlanStep]
    current_step: int
    total_revisions: int
    tags: List[str]
    created_at: float
    updated_at: float


class AgentTaskPlanner:
    """Creates and manages execution plans for agents."""

    STATUSES = ("draft", "active", "completed", "failed", "cancelled")
    STEP_STATUSES = ("pending", "running", "completed", "failed", "skipped")

    def __init__(self, max_plans: int = 10000):
        self._plans: Dict[str, _PlanEntry] = {}
        self._agent_index: Dict[str, List[str]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_plans = max_plans
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_completed = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # Plan creation
    # ------------------------------------------------------------------

    def create_plan(
        self,
        agent: str,
        goal: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not agent or not goal:
            return ""
        if len(self._plans) >= self._max_plans:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{goal}-{now}-{self._seq}"
        pid = "pln-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        plan_steps = []
        if steps:
            for i, s in enumerate(steps):
                plan_steps.append(_PlanStep(
                    step_index=i,
                    description=s.get("description", ""),
                    status="pending",
                    depends_on=s.get("depends_on", []),
                    result=None,
                    started_at=0.0,
                    completed_at=0.0,
                ))

        entry = _PlanEntry(
            plan_id=pid,
            agent=agent,
            goal=goal,
            status="draft",
            steps=plan_steps,
            current_step=0,
            total_revisions=0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._plans[pid] = entry
        self._agent_index.setdefault(agent, []).append(pid)
        self._total_created += 1
        self._fire("plan_created", {"plan_id": pid, "agent": agent, "goal": goal})
        return pid

    def get_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        e = self._plans.get(plan_id)
        if not e:
            return None
        return {
            "plan_id": e.plan_id,
            "agent": e.agent,
            "goal": e.goal,
            "status": e.status,
            "steps": [
                {
                    "step_index": s.step_index,
                    "description": s.description,
                    "status": s.status,
                    "depends_on": list(s.depends_on),
                    "result": s.result,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                }
                for s in e.steps
            ],
            "current_step": e.current_step,
            "total_revisions": e.total_revisions,
            "tags": list(e.tags),
            "created_at": e.created_at,
        }

    def remove_plan(self, plan_id: str) -> bool:
        e = self._plans.pop(plan_id, None)
        if not e:
            return False
        agent_list = self._agent_index.get(e.agent, [])
        if plan_id in agent_list:
            agent_list.remove(plan_id)
        return True

    # ------------------------------------------------------------------
    # Plan lifecycle
    # ------------------------------------------------------------------

    def activate(self, plan_id: str) -> bool:
        """Activate a draft plan."""
        e = self._plans.get(plan_id)
        if not e or e.status != "draft":
            return False
        if not e.steps:
            return False
        e.status = "active"
        e.updated_at = time.time()
        self._fire("plan_activated", {"plan_id": plan_id})
        return True

    def add_step(
        self,
        plan_id: str,
        description: str,
        depends_on: Optional[List[int]] = None,
    ) -> int:
        """Add a step to a draft plan. Returns step index or -1."""
        e = self._plans.get(plan_id)
        if not e or e.status != "draft":
            return -1
        if not description:
            return -1
        idx = len(e.steps)
        step = _PlanStep(
            step_index=idx,
            description=description,
            status="pending",
            depends_on=depends_on or [],
            result=None,
            started_at=0.0,
            completed_at=0.0,
        )
        e.steps.append(step)
        e.updated_at = time.time()
        return idx

    def start_step(self, plan_id: str, step_index: int) -> bool:
        """Start a step."""
        e = self._plans.get(plan_id)
        if not e or e.status != "active":
            return False
        if step_index < 0 or step_index >= len(e.steps):
            return False
        step = e.steps[step_index]
        if step.status != "pending":
            return False
        # check dependencies
        for dep_idx in step.depends_on:
            if dep_idx < 0 or dep_idx >= len(e.steps):
                return False
            if e.steps[dep_idx].status != "completed":
                return False
        step.status = "running"
        step.started_at = time.time()
        e.current_step = step_index
        e.updated_at = time.time()
        self._fire("step_started", {"plan_id": plan_id, "step_index": step_index})
        return True

    def complete_step(self, plan_id: str, step_index: int, result: Any = None) -> bool:
        """Complete a step."""
        e = self._plans.get(plan_id)
        if not e or e.status != "active":
            return False
        if step_index < 0 or step_index >= len(e.steps):
            return False
        step = e.steps[step_index]
        if step.status != "running":
            return False
        step.status = "completed"
        step.result = result
        step.completed_at = time.time()
        e.updated_at = time.time()
        self._fire("step_completed", {"plan_id": plan_id, "step_index": step_index})

        # check if all steps completed
        if all(s.status in ("completed", "skipped") for s in e.steps):
            e.status = "completed"
            self._total_completed += 1
            self._fire("plan_completed", {"plan_id": plan_id})
        return True

    def fail_step(self, plan_id: str, step_index: int, error: str = "") -> bool:
        """Fail a step."""
        e = self._plans.get(plan_id)
        if not e or e.status != "active":
            return False
        if step_index < 0 or step_index >= len(e.steps):
            return False
        step = e.steps[step_index]
        if step.status != "running":
            return False
        step.status = "failed"
        step.result = error
        step.completed_at = time.time()
        e.status = "failed"
        e.updated_at = time.time()
        self._total_failed += 1
        self._fire("step_failed", {"plan_id": plan_id, "step_index": step_index})
        self._fire("plan_failed", {"plan_id": plan_id})
        return True

    def skip_step(self, plan_id: str, step_index: int) -> bool:
        """Skip a pending step."""
        e = self._plans.get(plan_id)
        if not e or e.status != "active":
            return False
        if step_index < 0 or step_index >= len(e.steps):
            return False
        step = e.steps[step_index]
        if step.status != "pending":
            return False
        step.status = "skipped"
        e.updated_at = time.time()
        return True

    def cancel(self, plan_id: str) -> bool:
        """Cancel a plan."""
        e = self._plans.get(plan_id)
        if not e or e.status in ("completed", "cancelled"):
            return False
        e.status = "cancelled"
        e.updated_at = time.time()
        self._fire("plan_cancelled", {"plan_id": plan_id})
        return True

    def get_progress(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Get plan progress."""
        e = self._plans.get(plan_id)
        if not e:
            return None
        total = len(e.steps)
        completed = sum(1 for s in e.steps if s.status == "completed")
        failed = sum(1 for s in e.steps if s.status == "failed")
        skipped = sum(1 for s in e.steps if s.status == "skipped")
        return {
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "pending": total - completed - failed - skipped,
            "pct": (completed / total * 100.0) if total > 0 else 0.0,
        }

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_plans(
        self,
        agent: str = "",
        status: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in self._plans.values():
            if agent and e.agent != agent:
                continue
            if status and e.status != status:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_plan(e.plan_id))
        return results

    def get_plans_for_agent(self, agent: str) -> List[Dict[str, Any]]:
        pids = self._agent_index.get(agent, [])
        results = []
        for pid in pids:
            p = self.get_plan(pid)
            if p:
                results.append(p)
        return results

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
            "current_plans": len(self._plans),
            "total_created": self._total_created,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "active_count": sum(1 for e in self._plans.values() if e.status == "active"),
            "draft_count": sum(1 for e in self._plans.values() if e.status == "draft"),
        }

    def reset(self) -> None:
        self._plans.clear()
        self._agent_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_completed = 0
        self._total_failed = 0
