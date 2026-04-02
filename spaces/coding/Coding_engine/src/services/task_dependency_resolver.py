"""
Task Dependency Resolver — manages task dependencies, topological ordering, and execution readiness.

Features:
- DAG-based task dependency tracking
- Topological sort for execution order
- Circular dependency detection
- Ready-task identification (all deps satisfied)
- Dependency chain analysis
- Batch resolution for parallel execution groups
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TaskNode:
    """A task in the dependency graph."""
    task_id: str
    name: str
    status: str  # "pending", "ready", "running", "completed", "failed", "skipped"
    dependencies: Set[str]  # task_ids this depends on
    dependents: Set[str]  # task_ids that depend on this
    category: str
    priority: int
    metadata: Dict[str, Any]
    created_at: float
    completed_at: float = 0.0


# ---------------------------------------------------------------------------
# Task Dependency Resolver
# ---------------------------------------------------------------------------

class TaskDependencyResolver:
    """Manages task dependencies, ordering, and readiness detection."""

    def __init__(self, max_tasks: int = 10000):
        self._max_tasks = max_tasks
        self._tasks: Dict[str, TaskNode] = {}

        self._stats = {
            "total_added": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "total_cycle_checks": 0,
        }

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def add_task(
        self,
        name: str,
        dependencies: Optional[List[str]] = None,
        category: str = "general",
        priority: int = 50,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Add a task. Returns task_id."""
        task_id = f"td-{uuid.uuid4().hex[:8]}"
        deps = set(dependencies or [])

        # Validate dependencies exist
        for dep in deps:
            if dep not in self._tasks:
                return ""

        node = TaskNode(
            task_id=task_id,
            name=name,
            status="pending",
            dependencies=deps,
            dependents=set(),
            category=category,
            priority=priority,
            metadata=metadata or {},
            created_at=time.time(),
        )

        # Check for cycles before adding
        if deps and self._would_create_cycle(task_id, deps):
            return ""

        self._tasks[task_id] = node

        # Register as dependent in upstream tasks
        for dep in deps:
            if dep in self._tasks:
                self._tasks[dep].dependents.add(task_id)

        # Auto-mark ready if no deps
        if not deps:
            node.status = "ready"

        self._stats["total_added"] += 1

        # Prune if over limit
        if len(self._tasks) > self._max_tasks:
            self._prune()

        return task_id

    def remove_task(self, task_id: str) -> bool:
        """Remove a task. Fails if other tasks depend on it."""
        node = self._tasks.get(task_id)
        if not node:
            return False

        # Can't remove if others depend on this
        if node.dependents:
            return False

        # Remove from upstream dependency lists
        for dep in node.dependencies:
            if dep in self._tasks:
                self._tasks[dep].dependents.discard(task_id)

        del self._tasks[task_id]
        return True

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task info."""
        node = self._tasks.get(task_id)
        if not node:
            return None
        return self._node_to_dict(node)

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def complete_task(self, task_id: str) -> bool:
        """Mark task as completed. Updates downstream readiness."""
        node = self._tasks.get(task_id)
        if not node or node.status not in ("ready", "running"):
            return False

        node.status = "completed"
        node.completed_at = time.time()
        self._stats["total_completed"] += 1

        # Check if dependents become ready
        for dep_id in node.dependents:
            self._check_ready(dep_id)

        return True

    def fail_task(self, task_id: str) -> bool:
        """Mark task as failed."""
        node = self._tasks.get(task_id)
        if not node or node.status not in ("ready", "running"):
            return False

        node.status = "failed"
        self._stats["total_failed"] += 1
        return True

    def skip_task(self, task_id: str) -> bool:
        """Skip a task. Treats as completed for dependency purposes."""
        node = self._tasks.get(task_id)
        if not node or node.status in ("completed", "failed"):
            return False

        node.status = "skipped"
        node.completed_at = time.time()
        self._stats["total_skipped"] += 1

        # Treat as completed for downstream
        for dep_id in node.dependents:
            self._check_ready(dep_id)

        return True

    def start_task(self, task_id: str) -> bool:
        """Mark task as running."""
        node = self._tasks.get(task_id)
        if not node or node.status != "ready":
            return False

        node.status = "running"
        return True

    def reset_task(self, task_id: str) -> bool:
        """Reset a failed/completed task back to pending/ready."""
        node = self._tasks.get(task_id)
        if not node or node.status not in ("failed", "completed", "skipped"):
            return False

        node.completed_at = 0.0
        # Check if deps are satisfied
        if self._all_deps_satisfied(task_id):
            node.status = "ready"
        else:
            node.status = "pending"
        return True

    # ------------------------------------------------------------------
    # Dependency management
    # ------------------------------------------------------------------

    def add_dependency(self, task_id: str, depends_on: str) -> bool:
        """Add a dependency. Returns False on cycle or not found."""
        node = self._tasks.get(task_id)
        dep_node = self._tasks.get(depends_on)
        if not node or not dep_node:
            return False

        if depends_on in node.dependencies:
            return False  # Already exists

        # Check for cycle
        if self._would_create_cycle(task_id, {depends_on}):
            return False

        node.dependencies.add(depends_on)
        dep_node.dependents.add(task_id)

        # Update status
        if node.status == "ready" and dep_node.status not in ("completed", "skipped"):
            node.status = "pending"

        return True

    def remove_dependency(self, task_id: str, depends_on: str) -> bool:
        """Remove a dependency."""
        node = self._tasks.get(task_id)
        if not node or depends_on not in node.dependencies:
            return False

        node.dependencies.discard(depends_on)
        if depends_on in self._tasks:
            self._tasks[depends_on].dependents.discard(task_id)

        self._check_ready(task_id)
        return True

    def get_dependencies(self, task_id: str) -> List[Dict]:
        """Get direct dependencies of a task."""
        node = self._tasks.get(task_id)
        if not node:
            return []
        return [self._node_to_dict(self._tasks[d]) for d in node.dependencies if d in self._tasks]

    def get_dependents(self, task_id: str) -> List[Dict]:
        """Get direct dependents of a task."""
        node = self._tasks.get(task_id)
        if not node:
            return []
        return [self._node_to_dict(self._tasks[d]) for d in node.dependents if d in self._tasks]

    def get_all_dependencies(self, task_id: str) -> List[str]:
        """Get all transitive dependencies (upstream chain)."""
        node = self._tasks.get(task_id)
        if not node:
            return []

        visited: Set[str] = set()
        queue = deque(node.dependencies)
        while queue:
            dep_id = queue.popleft()
            if dep_id in visited:
                continue
            visited.add(dep_id)
            dep_node = self._tasks.get(dep_id)
            if dep_node:
                queue.extend(dep_node.dependencies - visited)
        return list(visited)

    def get_all_dependents(self, task_id: str) -> List[str]:
        """Get all transitive dependents (downstream chain)."""
        node = self._tasks.get(task_id)
        if not node:
            return []

        visited: Set[str] = set()
        queue = deque(node.dependents)
        while queue:
            dep_id = queue.popleft()
            if dep_id in visited:
                continue
            visited.add(dep_id)
            dep_node = self._tasks.get(dep_id)
            if dep_node:
                queue.extend(dep_node.dependents - visited)
        return list(visited)

    # ------------------------------------------------------------------
    # Querying & ordering
    # ------------------------------------------------------------------

    def get_ready_tasks(self, category: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get tasks that are ready to execute (all deps satisfied)."""
        results = []
        for node in sorted(self._tasks.values(), key=lambda n: -n.priority):
            if node.status != "ready":
                continue
            if category and node.category != category:
                continue
            results.append(self._node_to_dict(node))
            if len(results) >= limit:
                break
        return results

    def topological_sort(self) -> Optional[List[str]]:
        """Return topological ordering of all tasks. None if cycle exists."""
        self._stats["total_cycle_checks"] += 1

        in_degree: Dict[str, int] = {}
        for tid, node in self._tasks.items():
            in_degree.setdefault(tid, 0)
            for dep_id in node.dependents:
                in_degree[dep_id] = in_degree.get(dep_id, 0) + 1

        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        result = []

        while queue:
            tid = queue.popleft()
            result.append(tid)
            node = self._tasks.get(tid)
            if node:
                for dep_id in node.dependents:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        queue.append(dep_id)

        if len(result) != len(self._tasks):
            return None  # Cycle detected
        return result

    def get_execution_layers(self) -> List[List[str]]:
        """Get tasks grouped into parallel execution layers.

        Each layer contains tasks that can run in parallel.
        Layer N+1 depends on layer N being complete.
        """
        if not self._tasks:
            return []

        remaining = set(self._tasks.keys())
        completed = {tid for tid, n in self._tasks.items() if n.status in ("completed", "skipped")}
        layers = []

        while remaining:
            layer = []
            for tid in list(remaining):
                node = self._tasks[tid]
                # All deps must be in completed or prior layers
                deps_done = all(
                    d in completed or d not in remaining
                    for d in node.dependencies
                )
                if deps_done:
                    layer.append(tid)

            if not layer:
                break  # Cycle or stuck

            layers.append(sorted(layer, key=lambda t: -self._tasks[t].priority))
            remaining -= set(layer)
            completed |= set(layer)

        return layers

    def has_cycle(self) -> bool:
        """Check if the dependency graph has any cycles."""
        self._stats["total_cycle_checks"] += 1
        return self.topological_sort() is None

    def get_critical_path(self) -> List[str]:
        """Get the longest dependency chain."""
        if not self._tasks:
            return []

        memo: Dict[str, List[str]] = {}

        def longest_path(tid: str) -> List[str]:
            if tid in memo:
                return memo[tid]
            node = self._tasks.get(tid)
            if not node or not node.dependencies:
                memo[tid] = [tid]
                return [tid]

            best: List[str] = []
            for dep in node.dependencies:
                if dep in self._tasks:
                    path = longest_path(dep)
                    if len(path) > len(best):
                        best = path

            memo[tid] = best + [tid]
            return memo[tid]

        all_paths = [longest_path(tid) for tid in self._tasks]
        return max(all_paths, key=len) if all_paths else []

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List tasks with optional filters."""
        results = []
        for node in self._tasks.values():
            if status and node.status != status:
                continue
            if category and node.category != category:
                continue
            results.append(self._node_to_dict(node))
            if len(results) >= limit:
                break
        return results

    def list_categories(self) -> Dict[str, int]:
        """List categories with counts."""
        counts: Dict[str, int] = defaultdict(int)
        for node in self._tasks.values():
            counts[node.category] += 1
        return dict(sorted(counts.items()))

    def pending_count(self) -> int:
        """Count tasks not yet completed."""
        return sum(1 for n in self._tasks.values() if n.status in ("pending", "ready", "running"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _would_create_cycle(self, task_id: str, new_deps: Set[str]) -> bool:
        """Check if adding new_deps to task_id would create a cycle."""
        # BFS from each new dep to see if we can reach task_id
        for dep_id in new_deps:
            visited: Set[str] = set()
            queue = deque([task_id])
            while queue:
                current = queue.popleft()
                if current == dep_id:
                    return True
                if current in visited:
                    continue
                visited.add(current)
                node = self._tasks.get(current)
                if node:
                    queue.extend(node.dependents - visited)
        return False

    def _all_deps_satisfied(self, task_id: str) -> bool:
        """Check if all dependencies are completed or skipped."""
        node = self._tasks.get(task_id)
        if not node:
            return False
        return all(
            self._tasks.get(d) and self._tasks[d].status in ("completed", "skipped")
            for d in node.dependencies
        )

    def _check_ready(self, task_id: str) -> None:
        """Check if task should transition to ready."""
        node = self._tasks.get(task_id)
        if not node or node.status != "pending":
            return
        if self._all_deps_satisfied(task_id):
            node.status = "ready"

    def _prune(self) -> None:
        """Remove oldest completed/failed/skipped tasks."""
        finished = [
            (tid, n) for tid, n in self._tasks.items()
            if n.status in ("completed", "failed", "skipped")
        ]
        finished.sort(key=lambda x: x[1].completed_at)
        to_remove = len(self._tasks) - self._max_tasks
        for tid, _ in finished[:to_remove]:
            # Only remove if no dependents need us
            if not self._tasks[tid].dependents:
                del self._tasks[tid]

    def _node_to_dict(self, node: TaskNode) -> Dict:
        return {
            "task_id": node.task_id,
            "name": node.name,
            "status": node.status,
            "dependencies": list(node.dependencies),
            "dependents": list(node.dependents),
            "dependency_count": len(node.dependencies),
            "dependent_count": len(node.dependents),
            "category": node.category,
            "priority": node.priority,
            "metadata": node.metadata,
            "created_at": node.created_at,
            "completed_at": node.completed_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        status_counts = defaultdict(int)
        for n in self._tasks.values():
            status_counts[n.status] += 1
        return {
            **self._stats,
            "total_tasks": len(self._tasks),
            **{f"status_{k}": v for k, v in status_counts.items()},
        }

    def reset(self) -> None:
        self._tasks.clear()
        self._stats = {k: 0 for k in self._stats}
