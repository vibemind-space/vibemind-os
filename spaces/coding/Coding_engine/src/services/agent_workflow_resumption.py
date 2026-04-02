"""Agent Workflow Resumption -- tracks workflow resumptions for agents.

Stores resumption records when agents resume previously paused or interrupted
workflows.  Each record captures the agent, workflow name, checkpoint, and
optional metadata.  When the store exceeds ``MAX_ENTRIES`` the oldest quarter
of entries is pruned automatically.

Uses SHA-256-based IDs with an ``awrs-`` prefix.
"""

from __future__ import annotations

import copy, hashlib, logging, time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowResumptionState:
    """Internal store for workflow resumption entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowResumption:
    """Tracks workflow resumptions for agents.

    Each resumption record tracks which agent resumed which workflow, along
    with the checkpoint, and optional metadata.  Records can be queried by
    agent.
    """

    PREFIX = "awrs-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowResumptionState()
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

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke on_change and all registered callbacks; exceptions are logged."""
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.debug("on_change callback failed for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.debug("Callback failed for action=%s", action)

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
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Resume workflow
    # ------------------------------------------------------------------

    def resume_workflow(
        self,
        agent_id: str,
        workflow_name: str,
        checkpoint: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a workflow resumption.

        Returns the record ID (``awrs-`` prefix) on success, or ``""`` on
        failure (e.g. empty *agent_id* or *workflow_name*).
        """
        try:
            if not agent_id or not workflow_name:
                return ""

            record_id = self._generate_id()
            now = time.time()

            entry: Dict[str, Any] = {
                "record_id": record_id,
                "agent_id": agent_id,
                "workflow_name": workflow_name,
                "checkpoint": checkpoint,
                "metadata": copy.deepcopy(metadata) if metadata else {},
                "created_at": now,
                "_seq": self._state._seq,
            }
            self._state.entries[record_id] = entry
            self._prune()
            self._fire("resumed", entry)
            logger.debug(
                "Workflow resumed: %s agent=%s workflow=%s checkpoint=%s",
                record_id, agent_id, workflow_name, checkpoint,
            )
            return record_id
        except Exception:
            logger.exception("Failed to resume workflow")
            return ""

    # ------------------------------------------------------------------
    # Get resumption by ID
    # ------------------------------------------------------------------

    def get_resumption(self, record_id: str) -> Optional[dict]:
        """Get a resumption record by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get resumptions (query)
    # ------------------------------------------------------------------

    def get_resumptions(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query resumption records, newest first.

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
    # Get resumption count
    # ------------------------------------------------------------------

    def get_resumption_count(self, agent_id: str = "") -> int:
        """Return the number of resumption records, optionally filtered by *agent_id*."""
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
        """Return operational statistics for the resumption service."""
        total = len(self._state.entries)
        agents = set(e["agent_id"] for e in self._state.entries.values())
        return {
            "total_resumptions": total,
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored resumption records, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        self._on_change = None
