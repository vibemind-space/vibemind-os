"""Agent fault detector.

Detects agent faults based on error rate and consecutive failures.
Monitors registered agents, tracks success/failure outcomes, and
determines whether an agent should be considered faulty.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _AgentEntry:
    """A tracked agent entry."""
    entry_id: str = ""
    agent_id: str = ""
    error_threshold: float = 0.5
    max_consecutive_failures: int = 3
    total_successes: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    last_failure_reason: str = ""
    created_at: float = 0.0
    seq: int = 0


class AgentFaultDetector:
    """Detects agent faults based on error rate and consecutive failures."""

    def __init__(self, max_entries: int = 100000):
        self._agents: Dict[str, _AgentEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._max_entries = max_entries
        self._stats = {
            "total_registered": 0,
            "total_successes": 0,
            "total_failures": 0,
            "total_resets": 0,
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str,
                       error_threshold: float = 0.5,
                       max_consecutive_failures: int = 3) -> str:
        """Register an agent for fault detection. Returns entry ID."""
        if not agent_id:
            return ""
        if agent_id in self._agents:
            return self._agents[agent_id].entry_id
        if len(self._agents) >= self._max_entries:
            return ""

        self._seq += 1
        entry_id = "afd2-" + hashlib.sha256(
            f"{agent_id}{time.time()}{self._seq}".encode()
        ).hexdigest()[:12]

        self._agents[agent_id] = _AgentEntry(
            entry_id=entry_id,
            agent_id=agent_id,
            error_threshold=error_threshold,
            max_consecutive_failures=max_consecutive_failures,
            created_at=time.time(),
            seq=self._seq,
        )
        self._stats["total_registered"] += 1

        logger.info("agent_registered", agent_id=agent_id, entry_id=entry_id)
        self._fire("agent_registered", {
            "entry_id": entry_id, "agent_id": agent_id,
        })
        return entry_id

    # ------------------------------------------------------------------
    # Recording outcomes
    # ------------------------------------------------------------------

    def record_success(self, agent_id: str) -> None:
        """Record a successful outcome for an agent."""
        entry = self._agents.get(agent_id)
        if not entry:
            return
        entry.total_successes += 1
        entry.consecutive_failures = 0
        self._stats["total_successes"] += 1

        self._fire("success_recorded", {"agent_id": agent_id})

    def record_failure(self, agent_id: str, reason: str = "") -> None:
        """Record a failure for an agent."""
        entry = self._agents.get(agent_id)
        if not entry:
            return
        entry.total_failures += 1
        entry.consecutive_failures += 1
        entry.last_failure_reason = reason
        self._stats["total_failures"] += 1

        logger.warning("agent_failure_recorded",
                       agent_id=agent_id,
                       consecutive=entry.consecutive_failures,
                       reason=reason)
        self._fire("failure_recorded", {
            "agent_id": agent_id,
            "consecutive_failures": entry.consecutive_failures,
            "reason": reason,
        })

    # ------------------------------------------------------------------
    # Fault queries
    # ------------------------------------------------------------------

    def is_faulty(self, agent_id: str) -> bool:
        """True if error rate exceeds threshold OR consecutive failures exceed max."""
        entry = self._agents.get(agent_id)
        if not entry:
            return False
        total = entry.total_successes + entry.total_failures
        if total > 0:
            error_rate = entry.total_failures / total
            if error_rate > entry.error_threshold:
                return True
        if entry.consecutive_failures >= entry.max_consecutive_failures:
            return True
        return False

    def get_error_rate(self, agent_id: str) -> float:
        """Get error rate for an agent (0.0-1.0)."""
        entry = self._agents.get(agent_id)
        if not entry:
            return 0.0
        total = entry.total_successes + entry.total_failures
        if total == 0:
            return 0.0
        return entry.total_failures / total

    def get_consecutive_failures(self, agent_id: str) -> int:
        """Get number of consecutive failures for an agent."""
        entry = self._agents.get(agent_id)
        if not entry:
            return 0
        return entry.consecutive_failures

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def reset_agent(self, agent_id: str) -> bool:
        """Reset counters for an agent."""
        entry = self._agents.get(agent_id)
        if not entry:
            return False
        entry.total_successes = 0
        entry.total_failures = 0
        entry.consecutive_failures = 0
        entry.last_failure_reason = ""
        self._stats["total_resets"] += 1

        logger.info("agent_reset", agent_id=agent_id)
        self._fire("agent_reset", {"agent_id": agent_id})
        return True

    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        return list(self._agents.keys())

    def get_agent_count(self) -> int:
        """Get count of registered agents."""
        return len(self._agents)

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

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_agents": len(self._agents),
            "faulty_agents": sum(
                1 for a in self._agents
                if self.is_faulty(a)
            ),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
