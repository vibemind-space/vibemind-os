"""Agent Heartbeat Monitor -- monitors agent liveness via heartbeat signals.

Tracks registered agents by expecting periodic heartbeat signals within
a configurable timeout window.  Agents that fail to heartbeat within
their timeout are considered dead.  Supports change callbacks and
per-agent timeout configuration.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _HeartbeatEntry:
    """Internal state for a single monitored agent."""

    entry_id: str
    agent_id: str
    timeout: float
    last_heartbeat: float
    heartbeat_count: int
    missed_count: int
    created_at: float = field(default_factory=time.time)
    seq: int = 0


# ---------------------------------------------------------------------------
# AgentHeartbeatMonitor
# ---------------------------------------------------------------------------

class AgentHeartbeatMonitor:
    """Monitors agent liveness via heartbeat signals with configurable timeout."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._agents: Dict[str, _HeartbeatEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

        # cumulative stats
        self._total_registered: int = 0
        self._total_heartbeats: int = 0
        self._total_expired: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{uuid.uuid4().hex}{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ahm-{digest}"

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, timeout: float = 30.0) -> str:
        """Register an agent for heartbeat monitoring.

        Returns the entry ID, or empty string on failure.
        """
        if not agent_id or timeout <= 0:
            logger.warning("register_agent.invalid_input", agent_id=agent_id, timeout=timeout)
            return ""
        if agent_id in self._agents:
            logger.debug("register_agent.already_registered", agent_id=agent_id)
            return ""
        if len(self._agents) >= self._max_entries:
            logger.warning("register_agent.capacity_reached", max_entries=self._max_entries)
            return ""

        entry_id = self._make_id(agent_id)
        now = time.time()
        entry = _HeartbeatEntry(
            entry_id=entry_id,
            agent_id=agent_id,
            timeout=timeout,
            last_heartbeat=now,
            heartbeat_count=0,
            missed_count=0,
            created_at=now,
            seq=self._seq,
        )
        self._agents[agent_id] = entry
        self._total_registered += 1
        logger.info("register_agent.ok", agent_id=agent_id, entry_id=entry_id, timeout=timeout)
        self._fire("agent_registered", {"entry_id": entry_id, "agent_id": agent_id})
        return entry_id

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def heartbeat(self, agent_id: str) -> bool:
        """Record a heartbeat from the given agent.

        Returns True if the agent is registered, False otherwise.
        """
        entry = self._agents.get(agent_id)
        if not entry:
            logger.debug("heartbeat.unknown_agent", agent_id=agent_id)
            return False

        now = time.time()
        was_alive = self._is_alive(entry, now)

        entry.last_heartbeat = now
        entry.heartbeat_count += 1
        entry.missed_count = 0
        self._total_heartbeats += 1

        if not was_alive:
            logger.info("heartbeat.agent_revived", agent_id=agent_id)
            self._fire("agent_revived", {"agent_id": agent_id, "entry_id": entry.entry_id})

        self._fire("heartbeat_received", {"agent_id": agent_id, "entry_id": entry.entry_id})
        return True

    # ------------------------------------------------------------------
    # Liveness
    # ------------------------------------------------------------------

    @staticmethod
    def _is_alive(entry: _HeartbeatEntry, now: float | None = None) -> bool:
        now = now or time.time()
        return (now - entry.last_heartbeat) < entry.timeout

    def is_alive(self, agent_id: str) -> bool:
        """Return True if the agent's last heartbeat is within its timeout."""
        entry = self._agents.get(agent_id)
        if not entry:
            return False
        return self._is_alive(entry)

    def get_last_heartbeat(self, agent_id: str) -> float:
        """Return the timestamp of the last heartbeat, or 0.0 if not found."""
        entry = self._agents.get(agent_id)
        if not entry:
            return 0.0
        return entry.last_heartbeat

    def get_missed_count(self, agent_id: str) -> int:
        """Return the number of missed heartbeat intervals for the agent.

        A missed interval is counted each time a full ``timeout`` window
        elapses without a heartbeat.
        """
        entry = self._agents.get(agent_id)
        if not entry:
            return 0
        now = time.time()
        elapsed = now - entry.last_heartbeat
        if elapsed < entry.timeout:
            return 0
        return int(elapsed / entry.timeout)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all registered agent IDs."""
        return list(self._agents.keys())

    def get_alive_agents(self) -> List[str]:
        """Return only agent IDs whose heartbeat is within timeout."""
        now = time.time()
        return [
            aid for aid, entry in self._agents.items()
            if self._is_alive(entry, now)
        ]

    def get_agent_count(self) -> int:
        """Return the number of currently registered agents."""
        return len(self._agents)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback."""
        self._callbacks[name] = callback
        logger.debug("on_change.registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name."""
        removed = self._callbacks.pop(name, None) is not None
        if removed:
            logger.debug("remove_callback.ok", name=name)
        return removed

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("_fire.callback_error", callback=cb_name, action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics as a dict."""
        now = time.time()
        alive = sum(1 for e in self._agents.values() if self._is_alive(e, now))
        return {
            "registered_agents": len(self._agents),
            "alive_agents": alive,
            "dead_agents": len(self._agents) - alive,
            "total_registered": self._total_registered,
            "total_heartbeats": self._total_heartbeats,
            "total_expired": self._total_expired,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._agents.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_heartbeats = 0
        self._total_expired = 0
        logger.info("reset.ok")
