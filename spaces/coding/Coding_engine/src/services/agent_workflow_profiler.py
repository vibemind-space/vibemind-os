"""Agent Workflow Profiler -- profiles workflow execution performance.

Records performance metrics for workflow executions, providing an
in-memory profile store with rich querying, automatic pruning,
and change-notification callbacks.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.

Usage::

    profiler = AgentWorkflowProfiler()

    # Record a profile
    profile_id = profiler.profile("agent-1", "deploy", {"duration_ms": 1200})

    # Query
    entry = profiler.get_profile(profile_id)
    entries = profiler.get_profiles(agent_id="agent-1", workflow_name="deploy")
    stats = profiler.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# State dataclass
# ------------------------------------------------------------------

@dataclass
class AgentWorkflowProfilerState:
    """Holds the mutable state for the workflow profiler."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowProfiler:
    """Profiles workflow execution performance.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to keep.  When the limit is reached the
        oldest quarter of entries is pruned automatically.
    """

    PREFIX = "awpf-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowProfilerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

        # stats counters
        self._total_profiled: int = 0
        self._total_pruned: int = 0
        self._total_queries: int = 0

        logger.debug("agent_workflow_profiler.init")

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, workflow_name: str) -> str:
        self._state._seq += 1
        raw = f"{agent_id}-{workflow_name}-{time.time()}-{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = max(1, len(sorted_keys) // 4)
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]
            self._total_pruned += 1
        logger.debug("agent_workflow_profiler.pruned", extra={"removed": remove_count})

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Return the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns ``True`` if removed, ``False`` if not found."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke on_change first, then all registered callbacks, silencing exceptions."""
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("agent_workflow_profiler.on_change_error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("agent_workflow_profiler.callback_error")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def profile(
        self,
        agent_id: str,
        workflow_name: str,
        metrics: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a profile entry and return its profile ID (``awpf-xxx``).

        Parameters
        ----------
        agent_id:
            Identifier of the agent whose workflow is being profiled.
        workflow_name:
            Name of the workflow being profiled.
        metrics:
            Dictionary of performance metrics (e.g. ``{"duration_ms": 1200}``).
        metadata:
            Optional dictionary of additional metadata.

        Returns
        -------
        str
            The generated profile ID.
        """
        profile_id = self._generate_id(agent_id, workflow_name)
        now = time.time()
        entry = {
            "profile_id": profile_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "metrics": dict(metrics) if metrics else {},
            "metadata": dict(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[profile_id] = entry
        self._total_profiled += 1
        self._prune()

        logger.debug(
            "agent_workflow_profiler.profile",
            extra={
                "profile_id": profile_id,
                "agent_id": agent_id,
                "workflow_name": workflow_name,
            },
        )
        self._fire("profile_recorded", {
            "profile_id": profile_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
        })
        return profile_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_profile(self, profile_id: str) -> Optional[dict]:
        """Return the profile entry for *profile_id*, or ``None`` if not found.

        Returns a copy of the entry dict.
        """
        entry = self._state.entries.get(profile_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_profiles(
        self,
        agent_id: str = "",
        workflow_name: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return profile entries, optionally filtered by agent and/or workflow.

        Results are sorted newest-first by ``(created_at, _seq)`` for
        deterministic tie-breaking.

        Parameters
        ----------
        agent_id:
            Filter to entries for this agent.  Empty string means no filter.
        workflow_name:
            Filter to entries for this workflow.  Empty string means no filter.
        limit:
            Maximum number of entries to return.
        """
        self._total_queries += 1
        result = []
        for e in self._state.entries.values():
            if agent_id and e["agent_id"] != agent_id:
                continue
            if workflow_name and e["workflow_name"] != workflow_name:
                continue
            result.append(copy.deepcopy(e))

        result.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return result[:limit]

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_profile_count(self, agent_id: str = "") -> int:
        """Count profile entries, optionally filtered to a single agent.

        Parameters
        ----------
        agent_id:
            If non-empty, count only entries for this agent.
        """
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        return {
            "current_entries": len(self._state.entries),
            "total_profiled": self._total_profiled,
            "total_pruned": self._total_pruned,
            "total_queries": self._total_queries,
            "max_entries": self.MAX_ENTRIES,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state, callbacks, and on_change."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
        self._total_profiled = 0
        self._total_pruned = 0
        self._total_queries = 0
        logger.debug("agent_workflow_profiler.reset")
