"""Pipeline Dependency Graph -- manages pipeline step dependencies as a
directed acyclic graph (DAG).

Features:
- Add nodes (steps) within named pipelines
- Add directed dependency edges between steps
- Topological sort for execution ordering
- Cycle detection per pipeline
- Forward and reverse dependency queries
- Per-pipeline DAG management with max_entries pruning
- Change callbacks for graph mutations
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
class _NodeEntry:
    """Internal representation of a pipeline step node."""
    node_id: str
    pipeline_id: str
    step_name: str
    created_at: float
    seq: int


@dataclass
class _PipelineGraph:
    """Internal DAG state for a single pipeline."""
    nodes: Dict[str, _NodeEntry] = field(default_factory=dict)
    edges: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    reverse: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))


# ---------------------------------------------------------------------------
# Pipeline Dependency Graph
# ---------------------------------------------------------------------------

class PipelineDependencyGraph:
    """Manages pipeline step dependencies as a directed acyclic graph."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._pipelines: Dict[str, _PipelineGraph] = {}
        self._all_nodes: Dict[str, _NodeEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._total_nodes_added = 0
        self._total_edges_added = 0
        self._total_cycles_detected = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        """Generate a collision-free ID with prefix pdg2-."""
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pdg2-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name.

        Returns True if found and removed, False if not found.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with event and data."""
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                logger.warning("callback_error", event=event)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding max_entries."""
        while len(self._all_nodes) > self._max_entries:
            oldest_id = min(self._all_nodes, key=lambda k: self._all_nodes[k].created_at)
            entry = self._all_nodes.pop(oldest_id)
            graph = self._pipelines.get(entry.pipeline_id)
            if graph and entry.step_name in graph.nodes:
                self._remove_node_from_graph(graph, entry.step_name)

    # ------------------------------------------------------------------
    # add_node
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Backward-compatible API (global graph, no pipeline_id)
    # ------------------------------------------------------------------

    def add_pipeline(self, name: str) -> str:
        """Backward-compatible: add a pipeline as a node in the global graph."""
        return self.add_node("_global", name)

    def add_dependency(self, dependent: str, dependency: str) -> bool:
        """Backward-compatible: add_dependency(dependent, dependency) in global graph.

        Means 'dependent' depends on 'dependency', so edge from dependency -> dependent.
        """
        return self.add_edge("_global", dependency, dependent)

    # ------------------------------------------------------------------
    # add_node
    # ------------------------------------------------------------------

    def add_node(self, pipeline_id: str, step_name: str) -> str:
        """Add a step node to a pipeline's dependency graph.

        Returns the node_id (pdg2-...) or empty string if duplicate.
        """
        graph = self._pipelines.get(pipeline_id)
        if graph and step_name in graph.nodes:
            logger.warning("node_duplicate", pipeline_id=pipeline_id, step_name=step_name)
            return ""

        if graph is None:
            graph = _PipelineGraph()
            self._pipelines[pipeline_id] = graph

        node_id = self._generate_id(f"{pipeline_id}.{step_name}")
        entry = _NodeEntry(
            node_id=node_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
            created_at=time.time(),
            seq=self._seq,
        )
        graph.nodes[step_name] = entry
        self._all_nodes[node_id] = entry
        self._total_nodes_added += 1
        self._prune()

        logger.info("node_added", node_id=node_id, pipeline_id=pipeline_id, step_name=step_name)
        self._fire("node_added", {
            "node_id": node_id, "pipeline_id": pipeline_id, "step_name": step_name,
        })
        return node_id

    # ------------------------------------------------------------------
    # add_edge
    # ------------------------------------------------------------------

    def add_edge(self, pipeline_id: str, from_step: str, to_step: str) -> bool:
        """Add a dependency edge: to_step depends on from_step.

        Returns True if both steps exist in the pipeline, False otherwise.
        """
        graph = self._pipelines.get(pipeline_id)
        if graph is None:
            return False
        if from_step not in graph.nodes or to_step not in graph.nodes:
            return False
        if from_step == to_step:
            return False
        if from_step in graph.edges[to_step]:
            return True  # Already exists, both exist so return True

        graph.edges[to_step].add(from_step)
        graph.reverse[from_step].add(to_step)
        self._total_edges_added += 1

        logger.info("edge_added", pipeline_id=pipeline_id, from_step=from_step, to_step=to_step)
        self._fire("edge_added", {
            "pipeline_id": pipeline_id, "from_step": from_step, "to_step": to_step,
        })
        return True

    # ------------------------------------------------------------------
    # get_dependencies / get_dependents
    # ------------------------------------------------------------------

    def get_dependencies(self, pipeline_id: str, step_name: str) -> List[str]:
        """Get step names that this step depends on (direct dependencies)."""
        graph = self._pipelines.get(pipeline_id)
        if graph is None or step_name not in graph.nodes:
            return []
        return sorted(graph.edges.get(step_name, set()))

    def get_dependents(self, pipeline_id: str, step_name: str) -> List[str]:
        """Get step names that depend on this step (direct dependents)."""
        graph = self._pipelines.get(pipeline_id)
        if graph is None or step_name not in graph.nodes:
            return []
        return sorted(graph.reverse.get(step_name, set()))

    # ------------------------------------------------------------------
    # get_execution_order
    # ------------------------------------------------------------------

    def get_execution_order(self, pipeline_id: str = "_global") -> List[str]:
        """Return step names in topological order (dependencies first).

        Returns empty list if pipeline not found or cycle detected.
        """
        graph = self._pipelines.get(pipeline_id)
        if graph is None:
            return []
        order = self._topological_sort(graph)
        return order if order is not None else []

    # ------------------------------------------------------------------
    # has_cycle
    # ------------------------------------------------------------------

    def has_cycle(self, pipeline_id: str = "_global") -> bool:
        """Check whether a pipeline's dependency graph contains a cycle."""
        graph = self._pipelines.get(pipeline_id)
        if graph is None:
            return False
        return self._has_cycle(graph)

    # ------------------------------------------------------------------
    # get_node_count
    # ------------------------------------------------------------------

    def get_node_count(self, pipeline_id: str = "") -> int:
        """Get the number of nodes. If pipeline_id given, count for that
        pipeline only; otherwise count all nodes across all pipelines."""
        if pipeline_id:
            graph = self._pipelines.get(pipeline_id)
            if graph is None:
                return 0
            return len(graph.nodes)
        return len(self._all_nodes)

    # ------------------------------------------------------------------
    # list_pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """List all registered pipeline IDs, sorted."""
        return sorted(self._pipelines.keys())

    # ------------------------------------------------------------------
    # get_graph_count
    # ------------------------------------------------------------------

    def get_graph_count(self) -> int:
        """Return the number of unique pipelines."""
        return len(self._pipelines)

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        total_edges = sum(
            len(deps) for graph in self._pipelines.values() for deps in graph.edges.values()
        )
        return {
            "total_nodes_added": self._total_nodes_added,
            "total_edges_added": self._total_edges_added,
            "total_cycles_detected": self._total_cycles_detected,
            "current_nodes": len(self._all_nodes),
            "current_pipelines": len(self._pipelines),
            "current_edges": total_edges,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all pipelines, nodes, callbacks, and counters."""
        self._pipelines.clear()
        self._all_nodes.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_nodes_added = 0
        self._total_edges_added = 0
        self._total_cycles_detected = 0
        logger.info("pipeline_dependency_graph_reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_cycle(graph: _PipelineGraph) -> bool:
        """Detect cycles using Kahn's algorithm."""
        in_degree: Dict[str, int] = {name: 0 for name in graph.nodes}
        for step_name, deps in graph.edges.items():
            if step_name in in_degree:
                in_degree[step_name] = len(deps)

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
        return visited != len(graph.nodes)

    @staticmethod
    def _topological_sort(graph: _PipelineGraph) -> Optional[List[str]]:
        """Return topological ordering, or None if cycle exists."""
        in_degree: Dict[str, int] = {name: 0 for name in graph.nodes}
        for step_name, deps in graph.edges.items():
            if step_name in in_degree:
                in_degree[step_name] = len(deps)

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

        if len(result) != len(graph.nodes):
            return None
        return result

    @staticmethod
    def _remove_node_from_graph(graph: _PipelineGraph, step_name: str) -> None:
        """Remove a node and all its edges from a pipeline graph."""
        for dep in list(graph.edges.get(step_name, set())):
            graph.reverse[dep].discard(step_name)
        graph.edges.pop(step_name, None)

        for dependent in list(graph.reverse.get(step_name, set())):
            graph.edges[dependent].discard(step_name)
        graph.reverse.pop(step_name, None)

        graph.nodes.pop(step_name, None)
