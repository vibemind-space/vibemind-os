"""Agent Heartbeat Tracker -- tracks agent heartbeats and detects unresponsive agents.

Maintains a registry of agents with configurable heartbeat intervals.
Agents that fail to send a heartbeat within their configured interval
are considered unresponsive.  Provides query methods for responsiveness
checks, missed-interval counts, and filtered agent listings.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _TrackerEntry:
    """Internal state for a single tracked agent."""

    tracker_id: str
    agent_id: str
    interval_seconds: float
    last_heartbeat: float
    heartbeat_count: int
    missed_count: int
    created_at: float = field(default_factory=time.time)
    seq: int = 0


# ---------------------------------------------------------------------------
# AgentHeartbeatTracker
# ---------------------------------------------------------------------------

class AgentHeartbeatTracker:
    """Tracks agent heartbeats and detects unresponsive agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._agents: Dict[str, _TrackerEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

        # cumulative stats
        self._total_registered: int = 0
        self._total_heartbeats: int = 0
        self._total_unresponsive: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"aht-{digest}"

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, interval_seconds: float = 30.0) -> str:
        """Register an agent for heartbeat tracking.

        Returns the tracker ID (``aht-...``), or empty string on failure.
        """
        if not agent_id or interval_seconds <= 0:
            logger.warning(
                "register_agent.invalid_input",
                agent_id=agent_id,
                interval_seconds=interval_seconds,
            )
            return ""
        if agent_id in self._agents:
            logger.debug("register_agent.already_registered", agent_id=agent_id)
            return ""
        if len(self._agents) >= self._max_entries:
            logger.warning("register_agent.capacity_reached", max_entries=self._max_entries)
            return ""

        tracker_id = self._make_id(agent_id)
        now = time.time()
        entry = _TrackerEntry(
            tracker_id=tracker_id,
            agent_id=agent_id,
            interval_seconds=interval_seconds,
            last_heartbeat=now,
            heartbeat_count=0,
            missed_count=0,
            created_at=now,
            seq=self._seq,
        )
        self._agents[agent_id] = entry
        self._total_registered += 1
        logger.info(
            "register_agent.ok",
            agent_id=agent_id,
            tracker_id=tracker_id,
            interval_seconds=interval_seconds,
        )
        self._fire("agent_registered", {"tracker_id": tracker_id, "agent_id": agent_id})
        return tracker_id

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def record_heartbeat(self, agent_id: str) -> bool:
        """Record a heartbeat from the given agent.

        Returns True if the agent is registered, False otherwise.
        """
        entry = self._agents.get(agent_id)
        if not entry:
            logger.debug("record_heartbeat.unknown_agent", agent_id=agent_id)
            return False

        now = time.time()
        was_responsive = self._check_responsive(entry, now)

        entry.last_heartbeat = now
        entry.heartbeat_count += 1
        entry.missed_count = 0
        self._total_heartbeats += 1

        if not was_responsive:
            logger.info("record_heartbeat.agent_recovered", agent_id=agent_id)
            self._fire("agent_recovered", {"agent_id": agent_id, "tracker_id": entry.tracker_id})

        self._fire("heartbeat_recorded", {"agent_id": agent_id, "tracker_id": entry.tracker_id})
        return True

    # ------------------------------------------------------------------
    # Responsiveness
    # ------------------------------------------------------------------

    @staticmethod
    def _check_responsive(entry: _TrackerEntry, now: float | None = None) -> bool:
        now = now or time.time()
        return (now - entry.last_heartbeat) < entry.interval_seconds

    def is_responsive(self, agent_id: str) -> bool:
        """Return True if the agent's last heartbeat is within its interval."""
        entry = self._agents.get(agent_id)
        if not entry:
            return False
        return self._check_responsive(entry)

    def get_last_heartbeat(self, agent_id: str) -> Optional[float]:
        """Return the timestamp of the last heartbeat, or None if not found."""
        entry = self._agents.get(agent_id)
        if not entry:
            return None
        return entry.last_heartbeat

    def get_missed_count(self, agent_id: str) -> int:
        """Return the number of missed heartbeat intervals for the agent.

        A missed interval is counted each time a full ``interval_seconds``
        window elapses without a heartbeat.
        """
        entry = self._agents.get(agent_id)
        if not entry:
            return 0
        now = time.time()
        elapsed = now - entry.last_heartbeat
        if elapsed < entry.interval_seconds:
            return 0
        return int(elapsed / entry.interval_seconds)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all registered agent IDs."""
        return list(self._agents.keys())

    def get_responsive_agents(self) -> List[str]:
        """Return only agent IDs whose heartbeat is within their interval."""
        now = time.time()
        return [
            aid for aid, entry in self._agents.items()
            if self._check_responsive(entry, now)
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

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given event and data."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("_fire.callback_error", callback=cb_name, event=event)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics as a dict."""
        now = time.time()
        responsive = sum(1 for e in self._agents.values() if self._check_responsive(e, now))
        return {
            "registered_agents": len(self._agents),
            "responsive_agents": responsive,
            "unresponsive_agents": len(self._agents) - responsive,
            "total_registered": self._total_registered,
            "total_heartbeats": self._total_heartbeats,
            "total_unresponsive": self._total_unresponsive,
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
        self._total_unresponsive = 0
        logger.info("reset.ok")
