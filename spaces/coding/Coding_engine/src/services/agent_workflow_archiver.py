"""Agent Workflow Archiver -- archives completed workflow executions.

Stores archive records for finished agent workflows.  Each archive captures
the agent, workflow name, result, reason, and optional metadata.  When the
store exceeds ``MAX_ENTRIES`` the oldest quarter of entries is pruned
automatically.

Uses SHA-256-based IDs with an ``awar-`` prefix.
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
class AgentWorkflowArchiverState:
    """Internal store for workflow archive entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowArchiver:
    """Archives completed workflow executions for agents.

    Each archive record tracks which agent ran which workflow, along with the
    result, reason, and optional metadata.  Records can be queried by agent
    and/or workflow name.
    """

    PREFIX = "awar-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowArchiverState()
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
        """Remove the oldest quarter of entries when at capacity."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(),
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("seq", 0)),
        )
        remove_count = len(sorted_entries) // 4
        if remove_count < 1:
            remove_count = 1
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
    # Archive workflow
    # ------------------------------------------------------------------

    def archive_workflow(
        self,
        agent_id: str,
        workflow_name: str,
        result: str,
        reason: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Archive a completed workflow execution.

        Returns the archive ID (``awar-`` prefix).
        """
        archive_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "archive_id": archive_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "result": result,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[archive_id] = entry
        self._prune()
        self._fire("archived", entry)
        logger.debug(
            "Workflow archived: %s agent=%s workflow=%s reason=%s",
            archive_id, agent_id, workflow_name, reason,
        )
        return archive_id

    # ------------------------------------------------------------------
    # Get archived workflow by ID
    # ------------------------------------------------------------------

    def get_archived_workflow(self, archive_id: str) -> Optional[dict]:
        """Get an archive record by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(archive_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get archived workflows (query)
    # ------------------------------------------------------------------

    def get_archived_workflows(
        self,
        agent_id: str = "",
        workflow_name: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query archive records, newest first.

        Optionally filter by *agent_id* and/or *workflow_name* and cap
        results with *limit*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if (not agent_id or e["agent_id"] == agent_id)
            and (not workflow_name or e["workflow_name"] == workflow_name)
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get archive count
    # ------------------------------------------------------------------

    def get_archive_count(self, agent_id: str = "") -> int:
        """Return the number of archive records, optionally filtered by *agent_id*."""
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
        """Return operational statistics for the archiver service."""
        total = len(self._state.entries)
        agents = set(e["agent_id"] for e in self._state.entries.values())
        workflows = set(e["workflow_name"] for e in self._state.entries.values())
        reasons: Dict[str, int] = {}
        for e in self._state.entries.values():
            r = e["reason"]
            reasons[r] = reasons.get(r, 0) + 1
        return {
            "total_archived": total,
            "unique_agents": len(agents),
            "unique_workflows": len(workflows),
            "reasons": reasons,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored archive records, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
