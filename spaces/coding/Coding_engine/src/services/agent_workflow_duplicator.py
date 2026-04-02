"""Agent Workflow Duplicator -- duplicates agent workflow executions.

Stores duplication records for agent workflows.  Each record captures the
agent, workflow name, number of copies, and optional metadata.  When the
store exceeds ``MAX_ENTRIES`` the oldest quarter of entries is pruned
automatically.

Uses SHA-256-based IDs with an ``awdu-`` prefix.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowDuplicatorState:
    """Internal store for workflow duplication entries."""

    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowDuplicator:
    """Duplicates workflow executions for agents.

    Each duplication record tracks which agent duplicated which workflow,
    along with the number of copies and optional metadata.  Records can be
    queried by agent.
    """

    PREFIX = "awdu-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowDuplicatorState()
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

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Duplicate workflow
    # ------------------------------------------------------------------

    def duplicate(
        self,
        agent_id: str,
        workflow_name: str,
        copies: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Duplicate a workflow execution.

        Returns the record ID (``awdu-`` prefix), or ``""`` if *agent_id*
        or *workflow_name* is empty.
        """
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "copies": copies,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("duplicated", record_id=record_id, agent_id=agent_id,
                    workflow_name=workflow_name, copies=copies)
        logger.debug(
            "Workflow duplicated: %s agent=%s workflow=%s copies=%d",
            record_id, agent_id, workflow_name, copies,
        )
        return record_id

    # ------------------------------------------------------------------
    # Get duplication by ID
    # ------------------------------------------------------------------

    def get_duplication(self, record_id: str) -> Optional[dict]:
        """Get a duplication record by its ID.  Returns dict copy or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get duplications (query)
    # ------------------------------------------------------------------

    def get_duplications(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query duplication records, newest first.

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
    # Get duplication count
    # ------------------------------------------------------------------

    def get_duplication_count(self, agent_id: str = "") -> int:
        """Return the number of duplication records, optionally filtered by *agent_id*."""
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
        """Return operational statistics for the duplicator service."""
        total = len(self._state.entries)
        agents = set(e["agent_id"] for e in self._state.entries.values())
        return {
            "total_duplications": total,
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored duplication records, callbacks, and reset counters."""
        self._state = AgentWorkflowDuplicatorState()
        self._on_change = None
