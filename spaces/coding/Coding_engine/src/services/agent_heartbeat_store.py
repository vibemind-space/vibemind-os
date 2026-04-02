"""Agent Heartbeat Store – tracks agent heartbeats for liveness detection.

Provides per-agent heartbeat registration with configurable intervals,
liveness checking based on last-beat timestamps, dead-agent detection,
and status reporting for monitoring agent health.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HeartbeatEntry:
    entry_id: str
    agent_id: str
    last_beat: float
    interval_seconds: float
    status: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class AgentHeartbeatStore:
    """Tracks agent heartbeats for liveness detection with configurable timeouts."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._entries: Dict[str, HeartbeatEntry] = {}
        self._lookup: Dict[str, str] = {}  # agent_id -> entry_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_registers = 0
        self._total_beats = 0
        self._total_checks = 0
        self._total_unregisters = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"ahb-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ahb-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._entries) < self._max_entries:
            return
        sorted_ids = sorted(
            self._entries.keys(),
            key=lambda eid: self._entries[eid].seq,
        )
        to_remove = len(self._entries) - self._max_entries + 1
        for eid in sorted_ids[:to_remove]:
            entry = self._entries[eid]
            self._lookup.pop(entry.agent_id, None)
            del self._entries[eid]
            logger.debug("heartbeat_entry_pruned", entry_id=eid, agent_id=entry.agent_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_dict(self, entry: HeartbeatEntry) -> Dict[str, Any]:
        now = time.time()
        alive = (now - entry.last_beat) <= entry.interval_seconds
        return {
            "entry_id": entry.entry_id,
            "agent_id": entry.agent_id,
            "last_beat": entry.last_beat,
            "interval_seconds": entry.interval_seconds,
            "status": entry.status,
            "metadata": dict(entry.metadata),
            "created_at": entry.created_at,
            "alive": alive,
        }

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def register(
        self,
        agent_id: str,
        interval_seconds: float = 30,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register an agent for heartbeat tracking. Returns entry_id, or '' if duplicate."""
        if not agent_id:
            logger.warning("heartbeat_register_empty_agent_id")
            return ""

        if agent_id in self._lookup:
            logger.debug("heartbeat_register_duplicate", agent_id=agent_id)
            return ""

        self._prune_if_needed()
        now = time.time()
        entry_id = self._gen_id(agent_id)
        entry = HeartbeatEntry(
            entry_id=entry_id,
            agent_id=agent_id,
            last_beat=now,
            interval_seconds=interval_seconds,
            status="alive",
            metadata=dict(metadata) if metadata else {},
            created_at=now,
            seq=self._seq,
        )
        self._entries[entry_id] = entry
        self._lookup[agent_id] = entry_id
        self._total_registers += 1
        logger.debug(
            "heartbeat_registered", agent_id=agent_id, entry_id=entry_id,
            interval_seconds=interval_seconds,
        )
        self._fire("heartbeat_registered", {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "interval_seconds": interval_seconds,
        })
        return entry_id

    def beat(self, agent_id: str) -> bool:
        """Record a heartbeat for an agent. Returns True on success."""
        if not agent_id:
            return False

        eid = self._lookup.get(agent_id)
        if not eid or eid not in self._entries:
            logger.debug("heartbeat_beat_unknown_agent", agent_id=agent_id)
            return False

        entry = self._entries[eid]
        now = time.time()
        old_status = entry.status
        entry.last_beat = now
        entry.status = "alive"
        self._seq += 1
        entry.seq = self._seq
        self._total_beats += 1
        logger.debug("heartbeat_beat", agent_id=agent_id)
        if old_status != "alive":
            self._fire("heartbeat_revived", {
                "entry_id": eid,
                "agent_id": agent_id,
                "old_status": old_status,
            })
        self._fire("heartbeat_beat", {
            "entry_id": eid,
            "agent_id": agent_id,
        })
        return True

    def check_alive(self, agent_id: str) -> bool:
        """Check whether an agent is alive (last beat within interval)."""
        if not agent_id:
            return False

        self._total_checks += 1
        eid = self._lookup.get(agent_id)
        if not eid or eid not in self._entries:
            return False

        entry = self._entries[eid]
        now = time.time()
        alive = (now - entry.last_beat) <= entry.interval_seconds
        if alive and entry.status != "alive":
            entry.status = "alive"
        elif not alive and entry.status != "dead":
            entry.status = "dead"
            self._fire("heartbeat_dead", {
                "entry_id": eid,
                "agent_id": agent_id,
            })
        return alive

    def get_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get heartbeat status for an agent. Returns None if not registered."""
        if not agent_id:
            return None

        eid = self._lookup.get(agent_id)
        if not eid or eid not in self._entries:
            return None

        entry = self._entries[eid]
        # Refresh status on read
        now = time.time()
        alive = (now - entry.last_beat) <= entry.interval_seconds
        entry.status = "alive" if alive else "dead"
        return self._to_dict(entry)

    def get_dead_agents(self) -> List[str]:
        """Return list of agent_ids whose last beat is past their interval."""
        now = time.time()
        dead: List[str] = []
        for entry in self._entries.values():
            if (now - entry.last_beat) > entry.interval_seconds:
                entry.status = "dead"
                dead.append(entry.agent_id)
        return sorted(dead)

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        """Return status dicts for all registered agents."""
        now = time.time()
        result: List[Dict[str, Any]] = []
        for entry in self._entries.values():
            alive = (now - entry.last_beat) <= entry.interval_seconds
            entry.status = "alive" if alive else "dead"
            result.append(self._to_dict(entry))
        return result

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent from heartbeat tracking."""
        if not agent_id:
            return False

        eid = self._lookup.get(agent_id)
        if not eid or eid not in self._entries:
            return False

        entry = self._entries[eid]
        del self._entries[eid]
        del self._lookup[agent_id]
        self._total_unregisters += 1
        logger.debug("heartbeat_unregistered", agent_id=agent_id, entry_id=eid)
        self._fire("heartbeat_unregistered", {
            "entry_id": eid,
            "agent_id": agent_id,
        })
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        alive_count = sum(
            1 for e in self._entries.values()
            if (now - e.last_beat) <= e.interval_seconds
        )
        dead_count = len(self._entries) - alive_count
        return {
            "current_entries": len(self._entries),
            "alive_agents": alive_count,
            "dead_agents": dead_count,
            "total_registers": self._total_registers,
            "total_beats": self._total_beats,
            "total_checks": self._total_checks,
            "total_unregisters": self._total_unregisters,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._lookup.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registers = 0
        self._total_beats = 0
        self._total_checks = 0
        self._total_unregisters = 0
        logger.debug("agent_heartbeat_store_reset")
