"""Agent Strategy Planner – plans multi-step strategies for agents.

Manages strategy creation with goals, steps, dependencies, and execution tracking.
Each strategy has ordered steps that can be executed, skipped, or failed.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Strategy:
    strategy_id: str
    name: str
    agent: str
    goals: List[str]
    status: str  # draft, active, executing, completed, failed, cancelled
    steps: List[str]  # ordered step_ids
    tags: List[str]
    created_at: float
    updated_at: float
    metadata: Dict[str, Any]


@dataclass
class _Step:
    step_id: str
    strategy_id: str
    name: str
    description: str
    status: str  # pending, running, completed, skipped, failed
    order: int
    depends_on: List[str]  # step_ids
    result: str
    started_at: float
    completed_at: float
    created_at: float


class AgentStrategyPlanner:
    """Plans and tracks multi-step agent strategies."""

    STRATEGY_STATUSES = ("draft", "active", "executing", "completed", "failed", "cancelled")
    STEP_STATUSES = ("pending", "running", "completed", "skipped", "failed")

    def __init__(self, max_strategies: int = 50000, max_steps: int = 500000):
        self._strategies: Dict[str, _Strategy] = {}
        self._steps: Dict[str, _Step] = {}
        self._name_index: Dict[str, str] = {}  # name -> strategy_id
        self._callbacks: Dict[str, Callable] = {}
        self._max_strategies = max_strategies
        self._max_steps = max_steps
        self._seq = 0

        # stats
        self._total_strategies = 0
        self._total_steps = 0
        self._total_completed = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def create_strategy(
        self,
        name: str,
        agent: str = "",
        goals: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._strategies) >= self._max_strategies:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        sid = "str-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        s = _Strategy(
            strategy_id=sid,
            name=name,
            agent=agent,
            goals=goals or [],
            status="draft",
            steps=[],
            tags=tags or [],
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        self._strategies[sid] = s
        self._name_index[name] = sid
        self._total_strategies += 1
        self._fire("strategy_created", {"strategy_id": sid, "name": name})
        return sid

    def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        s = self._strategies.get(strategy_id)
        if not s:
            return None
        return {
            "strategy_id": s.strategy_id,
            "name": s.name,
            "agent": s.agent,
            "goals": list(s.goals),
            "status": s.status,
            "steps": list(s.steps),
            "tags": list(s.tags),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "metadata": dict(s.metadata),
        }

    def get_strategy_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        sid = self._name_index.get(name)
        if not sid:
            return None
        return self.get_strategy(sid)

    def remove_strategy(self, strategy_id: str) -> bool:
        s = self._strategies.pop(strategy_id, None)
        if not s:
            return False
        self._name_index.pop(s.name, None)
        # cascade remove steps
        for step_id in list(s.steps):
            self._steps.pop(step_id, None)
        self._fire("strategy_removed", {"strategy_id": strategy_id})
        return True

    def activate_strategy(self, strategy_id: str) -> bool:
        s = self._strategies.get(strategy_id)
        if not s or s.status != "draft":
            return False
        s.status = "active"
        s.updated_at = time.time()
        self._fire("strategy_activated", {"strategy_id": strategy_id})
        return True

    def cancel_strategy(self, strategy_id: str) -> bool:
        s = self._strategies.get(strategy_id)
        if not s or s.status in ("completed", "cancelled"):
            return False
        s.status = "cancelled"
        s.updated_at = time.time()
        self._fire("strategy_cancelled", {"strategy_id": strategy_id})
        return True

    def list_strategies(
        self,
        agent: str = "",
        status: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for s in self._strategies.values():
            if agent and s.agent != agent:
                continue
            if status and s.status != status:
                continue
            if tag and tag not in s.tags:
                continue
            results.append(self.get_strategy(s.strategy_id))
        return results

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def add_step(
        self,
        strategy_id: str,
        name: str,
        description: str = "",
        depends_on: Optional[List[str]] = None,
    ) -> str:
        s = self._strategies.get(strategy_id)
        if not s:
            return ""
        if not name:
            return ""
        if len(self._steps) >= self._max_steps:
            return ""
        # validate dependencies exist
        deps = depends_on or []
        for dep in deps:
            if dep not in self._steps:
                return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{strategy_id}-{now}-{self._seq}"
        step_id = "stp-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        order = len(s.steps)
        step = _Step(
            step_id=step_id,
            strategy_id=strategy_id,
            name=name,
            description=description,
            status="pending",
            order=order,
            depends_on=deps,
            result="",
            started_at=0.0,
            completed_at=0.0,
            created_at=now,
        )
        self._steps[step_id] = step
        s.steps.append(step_id)
        s.updated_at = now
        self._total_steps += 1
        self._fire("step_added", {"step_id": step_id, "strategy_id": strategy_id})
        return step_id

    def get_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        step = self._steps.get(step_id)
        if not step:
            return None
        return {
            "step_id": step.step_id,
            "strategy_id": step.strategy_id,
            "name": step.name,
            "description": step.description,
            "status": step.status,
            "order": step.order,
            "depends_on": list(step.depends_on),
            "result": step.result,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
            "created_at": step.created_at,
        }

    def start_step(self, step_id: str) -> bool:
        step = self._steps.get(step_id)
        if not step or step.status != "pending":
            return False
        # check dependencies completed
        for dep_id in step.depends_on:
            dep = self._steps.get(dep_id)
            if not dep or dep.status not in ("completed", "skipped"):
                return False
        step.status = "running"
        step.started_at = time.time()
        # update strategy to executing
        s = self._strategies.get(step.strategy_id)
        if s and s.status in ("active", "draft"):
            s.status = "executing"
            s.updated_at = time.time()
        self._fire("step_started", {"step_id": step_id})
        return True

    def complete_step(self, step_id: str, result: str = "") -> bool:
        step = self._steps.get(step_id)
        if not step or step.status != "running":
            return False
        step.status = "completed"
        step.result = result
        step.completed_at = time.time()
        self._check_strategy_completion(step.strategy_id)
        self._fire("step_completed", {"step_id": step_id})
        return True

    def fail_step(self, step_id: str, result: str = "") -> bool:
        step = self._steps.get(step_id)
        if not step or step.status != "running":
            return False
        step.status = "failed"
        step.result = result
        step.completed_at = time.time()
        # mark strategy as failed
        s = self._strategies.get(step.strategy_id)
        if s and s.status == "executing":
            s.status = "failed"
            s.updated_at = time.time()
            self._total_failed += 1
        self._fire("step_failed", {"step_id": step_id})
        return True

    def skip_step(self, step_id: str) -> bool:
        step = self._steps.get(step_id)
        if not step or step.status != "pending":
            return False
        step.status = "skipped"
        step.completed_at = time.time()
        self._check_strategy_completion(step.strategy_id)
        self._fire("step_skipped", {"step_id": step_id})
        return True

    def get_strategy_steps(self, strategy_id: str) -> List[Dict[str, Any]]:
        s = self._strategies.get(strategy_id)
        if not s:
            return []
        results = []
        for step_id in s.steps:
            step = self.get_step(step_id)
            if step:
                results.append(step)
        return results

    def get_next_steps(self, strategy_id: str) -> List[Dict[str, Any]]:
        """Get steps that are ready to execute (pending with all deps met)."""
        s = self._strategies.get(strategy_id)
        if not s:
            return []
        ready = []
        for step_id in s.steps:
            step = self._steps.get(step_id)
            if not step or step.status != "pending":
                continue
            deps_met = all(
                self._steps.get(d) and self._steps[d].status in ("completed", "skipped")
                for d in step.depends_on
            )
            if deps_met:
                ready.append(self.get_step(step_id))
        return ready

    def _check_strategy_completion(self, strategy_id: str) -> None:
        s = self._strategies.get(strategy_id)
        if not s or s.status not in ("executing", "active"):
            return
        all_done = all(
            self._steps.get(sid) and self._steps[sid].status in ("completed", "skipped")
            for sid in s.steps
        )
        if all_done and s.steps:
            s.status = "completed"
            s.updated_at = time.time()
            self._total_completed += 1
            self._fire("strategy_completed", {"strategy_id": strategy_id})

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
            "current_strategies": len(self._strategies),
            "current_steps": len(self._steps),
            "total_strategies": self._total_strategies,
            "total_steps": self._total_steps,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
        }

    def reset(self) -> None:
        self._strategies.clear()
        self._steps.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_strategies = 0
        self._total_steps = 0
        self._total_completed = 0
        self._total_failed = 0
