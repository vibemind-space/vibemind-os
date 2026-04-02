"""Pipeline Dependency Store -- tracks pipeline stage dependencies with
DAG validation and topological sorting.

Features:
- Register stages within named pipelines
- Declare directed dependencies between stages
- Cycle detection via Kahn's algorithm
- Topological sort for execution ordering
- Forward and reverse dependency queries
- Per-pipeline DAG management
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _StageEntry:
    """Internal representation of a pipeline stage."""
    stage_id: str
    pipeline_name: str
    stage_name: str
    tags: List[str]
    created_at: float


@dataclass
class _PipelineGraph:
    """Internal DAG state for a single pipeline."""
    stages: Dict[str, _StageEntry] = field(default_factory=dict)
    edges: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    reverse: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))


# ---------------------------------------------------------------------------
# Pipeline Dependency Store
# ---------------------------------------------------------------------------

class PipelineDependencyStore:
    """Tracks pipeline stage dependencies with DAG validation and
    topological sorting."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._pipelines: Dict[str, _PipelineGraph] = {}
        self._all_stages: Dict[str, _StageEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._total_registered = 0
        self._total_dependencies_added = 0
        self._total_removed = 0
        self._total_cycles_detected = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        """Generate a collision-free ID with prefix pds-."""
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pds-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

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
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding max_entries."""
        while len(self._all_stages) > self._max_entries:
            oldest_id = min(self._all_stages, key=lambda k: self._all_stages[k].created_at)
            entry = self._all_stages.pop(oldest_id)
            graph = self._pipelines.get(entry.pipeline_name)
            if graph and entry.stage_name in graph.stages:
                self._remove_stage_from_graph(graph, entry.stage_name)

    # ------------------------------------------------------------------
    # register_stage
    # ------------------------------------------------------------------

    def register_stage(self, pipeline_name: str, stage_name: str, tags: Optional[List[str]] = None) -> str:
        """Register a stage. Returns stage ID (pds-...) or "" if duplicate."""
        graph = self._pipelines.get(pipeline_name)
        if graph and stage_name in graph.stages:
            logger.warning("stage_duplicate", pipeline=pipeline_name, stage=stage_name)
            return ""

        if graph is None:
            graph = _PipelineGraph()
            self._pipelines[pipeline_name] = graph

        stage_id = self._generate_id(f"{pipeline_name}.{stage_name}")
        entry = _StageEntry(
            stage_id=stage_id,
            pipeline_name=pipeline_name,
            stage_name=stage_name,
            tags=list(tags) if tags else [],
            created_at=time.time(),
        )
        graph.stages[stage_name] = entry
        self._all_stages[stage_id] = entry
        self._total_registered += 1
        self._prune()

        logger.info("stage_registered", stage_id=stage_id, pipeline=pipeline_name, stage=stage_name)
        self._fire("register_stage", {
            "stage_id": stage_id, "pipeline_name": pipeline_name, "stage_name": stage_name,
        })
        return stage_id

    # ------------------------------------------------------------------
    # add_dependency
    # ------------------------------------------------------------------

    def add_dependency(self, pipeline_name: str, stage_name: str, depends_on: str) -> bool:
        """Add a dependency: stage_name depends on depends_on.
        Returns False on missing stage, self-dep, duplicate, or cycle."""
        graph = self._pipelines.get(pipeline_name)
        if graph is None:
            return False
        if stage_name not in graph.stages or depends_on not in graph.stages:
            return False
        if stage_name == depends_on:
            return False
        if depends_on in graph.edges[stage_name]:
            return False

        # Tentatively add and check for cycle
        graph.edges[stage_name].add(depends_on)
        graph.reverse[depends_on].add(stage_name)

        if self._has_cycle(graph):
            graph.edges[stage_name].discard(depends_on)
            graph.reverse[depends_on].discard(stage_name)
            self._total_cycles_detected += 1
            logger.warning("dependency_cycle_rejected", pipeline=pipeline_name,
                           stage=stage_name, depends_on=depends_on)
            return False

        self._total_dependencies_added += 1
        logger.info("dependency_added", pipeline=pipeline_name, stage=stage_name, depends_on=depends_on)
        self._fire("add_dependency", {
            "pipeline_name": pipeline_name, "stage_name": stage_name, "depends_on": depends_on,
        })
        return True

    # ------------------------------------------------------------------
    # get_dependencies / get_dependents
    # ------------------------------------------------------------------

    def get_dependencies(self, pipeline_name: str, stage_name: str) -> List[str]:
        """Get direct dependencies of a stage (what it depends on)."""
        graph = self._pipelines.get(pipeline_name)
        if graph is None or stage_name not in graph.stages:
            return []
        return sorted(graph.edges.get(stage_name, set()))

    def get_dependents(self, pipeline_name: str, stage_name: str) -> List[str]:
        """Get direct dependents of a stage (what depends on it)."""
        graph = self._pipelines.get(pipeline_name)
        if graph is None or stage_name not in graph.stages:
            return []
        return sorted(graph.reverse.get(stage_name, set()))

    # ------------------------------------------------------------------
    # get_execution_order
    # ------------------------------------------------------------------

    def get_execution_order(self, pipeline_name: str) -> List[str]:
        """Return topological execution order, or [] if not found / cycle."""
        graph = self._pipelines.get(pipeline_name)
        if graph is None:
            return []
        order = self._topological_sort(graph)
        return order if order is not None else []

    # ------------------------------------------------------------------
    # has_cycle
    # ------------------------------------------------------------------

    def has_cycle(self, pipeline_name: str) -> bool:
        """Check whether a pipeline's dependency graph contains a cycle."""
        graph = self._pipelines.get(pipeline_name)
        if graph is None:
            return False
        return self._has_cycle(graph)

    # ------------------------------------------------------------------
    # list_stages / list_pipelines
    # ------------------------------------------------------------------

    def list_stages(self, pipeline_name: str) -> List[Dict[str, Any]]:
        """List all stages in a pipeline as dicts, sorted by stage name."""
        graph = self._pipelines.get(pipeline_name)
        if graph is None:
            return []
        results: List[Dict[str, Any]] = []
        for entry in sorted(graph.stages.values(), key=lambda e: e.stage_name):
            results.append({
                "stage_id": entry.stage_id,
                "pipeline_name": entry.pipeline_name,
                "stage_name": entry.stage_name,
                "tags": list(entry.tags),
                "created_at": entry.created_at,
                "dependencies": sorted(graph.edges.get(entry.stage_name, set())),
                "dependents": sorted(graph.reverse.get(entry.stage_name, set())),
            })
        return results

    def list_pipelines(self) -> List[str]:
        """List all registered pipeline names, sorted."""
        return sorted(self._pipelines.keys())

    # ------------------------------------------------------------------
    # remove_stage
    # ------------------------------------------------------------------

    def remove_stage(self, pipeline_name: str, stage_name: str) -> bool:
        """Remove a stage and all its edges. Returns True if removed."""
        graph = self._pipelines.get(pipeline_name)
        if graph is None or stage_name not in graph.stages:
            return False

        entry = graph.stages[stage_name]
        self._all_stages.pop(entry.stage_id, None)
        self._remove_stage_from_graph(graph, stage_name)
        self._total_removed += 1

        if not graph.stages:
            del self._pipelines[pipeline_name]

        logger.info("stage_removed", pipeline=pipeline_name, stage=stage_name)
        self._fire("remove_stage", {"pipeline_name": pipeline_name, "stage_name": stage_name})
        return True

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        total_edges = sum(
            len(deps) for graph in self._pipelines.values() for deps in graph.edges.values()
        )
        return {
            "total_registered": self._total_registered,
            "total_dependencies_added": self._total_dependencies_added,
            "total_removed": self._total_removed,
            "total_cycles_detected": self._total_cycles_detected,
            "current_stages": len(self._all_stages),
            "current_pipelines": len(self._pipelines),
            "current_edges": total_edges,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all pipelines, stages, callbacks, and counters."""
        self._pipelines.clear()
        self._all_stages.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_dependencies_added = 0
        self._total_removed = 0
        self._total_cycles_detected = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_cycle(graph: _PipelineGraph) -> bool:
        """Detect cycles using Kahn's algorithm."""
        in_degree: Dict[str, int] = {name: 0 for name in graph.stages}
        for stage_name, deps in graph.edges.items():
            if stage_name in in_degree:
                in_degree[stage_name] = len(deps)

        queue = deque(name for name, d in in_degree.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for dependent in graph.reverse.get(node, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        return visited != len(graph.stages)

    @staticmethod
    def _topological_sort(graph: _PipelineGraph) -> Optional[List[str]]:
        """Return topological ordering, or None if cycle exists."""
        in_degree: Dict[str, int] = {name: 0 for name in graph.stages}
        for stage_name, deps in graph.edges.items():
            if stage_name in in_degree:
                in_degree[stage_name] = len(deps)

        queue = deque(sorted(name for name, d in in_degree.items() if d == 0))
        result: List[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for dependent in sorted(graph.reverse.get(node, set())):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if len(result) != len(graph.stages):
            return None
        return result

    @staticmethod
    def _remove_stage_from_graph(graph: _PipelineGraph, stage_name: str) -> None:
        """Remove a stage and all its edges from a pipeline graph."""
        for dep in list(graph.edges.get(stage_name, set())):
            graph.reverse[dep].discard(stage_name)
        graph.edges.pop(stage_name, None)

        for dependent in list(graph.reverse.get(stage_name, set())):
            graph.edges[dependent].discard(stage_name)
        graph.reverse.pop(stage_name, None)

        graph.stages.pop(stage_name, None)
