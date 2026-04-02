"""Agent State Snapshot – creates, retrieves, compares, and restores
snapshots of agent states.

Provides point-in-time capture of agent state with snapshot comparison,
restoration tracking, change-notification callbacks, and automatic pruning.
Uses SHA-256-based IDs with an ``asn-`` prefix.
"""

from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SnapshotEntry:
    """A single captured agent state snapshot."""

    snapshot_id: str = ""
    agent_id: str = ""
    state_data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    restored: bool = False
    seq: int = 0


class AgentStateSnapshot:
    """Manages point-in-time snapshots of agent state.

    Supports creating, retrieving, comparing, and restoring snapshots
    with automatic pruning when the store exceeds *max_entries*.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._snapshots: Dict[str, SnapshotEntry] = {}
        self._callbacks: Dict[str, Any] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"asn-{self._seq}-{id(self)}"
        return "asn-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict the oldest entries when the store exceeds *max_entries*."""
        if len(self._snapshots) <= self._max_entries:
            return
        sorted_entries = sorted(
            self._snapshots.values(), key=lambda e: e.created_at
        )
        remove_count = len(self._snapshots) - self._max_entries
        for entry in sorted_entries[:remove_count]:
            del self._snapshots[entry.snapshot_id]

    def _entry_to_dict(self, entry: SnapshotEntry) -> Dict[str, Any]:
        """Convert a *SnapshotEntry* to a plain dictionary."""
        return {
            "snapshot_id": entry.snapshot_id,
            "agent_id": entry.agent_id,
            "state_data": copy.deepcopy(entry.state_data),
            "created_at": entry.created_at,
            "restored": entry.restored,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> None:
        """Register a named change-notification callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently ignored."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Create snapshot
    # ------------------------------------------------------------------

    def create_snapshot(self, agent_id: str, state_data: dict) -> str:
        """Create a snapshot of the agent state.

        Returns the snapshot ID (``asn-`` prefix).
        """
        self._prune_if_needed()
        snapshot_id = self._generate_id()
        now = time.time()

        entry = SnapshotEntry(
            snapshot_id=snapshot_id,
            agent_id=agent_id,
            state_data=copy.deepcopy(state_data),
            created_at=now,
            restored=False,
            seq=self._seq,
        )
        self._snapshots[snapshot_id] = entry
        self._fire("snapshot_created", self._entry_to_dict(entry))
        return snapshot_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Get snapshot by ID.  Returns dict or ``None``."""
        entry = self._snapshots.get(snapshot_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    def get_agent_snapshots(self, agent_id: str) -> List[Dict[str, Any]]:
        """List snapshots for an agent, most recent first."""
        candidates = sorted(
            (e for e in self._snapshots.values() if e.agent_id == agent_id),
            key=lambda e: (e.created_at, e.seq),
            reverse=True,
        )
        return [self._entry_to_dict(e) for e in candidates]

    def get_latest_snapshot(self, agent_id: str) -> Optional[dict]:
        """Get the most recent snapshot for an agent.  Returns ``None`` if empty."""
        candidates = [
            e for e in self._snapshots.values() if e.agent_id == agent_id
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda e: (e.created_at, e.seq))
        return self._entry_to_dict(latest)

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def compare_snapshots(
        self, snapshot_id_1: str, snapshot_id_2: str
    ) -> dict:
        """Compare two snapshots by their *state_data* keys.

        Returns ``{"added": [...], "removed": [...], "changed": [...]}``.
        Returns an empty diff if either snapshot is not found.
        """
        entry_1 = self._snapshots.get(snapshot_id_1)
        entry_2 = self._snapshots.get(snapshot_id_2)
        if entry_1 is None or entry_2 is None:
            return {"added": [], "removed": [], "changed": []}

        data_1 = entry_1.state_data
        data_2 = entry_2.state_data

        added: List[str] = []
        removed: List[str] = []
        changed: List[str] = []

        all_keys = set(data_1.keys()) | set(data_2.keys())
        for key in sorted(all_keys):
            in_1 = key in data_1
            in_2 = key in data_2
            if in_1 and not in_2:
                removed.append(key)
            elif not in_1 and in_2:
                added.append(key)
            elif data_1[key] != data_2[key]:
                changed.append(key)

        return {"added": added, "removed": removed, "changed": changed}

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Mark a snapshot as restored.

        Returns ``True`` if the snapshot was found and marked, ``False`` otherwise.
        """
        entry = self._snapshots.get(snapshot_id)
        if entry is None:
            return False
        entry.restored = True
        self._fire("snapshot_restored", {"snapshot_id": snapshot_id})
        return True

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot by ID.  Returns ``False`` if not found."""
        entry = self._snapshots.pop(snapshot_id, None)
        if entry is None:
            return False
        self._fire("snapshot_deleted", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_snapshot_count(self) -> int:
        """Return the total number of stored snapshots."""
        return len(self._snapshots)

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, agent_id: str) -> int:
        """Remove all snapshots for an agent.

        Returns the number of snapshots deleted.
        """
        to_remove = [
            sid
            for sid, e in self._snapshots.items()
            if e.agent_id == agent_id
        ]
        for sid in to_remove:
            del self._snapshots[sid]
        count = len(to_remove)
        if count:
            self._fire(
                "snapshots_purged",
                {"agent_id": agent_id, "count": count},
            )
        return count

    # ------------------------------------------------------------------
    # List agents
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return a sorted list of agent IDs that have at least one snapshot."""
        agents = {e.agent_id for e in self._snapshots.values()}
        return sorted(agents)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the snapshot service."""
        agent_counts: Dict[str, int] = {}
        for entry in self._snapshots.values():
            agent_counts[entry.agent_id] = (
                agent_counts.get(entry.agent_id, 0) + 1
            )
        restored_count = sum(
            1 for e in self._snapshots.values() if e.restored
        )
        return {
            "current_snapshots": len(self._snapshots),
            "max_entries": self._max_entries,
            "restored_count": restored_count,
            "by_agent": dict(sorted(agent_counts.items())),
            "registered_callbacks": len(self._callbacks),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored snapshots, callbacks, and reset counters."""
        self._snapshots.clear()
        self._callbacks.clear()
        self._seq = 0
