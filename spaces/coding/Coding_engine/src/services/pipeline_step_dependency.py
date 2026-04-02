"""Pipeline step dependency — manages dependencies between pipeline steps.

Ensures steps execute in the correct order by tracking which steps depend
on others, supporting readiness checks and topological sorting.
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepDependencyState:
    """Internal state for the PipelineStepDependency service."""

    deps: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepDependency:
    """Manages dependencies between pipeline steps.

    Tracks which steps must complete before others can run, supports
    readiness checks, and computes topological execution order.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepDependencyState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psd-{self._state._seq}-{id(self)}"
        return "psd-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict entries when the store exceeds max_entries."""
        if len(self._state.deps) <= self._max_entries:
            return
        remove_count = len(self._state.deps) - self._max_entries
        removed = 0
        for dep_id in list(self._state.deps.keys()):
            if removed >= remove_count:
                break
            del self._state.deps[dep_id]
            removed += 1

    # ------------------------------------------------------------------
    # Add dependency
    # ------------------------------------------------------------------

    def add_dependency(self, pipeline_id: str, step_name: str, depends_on: str) -> str:
        """Add a dependency: depends_on must complete before step_name.

        Returns a dependency ID (psd-xxx).
        """
        self._prune_if_needed()

        dep_id = self._generate_id()
        self._state.deps[dep_id] = {
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "depends_on": depends_on,
        }

        self._fire("dependency_added", {
            "dep_id": dep_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "depends_on": depends_on,
        })
        return dep_id

    # ------------------------------------------------------------------
    # Remove dependency
    # ------------------------------------------------------------------

    def remove_dependency(self, dep_id: str) -> bool:
        """Remove a dependency by ID. Returns True if removed."""
        if dep_id not in self._state.deps:
            return False
        info = self._state.deps.pop(dep_id)
        self._fire("dependency_removed", {
            "dep_id": dep_id,
            **info,
        })
        return True

    # ------------------------------------------------------------------
    # Get dependencies
    # ------------------------------------------------------------------

    def get_dependencies(self, pipeline_id: str, step_name: str) -> List[str]:
        """Get steps that step_name depends on (must complete first)."""
        result: List[str] = []
        for dep in self._state.deps.values():
            if dep["pipeline_id"] == pipeline_id and dep["step_name"] == step_name:
                result.append(dep["depends_on"])
        return result

    # ------------------------------------------------------------------
    # Get dependents
    # ------------------------------------------------------------------

    def get_dependents(self, pipeline_id: str, step_name: str) -> List[str]:
        """Get steps that depend on step_name (blocked until step_name completes)."""
        result: List[str] = []
        for dep in self._state.deps.values():
            if dep["pipeline_id"] == pipeline_id and dep["depends_on"] == step_name:
                result.append(dep["step_name"])
        return result

    # ------------------------------------------------------------------
    # Is ready
    # ------------------------------------------------------------------

    def is_ready(self, pipeline_id: str, step_name: str, completed_steps: set) -> bool:
        """Check if all dependencies of step_name are in completed_steps.

        Returns True if the step has no dependencies or all are satisfied.
        """
        deps = self.get_dependencies(pipeline_id, step_name)
        if not deps:
            return True
        return all(d in completed_steps for d in deps)

    # ------------------------------------------------------------------
    # Get execution order
    # ------------------------------------------------------------------

    def get_execution_order(self, pipeline_id: str) -> List[str]:
        """Return topological sort of steps for a pipeline.

        If a cycle is detected, returns an empty list.
        """
        # Collect all steps and build adjacency / in-degree structures
        graph: Dict[str, Set[str]] = {}
        in_degree: Dict[str, int] = {}

        for dep in self._state.deps.values():
            if dep["pipeline_id"] != pipeline_id:
                continue
            src = dep["depends_on"]
            dst = dep["step_name"]
            for node in (src, dst):
                if node not in graph:
                    graph[node] = set()
                    in_degree.setdefault(node, 0)
            graph[src].add(dst)
            in_degree[dst] = in_degree.get(dst, 0) + 1

        if not graph:
            return []

        # Kahn's algorithm
        queue: deque[str] = deque()
        for node, deg in in_degree.items():
            if deg == 0:
                queue.append(node)

        order: List[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbour in graph.get(node, set()):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(order) != len(graph):
            return []  # cycle detected

        return order

    # ------------------------------------------------------------------
    # Get dep count
    # ------------------------------------------------------------------

    def get_dep_count(self, pipeline_id: str = "") -> int:
        """Get total dependency count, optionally filtered by pipeline."""
        if pipeline_id:
            return sum(
                1 for dep in self._state.deps.values()
                if dep["pipeline_id"] == pipeline_id
            )
        return len(self._state.deps)

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have dependencies."""
        seen: set = set()
        result: List[str] = []
        for dep in self._state.deps.values():
            pid = dep["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        pipelines = set(dep["pipeline_id"] for dep in self._state.deps.values())
        return {
            "total_dependencies": len(self._state.deps),
            "max_entries": self._max_entries,
            "pipelines": len(pipelines),
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored dependencies, callbacks, and reset sequence."""
        self._state.deps.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
