"""Agent Dependency Graph – tracks dependencies between agents.

Tracks dependencies between agents (which agents depend on which other
agents).  Provides cycle detection, transitive dependency resolution,
and topological ordering.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _AgentEntry:
    entry_id: str = ""
    agent_id: str = ""
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    created_at: float = 0.0
    seq: int = 0


class AgentDependencyGraph:
    """Tracks dependencies between agents."""

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, _AgentEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries = max_entries
        self._agent_index: Dict[str, str] = {}  # agent_id -> entry_id
        self._adj: Dict[str, Set[str]] = {}  # agent_id -> set of agent_ids it depends on
        self._rev: Dict[str, Set[str]] = {}  # agent_id -> set of agent_ids that depend on it

    def _make_id(self, agent_id: str) -> str:
        raw = f"{agent_id}-{time.time()}-{self._seq}"
        return "adg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def add_agent(self, agent_id: str) -> str:
        """Add an agent node to the graph. Returns entry ID."""
        if not agent_id:
            return ""
        if agent_id in self._agent_index:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""
        self._seq += 1
        eid = self._make_id(agent_id)
        entry = _AgentEntry(
            entry_id=eid,
            agent_id=agent_id,
            dependencies=[],
            dependents=[],
            created_at=time.time(),
            seq=self._seq,
        )
        self._entries[eid] = entry
        self._agent_index[agent_id] = eid
        self._adj[agent_id] = set()
        self._rev[agent_id] = set()
        self._fire("agent_added", {"entry_id": eid, "agent_id": agent_id})
        return eid

    def add_dependency(self, agent_id: str, depends_on: str) -> bool:
        """Add a dependency edge. Returns False if it would create a cycle."""
        if agent_id not in self._agent_index or depends_on not in self._agent_index:
            return False
        if agent_id == depends_on:
            return False
        if depends_on in self._adj[agent_id]:
            return False
        # Cycle check: would adding agent_id -> depends_on create a cycle?
        if self._would_create_cycle(agent_id, depends_on):
            return False
        self._seq += 1
        self._adj[agent_id].add(depends_on)
        self._rev[depends_on].add(agent_id)
        # Update entries
        eid_from = self._agent_index[agent_id]
        eid_to = self._agent_index[depends_on]
        self._entries[eid_from].dependencies = sorted(self._adj[agent_id])
        self._entries[eid_from].seq = self._seq
        self._entries[eid_to].dependents = sorted(self._rev[depends_on])
        self._entries[eid_to].seq = self._seq
        self._fire("dependency_added", {"agent_id": agent_id, "depends_on": depends_on})
        return True

    def remove_dependency(self, agent_id: str, depends_on: str) -> bool:
        """Remove a dependency edge."""
        if agent_id not in self._agent_index or depends_on not in self._agent_index:
            return False
        if depends_on not in self._adj.get(agent_id, set()):
            return False
        self._seq += 1
        self._adj[agent_id].discard(depends_on)
        self._rev[depends_on].discard(agent_id)
        eid_from = self._agent_index[agent_id]
        eid_to = self._agent_index[depends_on]
        self._entries[eid_from].dependencies = sorted(self._adj[agent_id])
        self._entries[eid_from].seq = self._seq
        self._entries[eid_to].dependents = sorted(self._rev[depends_on])
        self._entries[eid_to].seq = self._seq
        self._fire("dependency_removed", {"agent_id": agent_id, "depends_on": depends_on})
        return True

    def get_dependencies(self, agent_id: str) -> List[str]:
        """Get direct dependencies of an agent."""
        return sorted(self._adj.get(agent_id, set()))

    def get_dependents(self, agent_id: str) -> List[str]:
        """Get agents that depend on this agent."""
        return sorted(self._rev.get(agent_id, set()))

    def get_all_dependencies(self, agent_id: str) -> List[str]:
        """Get transitive closure of dependencies."""
        if agent_id not in self._agent_index:
            return []
        visited: Set[str] = set()
        stack = list(self._adj.get(agent_id, set()))
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self._adj.get(current, set()) - visited)
        return sorted(visited)

    def get_topological_order(self) -> List[str]:
        """Return agents in topological order (dependencies first)."""
        in_degree: Dict[str, int] = {aid: 0 for aid in self._agent_index}
        for aid, deps in self._adj.items():
            for dep in deps:
                # dep is depended upon by aid, so dep comes first
                # in_degree tracks how many dependencies an agent has
                pass
        # Kahn's algorithm: in_degree = number of dependencies (edges pointing to deps are
        # "agent depends on dep", so for topological order we want deps first).
        # An agent with no dependencies has in_degree 0.
        in_degree = {aid: len(self._adj.get(aid, set())) for aid in self._agent_index}
        queue = sorted([aid for aid, d in in_degree.items() if d == 0])
        result: List[str] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for dependent in sorted(self._rev.get(node, set())):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
            queue.sort()
        return result

    def has_cycle(self) -> bool:
        """Check if graph has any cycles using DFS."""
        white: Set[str] = set(self._agent_index.keys())
        gray: Set[str] = set()
        black: Set[str] = set()

        def dfs(node: str) -> bool:
            white.discard(node)
            gray.add(node)
            for neighbor in self._adj.get(node, set()):
                if neighbor in gray:
                    return True
                if neighbor in white:
                    if dfs(neighbor):
                        return True
            gray.discard(node)
            black.add(node)
            return False

        while white:
            node = next(iter(white))
            if dfs(node):
                return True
        return False

    def remove_agent(self, agent_id: str) -> bool:
        """Remove agent and all its edges."""
        eid = self._agent_index.pop(agent_id, None)
        if not eid:
            return False
        self._seq += 1
        self._entries.pop(eid, None)
        # Remove all edges involving this agent
        deps = self._adj.pop(agent_id, set())
        for dep in deps:
            self._rev.get(dep, set()).discard(agent_id)
            dep_eid = self._agent_index.get(dep)
            if dep_eid and dep_eid in self._entries:
                self._entries[dep_eid].dependents = sorted(self._rev.get(dep, set()))
                self._entries[dep_eid].seq = self._seq
        dependents = self._rev.pop(agent_id, set())
        for dep in dependents:
            self._adj.get(dep, set()).discard(agent_id)
            dep_eid = self._agent_index.get(dep)
            if dep_eid and dep_eid in self._entries:
                self._entries[dep_eid].dependencies = sorted(self._adj.get(dep, set()))
                self._entries[dep_eid].seq = self._seq
        self._fire("agent_removed", {"agent_id": agent_id})
        return True

    def list_agents(self) -> List[str]:
        """List all agent IDs in the graph."""
        return sorted(self._agent_index.keys())

    def get_agent_count(self) -> int:
        """Total agent count."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Entry lookup
    # ------------------------------------------------------------------

    def get_entry(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get full entry dict for an agent."""
        eid = self._agent_index.get(agent_id)
        if not eid or eid not in self._entries:
            return None
        return asdict(self._entries[eid])

    # ------------------------------------------------------------------
    # Cycle detection helper
    # ------------------------------------------------------------------

    def _would_create_cycle(self, agent_id: str, depends_on: str) -> bool:
        """Check if adding agent_id -> depends_on would create a cycle.

        A cycle exists if depends_on can already reach agent_id through
        existing edges (i.e., agent_id is a transitive dependency of
        depends_on).
        """
        visited: Set[str] = set()
        stack = [depends_on]
        while stack:
            current = stack.pop()
            if current == agent_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self._adj.get(current, set()))
        return False

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
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        total_edges = sum(len(deps) for deps in self._adj.values())
        return {
            "agent_count": len(self._entries),
            "edge_count": total_edges,
            "seq": self._seq,
            "max_entries": self._max_entries,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._callbacks.clear()
        self._agent_index.clear()
        self._adj.clear()
        self._rev.clear()
        self._seq = 0
