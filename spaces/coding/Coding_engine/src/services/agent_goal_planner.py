"""Agent Goal Planner – hierarchical goal planning for agents.

Supports goal decomposition into sub-goals, dependency tracking between
goals, deadline management, and automatic progress aggregation from
children to parents.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Goal:
    goal_id: str
    name: str
    agent_id: str
    description: str
    priority: int
    deadline: float
    parent_goal: str
    status: str
    progress_pct: float
    reason: str
    tags: List[str]
    created_at: float
    completed_at: float


@dataclass
class _GoalDependency:
    dep_id: str
    goal_name: str
    depends_on: str
    created_at: float


@dataclass
class _GoalEvent:
    event_id: str
    goal_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class AgentGoalPlanner:
    """Hierarchical goal planning with dependencies and progress tracking."""

    def __init__(self, max_goals: int = 5000, max_history: int = 100000):
        self._goals: Dict[str, _Goal] = {}
        self._name_index: Dict[str, str] = {}
        self._dependencies: List[_GoalDependency] = []
        self._history: List[_GoalEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_goals = max_goals
        self._max_history = max_history
        self._seq = 0
        self._total_created = 0
        self._total_completed = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # Goal CRUD
    # ------------------------------------------------------------------

    def create_goal(self, name: str, agent_id: str = "", description: str = "", priority: int = 5, deadline: float = 0.0, parent_goal: str = "", tags: Optional[List[str]] = None) -> str:
        if not name:
            return ""
        if name in self._name_index or len(self._goals) >= self._max_goals:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        gid = "gol-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        if parent_goal and parent_goal not in self._name_index:
            return ""
        goal = _Goal(
            goal_id=gid, name=name, agent_id=agent_id, description=description,
            priority=priority, deadline=deadline, parent_goal=parent_goal,
            status="pending", progress_pct=0.0, reason="",
            tags=tags or [], created_at=now, completed_at=0.0,
        )
        self._goals[gid] = goal
        self._name_index[name] = gid
        self._total_created += 1
        self._record_event(name, "created", {"goal_id": gid, "agent_id": agent_id, "priority": priority})
        self._fire("goal_created", {"goal_id": gid, "name": name, "agent_id": agent_id})
        return gid

    def add_subgoal(self, parent_name: str, child_name: str) -> bool:
        pid = self._name_index.get(parent_name)
        cid = self._name_index.get(child_name)
        if not pid or not cid:
            return False
        child = self._goals[cid]
        if child.parent_goal and child.parent_goal != parent_name:
            return False
        child.parent_goal = parent_name
        self._record_event(child_name, "subgoal_added", {"parent": parent_name})
        self._fire("subgoal_added", {"parent": parent_name, "child": child_name})
        return True

    def add_dependency(self, goal_name: str, depends_on: str) -> bool:
        if goal_name not in self._name_index or depends_on not in self._name_index:
            return False
        if goal_name == depends_on:
            return False
        for dep in self._dependencies:
            if dep.goal_name == goal_name and dep.depends_on == depends_on:
                return False
        self._seq += 1
        now = time.time()
        raw = f"dep-{goal_name}-{depends_on}-{now}-{self._seq}"
        did = "dep-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        self._dependencies.append(_GoalDependency(dep_id=did, goal_name=goal_name, depends_on=depends_on, created_at=now))
        self._record_event(goal_name, "dependency_added", {"depends_on": depends_on})
        self._fire("dependency_added", {"goal": goal_name, "depends_on": depends_on})
        return True

    def start_goal(self, name: str) -> bool:
        gid = self._name_index.get(name)
        if not gid:
            return False
        goal = self._goals[gid]
        if goal.status != "pending":
            return False
        if self._is_blocked(name):
            return False
        goal.status = "active"
        self._record_event(name, "started", {"goal_id": gid})
        self._fire("goal_started", {"name": name, "goal_id": gid})
        return True

    def complete_goal(self, name: str) -> bool:
        gid = self._name_index.get(name)
        if not gid:
            return False
        goal = self._goals[gid]
        if goal.status not in ("pending", "active"):
            return False
        goal.status = "completed"
        goal.progress_pct = 100.0
        goal.completed_at = time.time()
        self._total_completed += 1
        self._record_event(name, "completed", {"goal_id": gid})
        self._fire("goal_completed", {"name": name, "goal_id": gid})
        if goal.parent_goal:
            self._update_parent_progress(goal.parent_goal)
        return True

    def fail_goal(self, name: str, reason: str = "") -> bool:
        gid = self._name_index.get(name)
        if not gid:
            return False
        goal = self._goals[gid]
        if goal.status not in ("pending", "active"):
            return False
        goal.status = "failed"
        goal.reason = reason
        goal.completed_at = time.time()
        self._total_failed += 1
        self._record_event(name, "failed", {"goal_id": gid, "reason": reason})
        self._fire("goal_failed", {"name": name, "goal_id": gid, "reason": reason})
        return True

    def update_progress(self, name: str, progress_pct: float) -> bool:
        gid = self._name_index.get(name)
        if not gid:
            return False
        goal = self._goals[gid]
        if goal.status not in ("pending", "active"):
            return False
        goal.progress_pct = max(0.0, min(100.0, progress_pct))
        self._record_event(name, "progress_updated", {"progress_pct": goal.progress_pct})
        self._fire("progress_updated", {"name": name, "progress_pct": goal.progress_pct})
        if goal.parent_goal:
            self._update_parent_progress(goal.parent_goal)
        return True

    def remove_goal(self, name: str) -> bool:
        gid = self._name_index.pop(name, None)
        if not gid:
            return False
        self._goals.pop(gid, None)
        self._dependencies = [d for d in self._dependencies if d.goal_name != name and d.depends_on != name]
        # Unlink children
        for g in self._goals.values():
            if g.parent_goal == name:
                g.parent_goal = ""
        self._record_event(name, "removed", {"goal_id": gid})
        self._fire("goal_removed", {"name": name, "goal_id": gid})
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_goal(self, name: str) -> Optional[Dict[str, Any]]:
        gid = self._name_index.get(name)
        if not gid:
            return None
        g = self._goals[gid]
        children = [c for c in self._goals.values() if c.parent_goal == name]
        deps = [d for d in self._dependencies if d.goal_name == name]
        return {
            "goal_id": g.goal_id, "name": g.name, "agent_id": g.agent_id,
            "description": g.description, "priority": g.priority, "deadline": g.deadline,
            "parent_goal": g.parent_goal, "status": g.status, "progress_pct": g.progress_pct,
            "reason": g.reason, "tags": list(g.tags), "created_at": g.created_at,
            "completed_at": g.completed_at, "subgoal_count": len(children),
            "dependency_count": len(deps), "is_blocked": self._is_blocked(name),
        }

    def get_goal_tree(self, name: str) -> Dict[str, Any]:
        info = self.get_goal(name)
        if not info:
            return {}
        children = [g for g in self._goals.values() if g.parent_goal == name]
        info["subgoals"] = [self.get_goal_tree(c.name) for c in children]
        return info

    def get_agent_goals(self, agent_id: str, status: str = "") -> List[Dict[str, Any]]:
        results = []
        for g in self._goals.values():
            if g.agent_id != agent_id:
                continue
            if status and g.status != status:
                continue
            results.append(self.get_goal(g.name))
        return [r for r in results if r]

    def get_blocked_goals(self) -> List[Dict[str, Any]]:
        results = []
        for g in self._goals.values():
            if g.status in ("completed", "failed"):
                continue
            if self._is_blocked(g.name):
                info = self.get_goal(g.name)
                if info:
                    results.append(info)
        return results

    def get_ready_goals(self) -> List[Dict[str, Any]]:
        results = []
        for g in self._goals.values():
            if g.status != "pending":
                continue
            if not self._is_blocked(g.name):
                info = self.get_goal(g.name)
                if info:
                    results.append(info)
        return results

    def list_goals(self, agent_id: str = "", status: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for g in self._goals.values():
            if agent_id and g.agent_id != agent_id:
                continue
            if status and g.status != status:
                continue
            if tag and tag not in g.tags:
                continue
            info = self.get_goal(g.name)
            if info:
                results.append(info)
        return results

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50, goal_name: str = "", action: str = "", agent_id: str = "") -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if goal_name and ev.goal_name != goal_name:
                continue
            if action and ev.action != action:
                continue
            if agent_id:
                gid = self._name_index.get(ev.goal_name)
                if gid:
                    g = self._goals.get(gid)
                    if g and g.agent_id != agent_id:
                        continue
                else:
                    continue
            results.append({
                "event_id": ev.event_id, "goal_name": ev.goal_name,
                "action": ev.action, "data": ev.data, "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_blocked(self, goal_name: str) -> bool:
        deps = [d for d in self._dependencies if d.goal_name == goal_name]
        for dep in deps:
            dep_gid = self._name_index.get(dep.depends_on)
            if not dep_gid:
                return True
            dep_goal = self._goals.get(dep_gid)
            if not dep_goal or dep_goal.status != "completed":
                return True
        return False

    def _update_parent_progress(self, parent_name: str) -> None:
        pid = self._name_index.get(parent_name)
        if not pid:
            return
        parent = self._goals[pid]
        children = [g for g in self._goals.values() if g.parent_goal == parent_name]
        if not children:
            return
        avg = sum(c.progress_pct for c in children) / len(children)
        parent.progress_pct = round(avg, 2)

    def _record_event(self, goal_name: str, action: str, data: Dict[str, Any]) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{goal_name}-{action}-{now}-{self._seq}"
        evid = "gev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _GoalEvent(event_id=evid, goal_name=goal_name, action=action, data=data, timestamp=now)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {}
        for g in self._goals.values():
            status_counts[g.status] = status_counts.get(g.status, 0) + 1
        return {
            "current_goals": len(self._goals),
            "total_created": self._total_created,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_dependencies": len(self._dependencies),
            "history_size": len(self._history),
            "status_counts": status_counts,
        }

    def reset(self) -> None:
        self._goals.clear()
        self._name_index.clear()
        self._dependencies.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_completed = 0
        self._total_failed = 0
