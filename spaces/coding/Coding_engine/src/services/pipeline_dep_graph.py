"""
Pipeline Dependency Graph — models task dependencies, topological
ordering, critical path analysis, and parallel execution planning.

Features:
- Add/remove nodes (tasks) with metadata
- Add/remove directed edges (dependencies)
- Topological sort for execution order
- Cycle detection
- Critical path analysis
- Parallel execution groups (tasks that can run concurrently)
- Subgraph extraction
- Impact analysis (what depends on X)
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    """A node (task) in the dependency graph."""
    node_id: str
    name: str
    duration: float = 0.0  # estimated duration in seconds
    status: str = "pending"  # pending, running, completed, failed, skipped
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Pipeline Dependency Graph
# ---------------------------------------------------------------------------

class PipelineDependencyGraph:
    """Models and analyzes task dependency graphs."""

    def __init__(self):
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[str, Set[str]] = defaultdict(set)  # node → set of dependencies
        self._reverse: Dict[str, Set[str]] = defaultdict(set)  # node → set of dependents

        self._stats = {
            "total_nodes_added": 0,
            "total_edges_added": 0,
        }

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        name: str = "",
        duration: float = 0.0,
        metadata: Optional[Dict] = None,
        tags: Optional[Set[str]] = None,
    ) -> bool:
        """Add a node to the graph."""
        if node_id in self._nodes:
            return False
        self._nodes[node_id] = GraphNode(
            node_id=node_id,
            name=name or node_id,
            duration=duration,
            metadata=metadata or {},
            tags=tags or set(),
        )
        self._stats["total_nodes_added"] += 1
        return True

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its edges."""
        if node_id not in self._nodes:
            return False
        # Remove edges
        for dep in list(self._edges.get(node_id, set())):
            self._reverse[dep].discard(node_id)
        self._edges.pop(node_id, None)

        for dependent in list(self._reverse.get(node_id, set())):
            self._edges[dependent].discard(node_id)
        self._reverse.pop(node_id, None)

        del self._nodes[node_id]
        return True

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node details."""
        n = self._nodes.get(node_id)
        if not n:
            return None
        return {
            "node_id": n.node_id,
            "name": n.name,
            "duration": n.duration,
            "status": n.status,
            "metadata": n.metadata,
            "tags": sorted(n.tags),
            "dependencies": sorted(self._edges.get(node_id, set())),
            "dependents": sorted(self._reverse.get(node_id, set())),
        }

    def list_nodes(self, status: Optional[str] = None, tags: Optional[Set[str]] = None) -> List[Dict]:
        """List nodes with optional filters."""
        results = []
        for n in sorted(self._nodes.values(), key=lambda x: x.node_id):
            if status and n.status != status:
                continue
            if tags and not tags.intersection(n.tags):
                continue
            results.append(self.get_node(n.node_id))
        return results

    def set_status(self, node_id: str, status: str) -> bool:
        """Set node status."""
        n = self._nodes.get(node_id)
        if not n:
            return False
        n.status = status
        return True

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(self, node_id: str, depends_on: str) -> bool:
        """Add a dependency edge: node_id depends on depends_on."""
        if node_id not in self._nodes or depends_on not in self._nodes:
            return False
        if node_id == depends_on:
            return False
        if depends_on in self._edges[node_id]:
            return False  # Already exists

        self._edges[node_id].add(depends_on)
        self._reverse[depends_on].add(node_id)
        self._stats["total_edges_added"] += 1
        return True

    def remove_edge(self, node_id: str, depends_on: str) -> bool:
        """Remove a dependency edge."""
        if depends_on not in self._edges.get(node_id, set()):
            return False
        self._edges[node_id].discard(depends_on)
        self._reverse[depends_on].discard(node_id)
        return True

    def get_dependencies(self, node_id: str) -> List[str]:
        """Get direct dependencies of a node."""
        return sorted(self._edges.get(node_id, set()))

    def get_dependents(self, node_id: str) -> List[str]:
        """Get direct dependents of a node."""
        return sorted(self._reverse.get(node_id, set()))

    # ------------------------------------------------------------------
    # Graph analysis
    # ------------------------------------------------------------------

    def has_cycle(self) -> bool:
        """Check if the graph has cycles."""
        return self.topological_sort() is None

    def topological_sort(self) -> Optional[List[str]]:
        """Return topological ordering, or None if cycle exists."""
        in_degree = {n: 0 for n in self._nodes}
        for node_id, deps in self._edges.items():
            in_degree[node_id] = len(deps)

        queue = deque(n for n, d in in_degree.items() if d == 0)
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for dependent in self._reverse.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(self._nodes):
            return None  # Cycle detected
        return result

    def parallel_groups(self) -> Optional[List[List[str]]]:
        """Group tasks into parallel execution layers.
        Each group can run concurrently; groups must run sequentially.
        Returns None if cycle exists."""
        in_degree = {n: 0 for n in self._nodes}
        for node_id, deps in self._edges.items():
            in_degree[node_id] = len(deps)

        queue = deque(n for n, d in in_degree.items() if d == 0)
        groups = []

        while queue:
            group = list(queue)
            groups.append(sorted(group))
            next_queue = deque()
            for node in group:
                for dependent in self._reverse.get(node, set()):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)
            queue = next_queue

        total = sum(len(g) for g in groups)
        if total != len(self._nodes):
            return None  # Cycle
        return groups

    def critical_path(self) -> Optional[List[Dict]]:
        """Find the critical path (longest path through the graph).
        Returns None if cycle exists."""
        order = self.topological_sort()
        if order is None:
            return None

        # Longest path via dynamic programming
        dist: Dict[str, float] = {n: 0.0 for n in self._nodes}
        pred: Dict[str, Optional[str]] = {n: None for n in self._nodes}

        for node_id in order:
            node = self._nodes[node_id]
            current = dist[node_id] + node.duration
            for dependent in self._reverse.get(node_id, set()):
                if current > dist[dependent]:
                    dist[dependent] = current
                    pred[dependent] = node_id

        # Find end of critical path
        if not dist:
            return []
        end_node = max(dist, key=lambda n: dist[n] + self._nodes[n].duration)

        # Trace back
        path = []
        current = end_node
        while current is not None:
            node = self._nodes[current]
            path.append({
                "node_id": current,
                "name": node.name,
                "duration": node.duration,
                "cumulative": round(dist[current] + node.duration, 3),
            })
            current = pred[current]

        path.reverse()
        return path

    def get_all_dependencies(self, node_id: str) -> Set[str]:
        """Get all transitive dependencies (everything this node depends on)."""
        if node_id not in self._nodes:
            return set()
        visited = set()
        queue = deque(self._edges.get(node_id, set()))
        while queue:
            dep = queue.popleft()
            if dep in visited:
                continue
            visited.add(dep)
            queue.extend(self._edges.get(dep, set()) - visited)
        return visited

    def get_all_dependents(self, node_id: str) -> Set[str]:
        """Get all transitive dependents (everything that depends on this node)."""
        if node_id not in self._nodes:
            return set()
        visited = set()
        queue = deque(self._reverse.get(node_id, set()))
        while queue:
            dep = queue.popleft()
            if dep in visited:
                continue
            visited.add(dep)
            queue.extend(self._reverse.get(dep, set()) - visited)
        return visited

    def impact_analysis(self, node_id: str) -> Dict:
        """Analyze the impact of a node failure."""
        if node_id not in self._nodes:
            return {"node_id": node_id, "found": False}

        affected = self.get_all_dependents(node_id)
        return {
            "node_id": node_id,
            "found": True,
            "direct_dependents": sorted(self._reverse.get(node_id, set())),
            "total_affected": len(affected),
            "affected_nodes": sorted(affected),
        }

    def get_roots(self) -> List[str]:
        """Get root nodes (no dependencies)."""
        return sorted(n for n in self._nodes if not self._edges.get(n))

    def get_leaves(self) -> List[str]:
        """Get leaf nodes (no dependents)."""
        return sorted(n for n in self._nodes if not self._reverse.get(n))

    def get_ready_nodes(self) -> List[str]:
        """Get nodes whose dependencies are all completed."""
        ready = []
        for node_id, node in self._nodes.items():
            if node.status != "pending":
                continue
            deps = self._edges.get(node_id, set())
            if all(self._nodes[d].status == "completed" for d in deps if d in self._nodes):
                ready.append(node_id)
        return sorted(ready)

    # ------------------------------------------------------------------
    # Subgraph
    # ------------------------------------------------------------------

    def extract_subgraph(self, node_ids: Set[str]) -> Dict:
        """Extract a subgraph containing only specified nodes."""
        nodes = []
        edges = []
        for nid in sorted(node_ids):
            n = self._nodes.get(nid)
            if not n:
                continue
            nodes.append(nid)
            for dep in self._edges.get(nid, set()):
                if dep in node_ids:
                    edges.append((nid, dep))
        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        edge_count = sum(len(deps) for deps in self._edges.values())
        return {
            **self._stats,
            "total_nodes": len(self._nodes),
            "total_edges": edge_count,
            "has_cycle": self.has_cycle(),
            "roots": len(self.get_roots()),
            "leaves": len(self.get_leaves()),
        }

    def reset(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._reverse.clear()
        self._stats = {k: 0 for k in self._stats}
