"""Agent Workflow Resolver -- resolves workflow step dependencies and execution
order for agent workflows.

Registers steps with their dependencies, computes topological execution order,
and tracks dependency metadata.  Uses SHA-256-based IDs with an ``awre-`` prefix.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowResolverState:
    """Internal store for workflow dependency entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowResolver:
    """Resolves workflow step dependencies and execution order.

    Supports registering steps with dependencies, computing topological
    execution order, querying, and collecting statistics.
    """

    PREFIX = "awre-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowResolverState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict the oldest entries when the store exceeds *MAX_ENTRIES*."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(), key=lambda kv: kv[1].get("created_at", 0)
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently ignored."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Add dependency
    # ------------------------------------------------------------------

    def add_dependency(
        self,
        workflow_id: str,
        step_name: str,
        depends_on: List[str] = None,
    ) -> str:
        """Register a step with its dependencies for a workflow.

        Returns the dependency ID (``awre-`` prefix).
        """
        self._prune()
        dep_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "dep_id": dep_id,
            "workflow_id": workflow_id,
            "step_name": step_name,
            "depends_on": list(depends_on) if depends_on else [],
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[dep_id] = entry
        self._fire("dependency_added", entry)
        logger.debug(
            "Dependency added: %s for workflow=%s step=%s depends_on=%s",
            dep_id, workflow_id, step_name, entry["depends_on"],
        )
        return dep_id

    # ------------------------------------------------------------------
    # Get dependency by ID
    # ------------------------------------------------------------------

    def get_dependency(self, dep_id: str) -> Optional[dict]:
        """Get a dependency by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(dep_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Resolve order
    # ------------------------------------------------------------------

    def resolve_order(self, workflow_id: str) -> List[str]:
        """Return topological execution order of step names for a workflow.

        Steps with no dependencies come first, followed by steps whose
        dependencies have already appeared.  Steps are stable-sorted by
        registration order within each tier.
        """
        # Collect steps for this workflow
        steps: Dict[str, List[str]] = {}
        step_seq: Dict[str, int] = {}
        for entry in self._state.entries.values():
            if entry["workflow_id"] != workflow_id:
                continue
            name = entry["step_name"]
            if name not in steps:
                steps[name] = entry["depends_on"]
                step_seq[name] = entry["seq"]
            else:
                # Merge dependencies if step registered multiple times
                for dep in entry["depends_on"]:
                    if dep not in steps[name]:
                        steps[name].append(dep)
                step_seq[name] = min(step_seq[name], entry["seq"])

        # Simple topological sort (Kahn's algorithm)
        resolved: List[str] = []
        remaining = dict(steps)

        while remaining:
            # Find steps whose dependencies are all resolved
            ready = [
                name for name, deps in remaining.items()
                if all(d in resolved or d not in steps for d in deps)
            ]
            if not ready:
                # Remaining steps have circular dependencies; add by seq order
                ready = sorted(remaining.keys(), key=lambda n: step_seq.get(n, 0))
                resolved.extend(ready)
                break
            # Sort ready steps by registration order for stability
            ready.sort(key=lambda n: step_seq.get(n, 0))
            for name in ready:
                del remaining[name]
            resolved.extend(ready)

        self._fire("order_resolved", {"workflow_id": workflow_id, "order": resolved})
        return resolved

    # ------------------------------------------------------------------
    # Get dependencies (query)
    # ------------------------------------------------------------------

    def get_dependencies(self, workflow_id: str, limit: int = 50) -> List[dict]:
        """Query dependencies for a workflow, newest first.

        Cap results with *limit*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if e["workflow_id"] == workflow_id
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get dependency count
    # ------------------------------------------------------------------

    def get_dependency_count(self, workflow_id: str = "") -> int:
        """Return the number of dependencies, optionally filtered by workflow."""
        if not workflow_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["workflow_id"] == workflow_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the resolver service."""
        workflows = set()
        steps = set()
        for entry in self._state.entries.values():
            workflows.add(entry["workflow_id"])
            steps.add((entry["workflow_id"], entry["step_name"]))
        return {
            "total_dependencies": len(self._state.entries),
            "unique_workflows": len(workflows),
            "total_steps": len(steps),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored dependencies, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
