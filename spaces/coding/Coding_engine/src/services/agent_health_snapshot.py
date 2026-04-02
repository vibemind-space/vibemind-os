"""Agent health snapshot service.

Takes, retrieves, and compares point-in-time health snapshots for agents.
Stores per-agent snapshot histories with SHA-256-based IDs (``ahs-`` prefix),
automatic pruning, and change-notification callbacks.
"""

from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the snapshot service."""

    snapshots: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent Health Snapshot
# ---------------------------------------------------------------------------

class AgentHealthSnapshot:
    """Takes, stores, and compares agent health snapshots."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = _State()
        self._max_entries = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix ``ahs-``."""
        self._state._seq += 1
        raw = f"{seed}:{time.time()}:{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ahs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._state.snapshots) <= self._max_entries:
            return
        sorted_entries = sorted(
            self._state.snapshots.values(), key=lambda e: e["timestamp"]
        )
        remove_count = len(self._state.snapshots) - self._max_entries
        for entry in sorted_entries[:remove_count]:
            del self._state.snapshots[entry["snapshot_id"]]
            logger.debug("snapshot_pruned", snapshot_id=entry["snapshot_id"])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns ``True`` if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *detail*."""
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.warning(
                    "callback_error", callback=cb_name, action=action
                )

    # ------------------------------------------------------------------
    # Take snapshot
    # ------------------------------------------------------------------

    def take_snapshot(self, agent_id: str, health_data: dict) -> str:
        """Take a health snapshot for an agent.

        Returns the snapshot ID (``ahs-`` prefix).
        """
        self._prune_if_needed()
        snapshot_id = self._next_id(agent_id)
        now = time.time()

        entry = {
            "snapshot_id": snapshot_id,
            "agent_id": agent_id,
            "health_data": copy.deepcopy(health_data),
            "timestamp": now,
            "_seq_num": self._state._seq,
        }
        self._state.snapshots[snapshot_id] = entry

        logger.debug(
            "snapshot_taken", snapshot_id=snapshot_id, agent_id=agent_id
        )
        self._fire("snapshot_taken", copy.deepcopy(entry))
        return snapshot_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Get a snapshot by ID. Returns dict or ``None``."""
        entry = self._state.snapshots.get(snapshot_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_snapshots(self, agent_id: str) -> List[dict]:
        """Get all snapshots for an agent, most recent first."""
        candidates = sorted(
            (
                e
                for e in self._state.snapshots.values()
                if e["agent_id"] == agent_id
            ),
            key=lambda e: e["timestamp"],
            reverse=True,
        )
        return [copy.deepcopy(e) for e in candidates]

    def get_latest_snapshot(self, agent_id: str) -> Optional[dict]:
        """Get the most recent snapshot for an agent. Returns ``None`` if empty."""
        candidates = [
            e
            for e in self._state.snapshots.values()
            if e["agent_id"] == agent_id
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda e: (e["timestamp"], e.get("_seq_num", 0)))
        return copy.deepcopy(latest)

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def compare_snapshots(
        self, snapshot_id_a: str, snapshot_id_b: str
    ) -> dict:
        """Compare two snapshots by their *health_data* keys.

        Returns ``{"changes": {key: {"old": v1, "new": v2}}}`` for keys
        that differ between the two snapshots. Returns an empty changes
        dict if either snapshot is not found.
        """
        entry_a = self._state.snapshots.get(snapshot_id_a)
        entry_b = self._state.snapshots.get(snapshot_id_b)
        if entry_a is None or entry_b is None:
            return {"changes": {}}

        data_a = entry_a["health_data"]
        data_b = entry_b["health_data"]

        changes: Dict[str, Dict[str, Any]] = {}
        all_keys = set(data_a.keys()) | set(data_b.keys())
        for key in sorted(all_keys):
            old_val = data_a.get(key)
            new_val = data_b.get(key)
            if old_val != new_val:
                changes[key] = {"old": old_val, "new": new_val}

        return {"changes": changes}

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_snapshot_count(self, agent_id: str = "") -> int:
        """Return snapshot count, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.snapshots)
        return sum(
            1
            for e in self._state.snapshots.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # List agents
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return a sorted list of agent IDs that have at least one snapshot."""
        agents = {e["agent_id"] for e in self._state.snapshots.values()}
        return sorted(agents)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the snapshot service."""
        agent_counts: Dict[str, int] = {}
        for entry in self._state.snapshots.values():
            aid = entry["agent_id"]
            agent_counts[aid] = agent_counts.get(aid, 0) + 1
        return {
            "current_snapshots": len(self._state.snapshots),
            "max_entries": self._max_entries,
            "by_agent": dict(sorted(agent_counts.items())),
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored snapshots, callbacks, and reset counters."""
        self._state.snapshots.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
        logger.debug("store_reset")
