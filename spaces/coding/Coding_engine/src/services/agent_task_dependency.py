"""Agent Task Dependency -- manages dependencies between agent tasks.

Tracks which tasks depend on other tasks and determines execution order.

Provides:
- Task registration with optional dependency lists
- Dynamic dependency addition and removal
- Circular dependency detection via DFS
- Ready-task resolution (all deps completed)
- Callback-based change notifications
- Max-entries pruning to bound memory usage

Usage::

    dep = AgentTaskDependency()

    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "test", depends_on=[t1])
    t3 = dep.register_task("agent-1", "deploy", depends_on=[t2])

    dep.complete_task(t1)
    ready = dep.get_ready_tasks("agent-1")  # [t2 info]
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# -------------------------------------------------------------------
# Internal state
# -------------------------------------------------------------------

@dataclass
class AgentTaskDependencyState:
    """Mutable state container for AgentTaskDependency."""

    entries: dict = field(default_factory=dict)
    _seq: int = 0


# -------------------------------------------------------------------
# AgentTaskDependency
# -------------------------------------------------------------------

class AgentTaskDependency:
    """Manages dependencies between agent tasks."""

    PREFIX = "atd-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskDependencyState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # -- id generation ------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + digest[:16]

    # -- pruning ------------------------------------------------------

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(entries, key=lambda k: entries[k]["created_at"])
        excess = len(entries) - self.MAX_ENTRIES
        for tid in sorted_ids[:excess]:
            del entries[tid]

    # -- event firing -------------------------------------------------

    def _fire(self, event: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback error", event=event)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("callback error", name=name, event=event)

    # -- on_change property -------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    # -- callback management ------------------------------------------

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- core methods -------------------------------------------------

    def register_task(
        self,
        agent_id: str,
        task_name: str,
        depends_on: Optional[List[str]] = None,
    ) -> str:
        """Register a task with optional dependencies (list of task_ids)."""
        task_id = self._generate_id(f"{agent_id}:{task_name}")
        self._state.entries[task_id] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "depends_on": list(depends_on) if depends_on else [],
            "status": "pending",
            "created_at": time.time(),
        }
        self._prune()
        self._fire("task_registered", {"task_id": task_id, "agent_id": agent_id})
        return task_id

    def add_dependency(self, task_id: str, depends_on_id: str) -> bool:
        """Add a dependency to a task. Return False if task not found."""
        entry = self._state.entries.get(task_id)
        if entry is None:
            return False
        if depends_on_id not in entry["depends_on"]:
            entry["depends_on"].append(depends_on_id)
        self._fire("dependency_added", {"task_id": task_id, "depends_on_id": depends_on_id})
        return True

    def remove_dependency(self, task_id: str, depends_on_id: str) -> bool:
        """Remove a dependency from a task."""
        entry = self._state.entries.get(task_id)
        if entry is None:
            return False
        if depends_on_id in entry["depends_on"]:
            entry["depends_on"].remove(depends_on_id)
            self._fire("dependency_removed", {"task_id": task_id, "depends_on_id": depends_on_id})
            return True
        return False

    def get_task(self, task_id: str) -> Optional[dict]:
        """Return task info or None."""
        entry = self._state.entries.get(task_id)
        if entry is None:
            return None
        return dict(entry)

    def get_tasks(self, agent_id: str) -> List[dict]:
        """List tasks for an agent."""
        return [
            dict(e) for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        ]

    def get_ready_tasks(self, agent_id: str) -> List[dict]:
        """Return pending tasks whose all dependencies have status 'completed'."""
        entries = self._state.entries
        result: List[dict] = []
        for e in entries.values():
            if e["agent_id"] != agent_id:
                continue
            if e["status"] != "pending":
                continue
            all_done = True
            for dep_id in e["depends_on"]:
                dep = entries.get(dep_id)
                if dep is None or dep["status"] != "completed":
                    all_done = False
                    break
            if all_done:
                result.append(dict(e))
        return result

    def complete_task(self, task_id: str) -> bool:
        """Mark task as completed."""
        entry = self._state.entries.get(task_id)
        if entry is None:
            return False
        entry["status"] = "completed"
        self._fire("task_completed", {"task_id": task_id})
        return True

    def get_dependents(self, task_id: str) -> List[dict]:
        """Get tasks that depend on this task."""
        return [
            dict(e) for e in self._state.entries.values()
            if task_id in e["depends_on"]
        ]

    def get_dependencies(self, task_id: str) -> List[dict]:
        """Get tasks this task depends on."""
        entry = self._state.entries.get(task_id)
        if entry is None:
            return []
        result: List[dict] = []
        for dep_id in entry["depends_on"]:
            dep = self._state.entries.get(dep_id)
            if dep is not None:
                result.append(dict(dep))
        return result

    def has_circular_dependency(self, task_id: str) -> bool:
        """Check for circular dependencies using DFS."""
        visited: Set[str] = set()
        stack: Set[str] = set()

        def _dfs(tid: str) -> bool:
            if tid in stack:
                return True
            if tid in visited:
                return False
            visited.add(tid)
            stack.add(tid)
            entry = self._state.entries.get(tid)
            if entry is not None:
                for dep_id in entry["depends_on"]:
                    if _dfs(dep_id):
                        return True
            stack.discard(tid)
            return False

        return _dfs(task_id)

    def get_task_count(self, agent_id: str = "") -> int:
        """Count tasks, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        entries = self._state.entries
        total = len(entries)
        completed = sum(1 for e in entries.values() if e["status"] == "completed")
        pending = sum(1 for e in entries.values() if e["status"] == "pending")
        total_deps = sum(len(e["depends_on"]) for e in entries.values())
        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "pending_tasks": pending,
            "total_dependencies": total_deps,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskDependencyState()
        self._fire("reset", {})
