"""Pipeline Dependency Resolver – manage pipeline component dependencies,
topological ordering, cycle detection, and parallel install planning.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _Component:
    component_id: str
    name: str
    version: str
    tags: List[str]
    created_at: float


@dataclass
class _HistoryEntry:
    entry_id: str
    action: str
    detail: Dict[str, Any]
    timestamp: float


# ---------------------------------------------------------------------------
# PipelineDependencyResolver
# ---------------------------------------------------------------------------

class PipelineDependencyResolver:
    """Manage pipeline component dependencies and compute execution order."""

    def __init__(self, max_entries: int = 10000, max_history: int = 50000):
        self._max_entries = max(1, max_entries)
        self._max_history = max(1, max_history)
        self._components: Dict[str, _Component] = {}       # component_id -> _Component
        self._name_index: Dict[str, str] = {}               # name -> component_id
        self._forward: Dict[str, Set[str]] = {}             # name -> set of dependency names
        self._forward_required: Dict[str, Dict[str, bool]] = {}  # name -> {dep: required}
        self._reverse: Dict[str, Set[str]] = {}             # name -> set of dependent names
        self._history: List[_HistoryEntry] = []
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._total_components_registered = 0
        self._total_dependencies_added = 0
        self._total_dependencies_removed = 0
        self._total_components_removed = 0
        self._cycles_detected = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, prefix: str, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        eid = self._make_id("evt-", action)
        entry = _HistoryEntry(
            entry_id=eid, action=action, detail=detail, timestamp=time.time(),
        )
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._fire(action, detail)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, fn: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = fn
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Notify all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Component management
    # ------------------------------------------------------------------

    def register_component(
        self,
        name: str,
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a pipeline component. Returns ID (pdr-...) or '' if dup."""
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._components) >= self._max_entries:
            oldest_id = next(iter(self._components))
            oldest = self._components[oldest_id]
            self._remove_component_internal(oldest.name)
        cid = self._make_id("pdr-", name)
        now = time.time()
        comp = _Component(
            component_id=cid,
            name=name,
            version=version,
            tags=list(tags) if tags else [],
            created_at=now,
        )
        self._components[cid] = comp
        self._name_index[name] = cid
        self._forward[name] = set()
        self._forward_required[name] = {}
        self._reverse[name] = set()
        self._total_components_registered += 1
        self._record_history("component_registered", {
            "component_id": cid, "name": name, "version": version,
        })
        return cid

    def get_component(self, name: str) -> Optional[Dict[str, Any]]:
        """Get component info by name."""
        cid = self._name_index.get(name)
        if not cid:
            return None
        comp = self._components[cid]
        return {
            "component_id": comp.component_id,
            "name": comp.name,
            "version": comp.version,
            "tags": list(comp.tags),
            "created_at": comp.created_at,
            "dependencies": sorted(self._forward.get(name, set())),
            "dependents": sorted(self._reverse.get(name, set())),
        }

    def list_components(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all components, optionally filtered by tag."""
        results: List[Dict[str, Any]] = []
        for comp in self._components.values():
            if tag and tag not in comp.tags:
                continue
            info = self.get_component(comp.name)
            if info:
                results.append(info)
        return results

    def remove_component(self, name: str) -> bool:
        """Remove a component and all its dependency edges."""
        if name not in self._name_index:
            return False
        self._remove_component_internal(name)
        self._total_components_removed += 1
        self._record_history("component_removed", {"name": name})
        return True

    def _remove_component_internal(self, name: str) -> None:
        """Remove component without recording history (also used by pruning)."""
        cid = self._name_index.pop(name, None)
        if cid:
            self._components.pop(cid, None)
        # Remove forward edges from this component
        deps = self._forward.pop(name, set())
        self._forward_required.pop(name, None)
        for dep in deps:
            rev = self._reverse.get(dep)
            if rev:
                rev.discard(name)
        # Remove reverse edges pointing to this component
        dependents = self._reverse.pop(name, set())
        for dep in dependents:
            fwd = self._forward.get(dep)
            if fwd:
                fwd.discard(name)
            req = self._forward_required.get(dep)
            if req:
                req.pop(name, None)

    # ------------------------------------------------------------------
    # Dependency management
    # ------------------------------------------------------------------

    def add_dependency(
        self, component: str, depends_on: str, required: bool = True,
    ) -> bool:
        """Add a dependency edge. Returns False if would create a cycle."""
        if component not in self._name_index or depends_on not in self._name_index:
            return False
        if component == depends_on:
            return False
        if depends_on in self._forward.get(component, set()):
            return True  # already exists
        if self._would_create_cycle(component, depends_on):
            return False
        self._forward.setdefault(component, set()).add(depends_on)
        self._forward_required.setdefault(component, {})[depends_on] = required
        self._reverse.setdefault(depends_on, set()).add(component)
        self._total_dependencies_added += 1
        self._record_history("dependency_added", {
            "component": component, "depends_on": depends_on, "required": required,
        })
        return True

    def remove_dependency(self, component: str, depends_on: str) -> bool:
        """Remove a dependency edge."""
        fwd = self._forward.get(component)
        if not fwd or depends_on not in fwd:
            return False
        fwd.discard(depends_on)
        req = self._forward_required.get(component)
        if req:
            req.pop(depends_on, None)
        rev = self._reverse.get(depends_on)
        if rev:
            rev.discard(component)
        self._total_dependencies_removed += 1
        self._record_history("dependency_removed", {
            "component": component, "depends_on": depends_on,
        })
        return True

    def get_dependencies(self, component: str) -> List[str]:
        """Get direct dependencies of a component."""
        return sorted(self._forward.get(component, set()))

    def get_dependents(self, component: str) -> List[str]:
        """Get components that directly depend on this component."""
        return sorted(self._reverse.get(component, set()))

    # ------------------------------------------------------------------
    # Cycle detection — DFS with visited / recursion-stack
    # ------------------------------------------------------------------

    def _would_create_cycle(self, component: str, depends_on: str) -> bool:
        """Check whether adding component -> depends_on would create a cycle."""
        visited: Set[str] = set()
        stack = [depends_on]
        while stack:
            current = stack.pop()
            if current == component:
                return True
            if current in visited:
                continue
            visited.add(current)
            for dep in self._forward.get(current, set()):
                if dep not in visited:
                    stack.append(dep)
        return False

    def detect_cycles(self) -> List[List[str]]:
        """Find all cycles using DFS with visited/recursion-stack."""
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        path: List[str] = []

        def _dfs(node: str) -> None:
            visited.add(node)
            in_stack.add(node)
            path.append(node)

            for neighbor in sorted(self._forward.get(node, set())):
                if neighbor not in visited:
                    _dfs(neighbor)
                elif neighbor in in_stack:
                    start = path.index(neighbor)
                    cycles.append(list(path[start:]))

            path.pop()
            in_stack.discard(node)

        for name in sorted(self._name_index.keys()):
            if name not in visited:
                _dfs(name)

        if cycles:
            self._cycles_detected += len(cycles)
            self._record_history("cycles_detected", {"count": len(cycles)})
        return cycles

    # ------------------------------------------------------------------
    # Topological sort — resolve transitive deps for one component
    # ------------------------------------------------------------------

    def resolve(self, component: str) -> List[str]:
        """Get ordered list of all transitive deps needed before component."""
        if component not in self._name_index:
            return []

        # BFS to collect all transitive dependencies
        needed: Set[str] = set()
        queue: deque[str] = deque(self._forward.get(component, set()))
        while queue:
            dep = queue.popleft()
            if dep in needed:
                continue
            needed.add(dep)
            queue.extend(self._forward.get(dep, set()) - needed)

        if not needed:
            return []

        # Build in-degree map for the subgraph
        in_degree: Dict[str, int] = {}
        for n in needed:
            count = 0
            for dep in self._forward.get(n, set()):
                if dep in needed:
                    count += 1
            in_degree[n] = count

        q: deque[str] = deque(sorted(n for n, d in in_degree.items() if d == 0))
        result: List[str] = []

        while q:
            node = q.popleft()
            result.append(node)
            for dependent in sorted(self._reverse.get(node, set())):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        q.append(dependent)

        return result

    # ------------------------------------------------------------------
    # Parallel install waves — Kahn's algorithm over entire graph
    # ------------------------------------------------------------------

    def get_install_order(self) -> List[List[str]]:
        """Get parallel install waves using Kahn's algorithm."""
        all_names = set(self._name_index.keys())
        if not all_names:
            return []

        # Compute in-degree for each component
        in_degree: Dict[str, int] = {}
        for name in all_names:
            count = 0
            for dep in self._forward.get(name, set()):
                if dep in all_names:
                    count += 1
            in_degree[name] = count

        queue: deque[str] = deque(sorted(
            n for n, d in in_degree.items() if d == 0
        ))
        waves: List[List[str]] = []
        processed = 0

        while queue:
            wave = sorted(queue)
            waves.append(wave)
            queue.clear()
            for node in wave:
                processed += 1
                for dependent in sorted(self._reverse.get(node, set())):
                    if dependent in in_degree:
                        in_degree[dependent] -= 1
                        if in_degree[dependent] == 0:
                            queue.append(dependent)

        # Remaining nodes have cycles — add as final wave
        if processed < len(all_names):
            remaining = sorted(
                n for n in all_names
                if n not in {name for wave in waves for name in wave}
            )
            if remaining:
                waves.append(remaining)

        return waves

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_leaf_components(self) -> List[str]:
        """Components with no dependencies (roots of the dependency tree)."""
        results: List[str] = []
        for name in sorted(self._name_index.keys()):
            if not self._forward.get(name):
                results.append(name)
        return results

    def get_orphan_components(self) -> List[str]:
        """Components that nothing depends on (no reverse edges)."""
        results: List[str] = []
        for name in sorted(self._name_index.keys()):
            if not self._reverse.get(name):
                results.append(name)
        return results

    # ------------------------------------------------------------------
    # Standard interface
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent history events, newest first."""
        entries = self._history[-limit:] if limit > 0 else self._history
        results: List[Dict[str, Any]] = []
        for entry in reversed(entries):
            results.append({
                "entry_id": entry.entry_id,
                "action": entry.action,
                "detail": entry.detail,
                "timestamp": entry.timestamp,
            })
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get resolver statistics."""
        edge_count = sum(len(deps) for deps in self._forward.values())
        return {
            "current_components": len(self._components),
            "current_edges": edge_count,
            "total_components_registered": self._total_components_registered,
            "total_components_removed": self._total_components_removed,
            "total_dependencies_added": self._total_dependencies_added,
            "total_dependencies_removed": self._total_dependencies_removed,
            "cycles_detected": self._cycles_detected,
            "history_size": len(self._history),
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state to initial values."""
        self._components.clear()
        self._name_index.clear()
        self._forward.clear()
        self._forward_required.clear()
        self._reverse.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_components_registered = 0
        self._total_dependencies_added = 0
        self._total_dependencies_removed = 0
        self._total_components_removed = 0
        self._cycles_detected = 0
