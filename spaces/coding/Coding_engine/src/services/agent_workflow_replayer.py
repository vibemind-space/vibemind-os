"""Agent Workflow Replayer – records and replays workflow execution sequences.

Captures workflow execution steps for later replay and analysis.  Supports
querying by agent and workflow name, counting replays, and collecting
statistics.  Uses SHA-256-based IDs with an ``awrp-`` prefix.
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
class AgentWorkflowReplayerState:
    """Internal store for workflow replay entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowReplayer:
    """Records and replays workflow execution sequences.

    Supports recording execution steps, retrieving replays, filtering by
    agent and workflow, and automatic pruning when the store exceeds
    *MAX_ENTRIES*.
    """

    PREFIX = "awrp-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowReplayerState()
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
        """Evict the oldest quarter of entries when the store exceeds *MAX_ENTRIES*."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(), key=lambda kv: kv[1].get("created_at", 0)
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
    # Record
    # ------------------------------------------------------------------

    def record(
        self,
        agent_id: str,
        workflow_name: str,
        steps_data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a workflow execution sequence for later replay.

        Returns the replay ID (``awrp-`` prefix).
        """
        self._prune()
        replay_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "replay_id": replay_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "steps_data": copy.deepcopy(steps_data),
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[replay_id] = entry
        self._fire("replay_recorded", entry)
        logger.debug(
            "Replay recorded: %s for agent=%s workflow=%s",
            replay_id,
            agent_id,
            workflow_name,
        )
        return replay_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_replay(self, replay_id: str) -> Optional[dict]:
        """Get a replay by ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(replay_id)
        if entry is None:
            return None
        return dict(entry)

    def get_replays(
        self,
        agent_id: str = "",
        workflow_name: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query replays, newest first.

        Optionally filter by *agent_id* and/or *workflow_name*.  Returns at
        most *limit* results.
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
    # Count
    # ------------------------------------------------------------------

    def get_replay_count(self, agent_id: str = "") -> int:
        """Return the number of stored replays, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the replayer service."""
        agents: set = set()
        workflows: set = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
            workflows.add(entry["workflow_name"])
        return {
            "total_replays": len(self._state.entries),
            "unique_agents": len(agents),
            "unique_workflows": len(workflows),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored replays, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
