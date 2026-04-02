"""Agent Workflow Scope -- manages workflow execution scopes (nested contexts).

Creates and manages scoped execution contexts for agent workflows, supporting
nested parent-child relationships, per-scope variables, and querying.
Uses SHA-256-based IDs with an ``awsc-`` prefix.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowScopeState:
    """Internal store for workflow scope entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowScope:
    """Manages workflow execution scopes (nested contexts).

    Supports creating scopes with optional parent relationships, setting and
    getting per-scope variables, querying, and collecting statistics.
    """

    PREFIX = "awsc-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowScopeState()
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
    # Create scope
    # ------------------------------------------------------------------

    def create_scope(
        self,
        agent_id: str,
        workflow_name: str,
        parent_scope_id: str = "",
        variables: dict = None,
    ) -> str:
        """Create a workflow execution scope.

        Returns the scope ID (``awsc-`` prefix).
        """
        self._prune()
        scope_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "scope_id": scope_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "parent_scope_id": parent_scope_id,
            "variables": dict(variables) if variables else {},
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[scope_id] = entry
        self._fire("scope_created", entry)
        logger.debug(
            "Scope created: %s for agent=%s workflow=%s parent=%s",
            scope_id, agent_id, workflow_name, parent_scope_id,
        )
        return scope_id

    # ------------------------------------------------------------------
    # Get scope by ID
    # ------------------------------------------------------------------

    def get_scope(self, scope_id: str) -> Optional[dict]:
        """Get a scope by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(scope_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Variable management
    # ------------------------------------------------------------------

    def set_variable(self, scope_id: str, key: str, value: Any) -> bool:
        """Set a variable within a scope.  Returns ``False`` if scope not found."""
        entry = self._state.entries.get(scope_id)
        if entry is None:
            return False
        entry["variables"][key] = value
        self._fire("variable_set", {"scope_id": scope_id, "key": key, "value": value})
        return True

    def get_variable(self, scope_id: str, key: str) -> Any:
        """Get a variable from a scope.  Returns ``None`` if not found."""
        entry = self._state.entries.get(scope_id)
        if entry is None:
            return None
        return entry["variables"].get(key)

    # ------------------------------------------------------------------
    # Get scopes (query)
    # ------------------------------------------------------------------

    def get_scopes(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query scopes, newest first.

        Optionally filter by *agent_id* and cap results with *limit*.
        """
        if agent_id:
            candidates = [
                e for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            ]
        else:
            candidates = list(self._state.entries.values())
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get scope count
    # ------------------------------------------------------------------

    def get_scope_count(self, agent_id: str = "") -> int:
        """Return the number of scopes, optionally filtered by *agent_id*."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the scope service."""
        agents = set()
        total_variables = 0
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
            total_variables += len(entry.get("variables", {}))
        return {
            "total_scopes": len(self._state.entries),
            "unique_agents": len(agents),
            "total_variables": total_variables,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored scopes, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
