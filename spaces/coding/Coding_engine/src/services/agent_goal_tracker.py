"""Agent goal tracking and completion.

Manages goals assigned to agents with status tracking, completion rates,
and callback notifications for goal lifecycle events.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class GoalEntry:
    """A tracked agent goal."""
    goal_id: str
    agent_id: str
    description: str
    priority: int
    status: str  # "active", "completed", "failed"
    reason: str
    created_at: float
    completed_at: Optional[float]


class AgentGoalTracker:
    """Tracks goals assigned to agents and their completion status."""

    def __init__(self, max_entries: int = 10000):
        self._goals: Dict[str, GoalEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._max_entries = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"agt-{self._seq}-{id(self)}"
        return "agt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest completed/failed goals when over capacity."""
        if len(self._goals) <= self._max_entries:
            return
        removable = [
            g for g in self._goals.values()
            if g.status in ("completed", "failed")
        ]
        removable.sort(key=lambda g: g.created_at)
        while len(self._goals) > self._max_entries and removable:
            victim = removable.pop(0)
            del self._goals[victim.goal_id]

    # ------------------------------------------------------------------
    # Goal CRUD
    # ------------------------------------------------------------------

    def create_goal(self, agent_id: str, description: str,
                    priority: int = 1) -> str:
        """Create a new goal for an agent.

        Returns the generated goal_id (prefixed with 'agt-').
        """
        if not agent_id or not description:
            return ""
        self._prune()
        goal_id = self._generate_id()
        entry = GoalEntry(
            goal_id=goal_id,
            agent_id=agent_id,
            description=description,
            priority=max(1, priority),
            status="active",
            reason="",
            created_at=time.time(),
            completed_at=None,
        )
        self._goals[goal_id] = entry
        self._fire("goal_created", {
            "goal_id": goal_id,
            "agent_id": agent_id,
            "description": description,
        })
        return goal_id

    def get_goal(self, goal_id: str) -> Optional[Dict[str, Any]]:
        """Return goal info as a dict, or None if not found."""
        entry = self._goals.get(goal_id)
        if entry is None:
            return None
        return {
            "goal_id": entry.goal_id,
            "agent_id": entry.agent_id,
            "description": entry.description,
            "priority": entry.priority,
            "status": entry.status,
            "reason": entry.reason,
            "created_at": entry.created_at,
            "completed_at": entry.completed_at,
        }

    def complete_goal(self, goal_id: str) -> bool:
        """Mark a goal as completed."""
        entry = self._goals.get(goal_id)
        if entry is None or entry.status != "active":
            return False
        entry.status = "completed"
        entry.completed_at = time.time()
        self._fire("goal_completed", {"goal_id": goal_id})
        return True

    def fail_goal(self, goal_id: str, reason: str = "") -> bool:
        """Mark a goal as failed with an optional reason."""
        entry = self._goals.get(goal_id)
        if entry is None or entry.status != "active":
            return False
        entry.status = "failed"
        entry.reason = reason
        entry.completed_at = time.time()
        self._fire("goal_failed", {"goal_id": goal_id, "reason": reason})
        return True

    def remove_goal(self, goal_id: str) -> bool:
        """Remove a goal entirely."""
        if goal_id not in self._goals:
            return False
        del self._goals[goal_id]
        self._fire("goal_removed", {"goal_id": goal_id})
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent_goals(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all goals for a given agent."""
        results = []
        for entry in self._goals.values():
            if entry.agent_id == agent_id:
                results.append({
                    "goal_id": entry.goal_id,
                    "agent_id": entry.agent_id,
                    "description": entry.description,
                    "priority": entry.priority,
                    "status": entry.status,
                    "reason": entry.reason,
                    "created_at": entry.created_at,
                    "completed_at": entry.completed_at,
                })
        results.sort(key=lambda g: (-g["priority"], g["created_at"]))
        return results

    def get_active_goals(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return active (non-completed, non-failed) goals for an agent."""
        return [
            g for g in self.get_agent_goals(agent_id)
            if g["status"] == "active"
        ]

    def get_completion_rate(self, agent_id: str) -> float:
        """Return completion rate for an agent as a float from 0.0 to 1.0.

        Only considers completed and failed goals. Returns 0.0 if no
        goals have been resolved.
        """
        resolved = [
            e for e in self._goals.values()
            if e.agent_id == agent_id and e.status in ("completed", "failed")
        ]
        if not resolved:
            return 0.0
        completed = sum(1 for e in resolved if e.status == "completed")
        return completed / len(resolved)

    def list_agents(self) -> List[str]:
        """Return a list of unique agent IDs that have goals."""
        seen: set[str] = set()
        result: List[str] = []
        for entry in self._goals.values():
            if entry.agent_id not in seen:
                seen.add(entry.agent_id)
                result.append(entry.agent_id)
        return result

    def get_goal_count(self) -> int:
        """Return the total number of tracked goals."""
        return len(self._goals)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics."""
        active = sum(1 for g in self._goals.values() if g.status == "active")
        completed = sum(1 for g in self._goals.values()
                        if g.status == "completed")
        failed = sum(1 for g in self._goals.values() if g.status == "failed")
        return {
            "total_goals": len(self._goals),
            "active": active,
            "completed": completed,
            "failed": failed,
            "unique_agents": len(self.list_agents()),
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all goals, callbacks, and reset sequence counter."""
        self._goals.clear()
        self._callbacks.clear()
        self._seq = 0
