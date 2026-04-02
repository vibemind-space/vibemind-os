"""Pipeline task dependency resolver.

Resolves task execution order based on dependency graphs.
Supports topological sorting, cycle detection, and parallel group identification.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


@dataclass
class _Task:
    """Internal task record."""
    task_id: str = ""
    name: str = ""
    graph_id: str = ""
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, ready, running, completed, failed, skipped
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    result: str = ""


@dataclass
class _Graph:
    """Internal dependency graph record."""
    graph_id: str = ""
    name: str = ""
    status: str = "building"  # building, ready, running, completed, failed
    tasks: Dict[str, _Task] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0


class PipelineTaskDependencyResolver:
    """Resolves task execution order based on dependency graphs."""

    TASK_STATUSES = ("pending", "ready", "running", "completed", "failed", "skipped")

    def __init__(self, max_graphs: int = 5000, max_tasks_per_graph: int = 500):
        self._max_graphs = max_graphs
        self._max_tasks_per_graph = max_tasks_per_graph
        self._graphs: Dict[str, _Graph] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_graphs_created": 0,
            "total_tasks_added": 0,
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
            "total_cycles_detected": 0,
        }

    # ------------------------------------------------------------------
    # Graph CRUD
    # ------------------------------------------------------------------

    def create_graph(self, name: str, tags: Optional[List[str]] = None) -> str:
        """Create a new dependency graph."""
        if not name:
            return ""
        if len(self._graphs) >= self._max_graphs:
            return ""

        gid = "graph-" + hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:12]
        self._graphs[gid] = _Graph(
            graph_id=gid,
            name=name,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_graphs_created"] += 1
        self._fire("graph_created", {"graph_id": gid, "name": name})
        return gid

    def get_graph(self, graph_id: str) -> Optional[Dict]:
        """Get graph info."""
        g = self._graphs.get(graph_id)
        if not g:
            return None
        return {
            "graph_id": g.graph_id,
            "name": g.name,
            "status": g.status,
            "task_count": len(g.tasks),
            "tags": list(g.tags),
            "created_at": g.created_at,
        }

    def remove_graph(self, graph_id: str) -> bool:
        """Remove a graph."""
        if graph_id not in self._graphs:
            return False
        del self._graphs[graph_id]
        return True

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def add_task(self, graph_id: str, name: str, dependencies: Optional[List[str]] = None,
                 priority: int = 0, metadata: Optional[Dict] = None,
                 tags: Optional[List[str]] = None) -> str:
        """Add a task to a graph."""
        g = self._graphs.get(graph_id)
        if not g or not name:
            return ""
        if g.status != "building":
            return ""
        if len(g.tasks) >= self._max_tasks_per_graph:
            return ""

        tid = "task-" + hashlib.md5(f"{graph_id}{name}{time.time()}".encode()).hexdigest()[:12]
        g.tasks[tid] = _Task(
            task_id=tid,
            name=name,
            graph_id=graph_id,
            dependencies=list(dependencies or []),
            priority=priority,
            metadata=dict(metadata or {}),
            tags=list(tags or []),
            created_at=time.time(),
        )
        self._stats["total_tasks_added"] += 1
        return tid

    def get_task(self, graph_id: str, task_id: str) -> Optional[Dict]:
        """Get task info."""
        g = self._graphs.get(graph_id)
        if not g:
            return None
        t = g.tasks.get(task_id)
        if not t:
            return None
        return {
            "task_id": t.task_id,
            "name": t.name,
            "status": t.status,
            "dependencies": list(t.dependencies),
            "priority": t.priority,
            "metadata": dict(t.metadata),
            "tags": list(t.tags),
            "created_at": t.created_at,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "result": t.result,
        }

    def remove_task(self, graph_id: str, task_id: str) -> bool:
        """Remove a task from a graph (only while building)."""
        g = self._graphs.get(graph_id)
        if not g or g.status != "building":
            return False
        if task_id not in g.tasks:
            return False
        # Remove from other tasks' dependencies
        for t in g.tasks.values():
            if task_id in t.dependencies:
                t.dependencies.remove(task_id)
        del g.tasks[task_id]
        return True

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def has_cycle(self, graph_id: str) -> bool:
        """Check if the graph has a dependency cycle."""
        g = self._graphs.get(graph_id)
        if not g:
            return False

        # Build adjacency from task_id -> dependency task_ids
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def _dfs(tid: str) -> bool:
            visited.add(tid)
            rec_stack.add(tid)
            t = g.tasks.get(tid)
            if t:
                for dep in t.dependencies:
                    if dep not in visited:
                        if _dfs(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.discard(tid)
            return False

        for tid in g.tasks:
            if tid not in visited:
                if _dfs(tid):
                    self._stats["total_cycles_detected"] += 1
                    return True
        return False

    def validate_graph(self, graph_id: str) -> Dict:
        """Validate graph: check for cycles and missing dependencies."""
        g = self._graphs.get(graph_id)
        if not g:
            return {"valid": False, "errors": ["graph not found"]}

        errors: List[str] = []
        all_ids = set(g.tasks.keys())

        # Check for missing dependencies
        for tid, t in g.tasks.items():
            for dep in t.dependencies:
                if dep not in all_ids:
                    errors.append(f"task {tid} depends on missing task {dep}")

        # Check for cycles
        if self.has_cycle(graph_id):
            errors.append("cycle detected")

        return {"valid": len(errors) == 0, "errors": errors}

    def resolve_order(self, graph_id: str) -> List[str]:
        """Get topological execution order. Returns empty list if cycle exists."""
        g = self._graphs.get(graph_id)
        if not g:
            return []

        if self.has_cycle(graph_id):
            return []

        # Kahn's algorithm
        in_degree: Dict[str, int] = {tid: 0 for tid in g.tasks}
        for tid, t in g.tasks.items():
            for dep in t.dependencies:
                if dep in in_degree:
                    in_degree[tid] += 1

        # Start with tasks that have no dependencies, sorted by priority (desc)
        queue = sorted(
            [tid for tid, d in in_degree.items() if d == 0],
            key=lambda x: -g.tasks[x].priority
        )
        result: List[str] = []

        while queue:
            tid = queue.pop(0)
            result.append(tid)
            # Reduce in-degree for dependents
            for other_id, other_task in g.tasks.items():
                if tid in other_task.dependencies:
                    in_degree[other_id] -= 1
                    if in_degree[other_id] == 0:
                        # Insert sorted by priority
                        inserted = False
                        for i, q_id in enumerate(queue):
                            if g.tasks[other_id].priority > g.tasks[q_id].priority:
                                queue.insert(i, other_id)
                                inserted = True
                                break
                        if not inserted:
                            queue.append(other_id)

        return result

    def get_parallel_groups(self, graph_id: str) -> List[List[str]]:
        """Get groups of tasks that can run in parallel (execution waves)."""
        g = self._graphs.get(graph_id)
        if not g:
            return []
        if self.has_cycle(graph_id):
            return []

        remaining = set(g.tasks.keys())
        completed: Set[str] = set()
        groups: List[List[str]] = []

        while remaining:
            # Find tasks whose dependencies are all completed
            ready = []
            for tid in remaining:
                t = g.tasks[tid]
                deps_met = all(d in completed or d not in g.tasks for d in t.dependencies)
                if deps_met:
                    ready.append(tid)

            if not ready:
                break  # Shouldn't happen if no cycle

            # Sort by priority within group
            ready.sort(key=lambda x: -g.tasks[x].priority)
            groups.append(ready)
            for tid in ready:
                remaining.discard(tid)
                completed.add(tid)

        return groups

    # ------------------------------------------------------------------
    # Execution tracking
    # ------------------------------------------------------------------

    def start_graph(self, graph_id: str) -> bool:
        """Start executing a graph."""
        g = self._graphs.get(graph_id)
        if not g or g.status != "building":
            return False

        validation = self.validate_graph(graph_id)
        if not validation["valid"]:
            return False

        g.status = "running"

        # Mark tasks with no deps as ready
        for t in g.tasks.values():
            valid_deps = [d for d in t.dependencies if d in g.tasks]
            if not valid_deps:
                t.status = "ready"

        self._fire("graph_started", {"graph_id": graph_id})
        return True

    def start_task(self, graph_id: str, task_id: str) -> bool:
        """Mark a task as running."""
        g = self._graphs.get(graph_id)
        if not g:
            return False
        t = g.tasks.get(task_id)
        if not t or t.status != "ready":
            return False

        t.status = "running"
        t.started_at = time.time()
        return True

    def complete_task(self, graph_id: str, task_id: str, result: str = "") -> bool:
        """Mark a task as completed and unblock dependents."""
        g = self._graphs.get(graph_id)
        if not g:
            return False
        t = g.tasks.get(task_id)
        if not t or t.status != "running":
            return False

        t.status = "completed"
        t.completed_at = time.time()
        t.result = result
        self._stats["total_tasks_completed"] += 1

        # Unblock dependents
        for other in g.tasks.values():
            if task_id in other.dependencies and other.status == "pending":
                all_done = all(
                    g.tasks[d].status == "completed"
                    for d in other.dependencies
                    if d in g.tasks
                )
                if all_done:
                    other.status = "ready"

        # Check if graph is complete
        if all(t2.status in ("completed", "skipped") for t2 in g.tasks.values()):
            g.status = "completed"
            self._fire("graph_completed", {"graph_id": graph_id})

        self._fire("task_completed", {"graph_id": graph_id, "task_id": task_id})
        return True

    def fail_task(self, graph_id: str, task_id: str, reason: str = "") -> bool:
        """Mark a task as failed."""
        g = self._graphs.get(graph_id)
        if not g:
            return False
        t = g.tasks.get(task_id)
        if not t or t.status != "running":
            return False

        t.status = "failed"
        t.completed_at = time.time()
        t.result = reason
        self._stats["total_tasks_failed"] += 1

        g.status = "failed"
        self._fire("task_failed", {"graph_id": graph_id, "task_id": task_id})
        return True

    def skip_task(self, graph_id: str, task_id: str) -> bool:
        """Skip a task."""
        g = self._graphs.get(graph_id)
        if not g:
            return False
        t = g.tasks.get(task_id)
        if not t or t.status not in ("pending", "ready"):
            return False

        t.status = "skipped"
        t.completed_at = time.time()

        # Unblock dependents (treat skip as done)
        for other in g.tasks.values():
            if task_id in other.dependencies and other.status == "pending":
                all_done = all(
                    g.tasks[d].status in ("completed", "skipped")
                    for d in other.dependencies
                    if d in g.tasks
                )
                if all_done:
                    other.status = "ready"

        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_ready_tasks(self, graph_id: str) -> List[Dict]:
        """Get tasks ready to execute."""
        g = self._graphs.get(graph_id)
        if not g:
            return []
        result = []
        for t in g.tasks.values():
            if t.status == "ready":
                result.append({"task_id": t.task_id, "name": t.name, "priority": t.priority})
        result.sort(key=lambda x: -x["priority"])
        return result

    def get_graph_progress(self, graph_id: str) -> Dict:
        """Get graph execution progress."""
        g = self._graphs.get(graph_id)
        if not g:
            return {}
        total = len(g.tasks)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "running": 0,
                    "ready": 0, "pending": 0, "skipped": 0, "percent": 100.0}

        counts = {"pending": 0, "ready": 0, "running": 0, "completed": 0, "failed": 0, "skipped": 0}
        for t in g.tasks.values():
            counts[t.status] = counts.get(t.status, 0) + 1

        done = counts["completed"] + counts["skipped"]
        return {
            "total": total,
            **counts,
            "percent": round(done / total * 100, 1),
        }

    def get_task_dependents(self, graph_id: str, task_id: str) -> List[str]:
        """Get tasks that depend on a given task."""
        g = self._graphs.get(graph_id)
        if not g:
            return []
        return [t.task_id for t in g.tasks.values() if task_id in t.dependencies]

    def get_critical_path(self, graph_id: str) -> List[str]:
        """Get the longest dependency chain (critical path)."""
        g = self._graphs.get(graph_id)
        if not g or self.has_cycle(graph_id):
            return []

        # Find longest path via DFS
        memo: Dict[str, List[str]] = {}

        def _longest(tid: str) -> List[str]:
            if tid in memo:
                return memo[tid]
            t = g.tasks.get(tid)
            if not t or not t.dependencies:
                memo[tid] = [tid]
                return memo[tid]

            best: List[str] = []
            for dep in t.dependencies:
                if dep in g.tasks:
                    path = _longest(dep)
                    if len(path) > len(best):
                        best = path
            memo[tid] = best + [tid]
            return memo[tid]

        longest: List[str] = []
        for tid in g.tasks:
            path = _longest(tid)
            if len(path) > len(longest):
                longest = path
        return longest

    def list_graphs(self, status: Optional[str] = None,
                    tag: Optional[str] = None) -> List[Dict]:
        """List graphs with optional filters."""
        result = []
        for g in self._graphs.values():
            if status and g.status != status:
                continue
            if tag and tag not in g.tags:
                continue
            result.append({
                "graph_id": g.graph_id,
                "name": g.name,
                "status": g.status,
                "task_count": len(g.tasks),
                "tags": list(g.tags),
            })
        return result

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
            "current_graphs": len(self._graphs),
        }

    def reset(self) -> None:
        self._graphs.clear()
        self._stats = {k: 0 for k in self._stats}
