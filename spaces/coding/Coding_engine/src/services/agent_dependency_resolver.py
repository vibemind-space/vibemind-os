"""Agent Dependency Resolver – manages task dependencies between agents.

Tracks which tasks depend on other tasks being completed before they can
run.  Provides dependency lookup, resolution checking, and ordering of
tasks based on their dependency state.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _DepEntry:
    dep_id: str = ""
    task_id: str = ""
    depends_on: str = ""
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _State:
    dependencies: Dict[str, _DepEntry] = field(default_factory=dict)
    _seq: int = 0


class AgentDependencyResolver:
    """Manages task dependencies between agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = _State()
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_id(self, label: str) -> str:
        self._state._seq += 1
        raw = f"{label}-{time.time()}-{self._state._seq}"
        return "adr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        while len(self._state.dependencies) > self._max_entries:
            oldest_key = min(
                self._state.dependencies,
                key=lambda k: self._state.dependencies[k].seq,
            )
            del self._state.dependencies[oldest_key]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = cb
        return True

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def add_dependency(self, task_id: str, depends_on: str) -> str:
        """Register that *task_id* depends on *depends_on*. Returns dep ID."""
        if not task_id or not depends_on:
            return ""
        if len(self._state.dependencies) >= self._max_entries:
            self._prune()
        dep_id = self._make_id(task_id)
        entry = _DepEntry(
            dep_id=dep_id,
            task_id=task_id,
            depends_on=depends_on,
            created_at=time.time(),
            seq=self._state._seq,
        )
        self._state.dependencies[dep_id] = entry
        logger.info("dependency_added", dep_id=dep_id, task_id=task_id, depends_on=depends_on)
        self._fire("dependency_added", {"dep_id": dep_id, "task_id": task_id, "depends_on": depends_on})
        return dep_id

    def remove_dependency(self, dep_id: str) -> bool:
        """Remove a dependency by its ID."""
        if dep_id in self._state.dependencies:
            del self._state.dependencies[dep_id]
            self._fire("dependency_removed", {"dep_id": dep_id})
            return True
        return False

    def get_dependencies(self, task_id: str) -> List[str]:
        """Get all tasks that *task_id* depends on."""
        result: List[str] = []
        for entry in self._state.dependencies.values():
            if entry.task_id == task_id:
                result.append(entry.depends_on)
        return sorted(set(result))

    def get_dependents(self, task_id: str) -> List[str]:
        """Get all tasks that depend on *task_id*."""
        result: List[str] = []
        for entry in self._state.dependencies.values():
            if entry.depends_on == task_id:
                result.append(entry.task_id)
        return sorted(set(result))

    def is_resolved(self, task_id: str, completed_tasks: Set[str]) -> bool:
        """Check if all dependencies of *task_id* are in *completed_tasks*.

        If the task has no dependencies, returns ``True``.
        """
        deps = self.get_dependencies(task_id)
        if not deps:
            return True
        return all(d in completed_tasks for d in deps)

    def resolve_order(self, task_ids: List[str], completed_tasks: Set[str] | None = None) -> List[str]:
        """Return tasks from *task_ids* whose dependencies are all resolved."""
        if completed_tasks is None:
            completed_tasks = set()
        return [tid for tid in task_ids if self.is_resolved(tid, completed_tasks)]

    def get_dependency_count(self, task_id: str = "") -> int:
        """Count dependencies.  If *task_id* given, count for that task only."""
        if task_id:
            return len(self.get_dependencies(task_id))
        return len(self._state.dependencies)

    def list_tasks(self) -> List[str]:
        """List all unique task IDs (both dependents and dependencies)."""
        tasks: Set[str] = set()
        for entry in self._state.dependencies.values():
            tasks.add(entry.task_id)
            tasks.add(entry.depends_on)
        return sorted(tasks)

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "dependency_count": len(self._state.dependencies),
            "task_count": len(self.list_tasks()),
            "seq": self._state._seq,
            "max_entries": self._max_entries,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        self._state.dependencies.clear()
        self._state._seq = 0
        self._callbacks.clear()
