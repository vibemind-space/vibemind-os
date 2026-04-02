"""Pipeline dependency validation - manages and validates dependencies between
pipelines, detects cycles."""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class DependencyEntry:
    """A single dependency edge between two pipelines."""
    dependency_id: str
    pipeline_id: str
    depends_on: str
    created_at: float


class PipelineDependencyValidator:
    """Manages and validates dependencies between pipelines, detects cycles."""

    def __init__(self) -> None:
        self._dependencies: Dict[str, DependencyEntry] = {}
        self._registered: Set[str] = set()
        self._callbacks: Dict[str, Any] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"pdv-{self._seq}-{id(self)}"
        return "pdv-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Any) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        while len(self._dependencies) > self._max_entries:
            oldest_id = min(
                self._dependencies,
                key=lambda k: self._dependencies[k].created_at,
            )
            del self._dependencies[oldest_id]

    # ------------------------------------------------------------------
    # Pipeline registration
    # ------------------------------------------------------------------

    def register_pipeline(self, pipeline_id: str) -> bool:
        if pipeline_id in self._registered:
            return False
        self._registered.add(pipeline_id)
        self._fire("register_pipeline", {"pipeline_id": pipeline_id})
        return True

    def is_registered(self, pipeline_id: str) -> bool:
        return pipeline_id in self._registered

    def list_pipelines(self) -> List[str]:
        return sorted(self._registered)

    # ------------------------------------------------------------------
    # Dependency management
    # ------------------------------------------------------------------

    def add_dependency(self, pipeline_id: str, depends_on: str) -> str:
        if pipeline_id == depends_on:
            return ""
        dependency_id = self._generate_id()
        entry = DependencyEntry(
            dependency_id=dependency_id,
            pipeline_id=pipeline_id,
            depends_on=depends_on,
            created_at=time.time(),
        )
        self._dependencies[dependency_id] = entry
        self._prune()
        self._fire("add_dependency", {
            "dependency_id": dependency_id,
            "pipeline_id": pipeline_id,
            "depends_on": depends_on,
        })
        return dependency_id

    def get_dependency(self, dependency_id: str) -> Optional[Dict]:
        entry = self._dependencies.get(dependency_id)
        if entry is None:
            return None
        return {
            "dependency_id": entry.dependency_id,
            "pipeline_id": entry.pipeline_id,
            "depends_on": entry.depends_on,
            "created_at": entry.created_at,
        }

    def get_dependencies(self, pipeline_id: str) -> List[str]:
        results: List[str] = []
        for entry in self._dependencies.values():
            if entry.pipeline_id == pipeline_id:
                results.append(entry.depends_on)
        return results

    def get_dependents(self, pipeline_id: str) -> List[str]:
        results: List[str] = []
        for entry in self._dependencies.values():
            if entry.depends_on == pipeline_id:
                results.append(entry.pipeline_id)
        return results

    def remove_dependency(self, dependency_id: str) -> bool:
        entry = self._dependencies.pop(dependency_id, None)
        if entry is None:
            return False
        self._fire("remove_dependency", {
            "dependency_id": dependency_id,
            "pipeline_id": entry.pipeline_id,
            "depends_on": entry.depends_on,
        })
        return True

    def get_dependency_count(self) -> int:
        return len(self._dependencies)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, pipeline_id: str) -> Dict:
        missing: List[str] = []
        for entry in self._dependencies.values():
            if entry.pipeline_id == pipeline_id:
                if entry.depends_on not in self._registered:
                    missing.append(entry.depends_on)
        valid = len(missing) == 0
        return {"valid": valid, "missing": missing}

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    def has_cycle(self, pipeline_id: Optional[str] = None) -> bool:
        if pipeline_id is not None:
            return self._has_cycle_from(pipeline_id)
        return self._detect_cycle_global()

    def _has_cycle_from(self, start: str) -> bool:
        visited: Set[str] = set()
        stack: List[str] = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                return True
            visited.add(node)
            for entry in self._dependencies.values():
                if entry.pipeline_id == node:
                    if entry.depends_on == start:
                        return True
                    if entry.depends_on not in visited:
                        stack.append(entry.depends_on)
        return False

    def _detect_cycle_global(self) -> bool:
        adj: Dict[str, List[str]] = {}
        all_nodes: Set[str] = set()
        for entry in self._dependencies.values():
            adj.setdefault(entry.pipeline_id, []).append(entry.depends_on)
            all_nodes.add(entry.pipeline_id)
            all_nodes.add(entry.depends_on)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in all_nodes}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adj.get(node, []):
                if color[neighbor] == GRAY:
                    return True
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for node in all_nodes:
            if color[node] == WHITE:
                if dfs(node):
                    return True
        return False

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            "registered_count": len(self._registered),
            "dependency_count": len(self._dependencies),
            "callback_count": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        self._dependencies.clear()
        self._registered.clear()
        self._callbacks.clear()
        self._seq = 0
