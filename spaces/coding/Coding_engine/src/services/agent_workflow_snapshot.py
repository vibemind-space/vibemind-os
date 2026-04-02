"""Agent Workflow Snapshot – takes point-in-time snapshots of agent workflow
state for debugging and auditing.

Captures workflow state at a given moment, supports querying by agent and
workflow name, comparing snapshots, and collecting statistics.
Uses SHA-256-based IDs with an ``awss-`` prefix.
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
class AgentWorkflowSnapshotState:
    """Internal store for workflow snapshot entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowSnapshot:
    """Manages point-in-time snapshots of agent workflow state.

    Supports creating, retrieving, comparing, and removing snapshots
    with automatic pruning when the store exceeds *MAX_ENTRIES*.
    """

    PREFIX = "awss-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowSnapshotState()
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
    # Take snapshot
    # ------------------------------------------------------------------

    def take_snapshot(
        self,
        agent_id: str,
        workflow_name: str,
        state: dict,
        label: str = "",
    ) -> str:
        """Take a point-in-time snapshot of agent workflow state.

        Returns the snapshot ID (``awss-`` prefix).
        """
        self._prune()
        snapshot_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "state": copy.deepcopy(state),
            "label": label,
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[snapshot_id] = entry
        self._fire("snapshot_taken", entry)
        logger.debug("Snapshot taken: %s for agent=%s workflow=%s", snapshot_id, agent_id, workflow_name)
        return snapshot_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Get snapshot by ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(snapshot_id)
        if entry is None:
            return None
        return dict(entry)

    def get_snapshots(
        self,
        agent_id: str,
        workflow_name: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query snapshots for an agent, newest first.

        Optionally filter by *workflow_name*.  Returns at most *limit* results.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if e["agent_id"] == agent_id
            and (not workflow_name or e["workflow_name"] == workflow_name)
        ]
        candidates.sort(key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True)
        return [dict(c) for c in candidates[:limit]]

    def get_latest_snapshot(
        self, agent_id: str, workflow_name: str
    ) -> Optional[dict]:
        """Get the most recent snapshot for an agent+workflow.

        Returns ``None`` if no matching snapshot exists.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["workflow_name"] == workflow_name
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda e: (e.get("created_at", 0), e.get("seq", 0)))
        return dict(latest)

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def compare_snapshots(
        self, snapshot_id_a: str, snapshot_id_b: str
    ) -> dict:
        """Compare two snapshots by their *state* keys.

        Returns ``{"added": [...], "removed": [...], "changed": [...]}``.
        Returns an empty diff if either snapshot is not found.
        """
        entry_a = self._state.entries.get(snapshot_id_a)
        entry_b = self._state.entries.get(snapshot_id_b)
        if entry_a is None or entry_b is None:
            return {"added": [], "removed": [], "changed": []}

        state_a = entry_a.get("state", {})
        state_b = entry_b.get("state", {})

        added: List[str] = []
        removed: List[str] = []
        changed: List[str] = []

        all_keys = set(state_a.keys()) | set(state_b.keys())
        for key in sorted(all_keys):
            in_a = key in state_a
            in_b = key in state_b
            if in_a and not in_b:
                removed.append(key)
            elif not in_a and in_b:
                added.append(key)
            elif state_a[key] != state_b[key]:
                changed.append(key)

        return {"added": added, "removed": removed, "changed": changed}

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_snapshot_count(self, agent_id: str = "") -> int:
        """Return the number of stored snapshots, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def remove_snapshot(self, snapshot_id: str) -> bool:
        """Remove a snapshot by ID.  Returns ``False`` if not found."""
        entry = self._state.entries.pop(snapshot_id, None)
        if entry is None:
            return False
        self._fire("snapshot_removed", entry)
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the snapshot service."""
        agents = set()
        workflows = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
            workflows.add(entry["workflow_name"])
        return {
            "total_snapshots": len(self._state.entries),
            "unique_agents": len(agents),
            "unique_workflows": len(workflows),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored snapshots, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
