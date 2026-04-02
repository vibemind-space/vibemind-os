"""Agent Workflow Brancher -- creates workflow branches for conditional execution.

Stores branch records for agent workflows.  Each branch captures the agent,
workflow name, branch name, condition, and optional metadata.  When the store
exceeds ``MAX_ENTRIES`` the oldest quarter of entries is pruned automatically.

Uses SHA-256-based IDs with an ``awbr-`` prefix.

Usage::

    brancher = AgentWorkflowBrancher()

    # Create a branch
    record_id = brancher.branch("agent-1", "wf1", "left", condition="x > 0")

    # Query
    entry = brancher.get_branch(record_id)
    entries = brancher.get_branches(agent_id="agent-1")
    stats = brancher.get_stats()
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowBrancherState:
    """Internal store for workflow branch entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowBrancher:
    """Creates workflow branches for conditional execution.

    Each branch record tracks which agent branched which workflow,
    along with the branch name, condition, and optional metadata.
    Records can be queried by agent.
    """

    PREFIX = "awbr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowBrancherState()

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
        """Remove the oldest quarter of entries when at capacity."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(),
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("_seq", 0)),
        )
        remove_count = len(sorted_entries) // 4
        if remove_count < 1:
            remove_count = 1
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently ignored."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        """Set the on_change callback."""
        if value is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = value

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Branch workflow
    # ------------------------------------------------------------------

    def branch(
        self,
        agent_id: str,
        workflow_name: str,
        branch_name: str,
        condition: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a workflow branch.

        Returns the record ID (``awbr-`` prefix) on success or ``""`` on failure.
        """
        if not agent_id or not workflow_name or not branch_name:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "branch_name": branch_name,
            "condition": condition,
            "metadata": dict(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("branch", self._state.entries[record_id])
        logger.debug(
            "Workflow branched: %s agent=%s workflow=%s branch=%s",
            record_id, agent_id, workflow_name, branch_name,
        )
        return record_id

    # ------------------------------------------------------------------
    # Get branch by ID
    # ------------------------------------------------------------------

    def get_branch(self, record_id: str) -> Optional[dict]:
        """Get a branch record by its ID. Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get branches (query)
    # ------------------------------------------------------------------

    def get_branches(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query branch records, newest first.

        Optionally filter by *agent_id* and cap results with *limit*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if (not agent_id or e["agent_id"] == agent_id)
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get branch count
    # ------------------------------------------------------------------

    def get_branch_count(self, agent_id: str = "") -> int:
        """Return the number of branch records, optionally filtered by *agent_id*."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        agents = set(e["agent_id"] for e in self._state.entries.values())
        return {
            "total_branches": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowBrancherState()
        logger.debug("AgentWorkflowBrancher reset")
