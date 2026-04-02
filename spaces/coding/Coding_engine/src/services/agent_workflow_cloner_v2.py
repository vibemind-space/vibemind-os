"""Agent Workflow Cloner V2 -- clones workflow definitions for reuse.

Stores clone records for agent workflows.  Each clone captures the agent,
workflow name, target, and optional metadata.  When the store exceeds
``MAX_ENTRIES`` the oldest quarter of entries is pruned automatically.

Uses SHA-256-based IDs with an ``awcv-`` prefix.

Usage::

    cloner = AgentWorkflowClonerV2()

    # Clone a workflow
    clone_id = cloner.clone_v2("agent-1", "wf-source", target="wf-target")

    # Query
    entry = cloner.get_clone(clone_id)
    entries = cloner.get_clones(agent_id="agent-1")
    stats = cloner.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowClonerV2State:
    """Internal store for workflow clone entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowClonerV2:
    """Clones workflow definitions for reuse (v2).

    Each clone record tracks which agent cloned which workflow to a new
    target, along with optional metadata.  Records can be queried by agent.
    """

    PREFIX = "awcv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowClonerV2State()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{datetime.now(timezone.utc).isoformat()}"
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

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = value

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Fire callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        """Invoke on_change and all registered callbacks; exceptions are silently ignored."""
        data: Dict[str, Any] = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Clone workflow (v2)
    # ------------------------------------------------------------------

    def clone_v2(
        self,
        agent_id: str,
        workflow_name: str,
        target: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Clone a workflow definition.

        Returns the clone record ID (``awcv-`` prefix), or ``""`` if
        *agent_id* or *workflow_name* is empty.
        """
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "target": target,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("clone_v2", agent_id=agent_id, record_id=record_id)
        logger.debug(
            "Workflow cloned (v2): %s agent=%s workflow=%s target=%s",
            record_id, agent_id, workflow_name, target,
        )
        return record_id

    # ------------------------------------------------------------------
    # Get clone by ID
    # ------------------------------------------------------------------

    def get_clone(self, record_id: str) -> Optional[dict]:
        """Get a clone record by its ID. Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    # ------------------------------------------------------------------
    # Get clones (query)
    # ------------------------------------------------------------------

    def get_clones(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query clone records, newest first.

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
        return [copy.deepcopy(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get clone count
    # ------------------------------------------------------------------

    def get_clone_count(self, agent_id: str = "") -> int:
        """Return the number of clone records, optionally filtered by *agent_id*."""
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
            "total_clones": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowClonerV2State()
        self._on_change = None
        logger.debug("AgentWorkflowClonerV2 reset")
