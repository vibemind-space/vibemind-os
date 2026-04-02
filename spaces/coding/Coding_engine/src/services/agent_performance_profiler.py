"""Agent performance profiler.

Profiles agent performance by recording execution times and throughput.
Tracks per-agent, per-operation timing with min/max/average statistics.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _ProfileEntry:
    """A single profiling entry."""
    profile_id: str = ""
    agent_id: str = ""
    operation: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    elapsed: float = 0.0
    completed: bool = False
    created_at: float = 0.0
    seq: int = 0


class AgentPerformanceProfiler:
    """Profiles agent performance by recording execution times and throughput."""

    def __init__(self, max_entries: int = 100000):
        self._profiles: Dict[str, _ProfileEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._max_entries = max_entries
        self._stats = {
            "total_profiles_started": 0,
            "total_profiles_completed": 0,
        }
        self._log = logger.bind(component="agent_performance_profiler")

    # ------------------------------------------------------------------
    # Profiling
    # ------------------------------------------------------------------

    def start_profile(self, agent_id: str, operation: str) -> str:
        """Start profiling an operation for an agent. Returns profile ID."""
        if not agent_id or not operation:
            return ""
        if len(self._profiles) >= self._max_entries:
            self._prune()

        self._seq += 1
        now = time.time()
        pid = "app2-" + hashlib.sha256(
            f"{agent_id}{operation}{now}{self._seq}".encode()
        ).hexdigest()[:12]

        self._profiles[pid] = _ProfileEntry(
            profile_id=pid,
            agent_id=agent_id,
            operation=operation,
            started_at=now,
            created_at=now,
            seq=self._seq,
        )
        self._stats["total_profiles_started"] += 1
        self._log.debug("profile_started", profile_id=pid,
                        agent_id=agent_id, operation=operation)
        self._fire("profile_started", {
            "profile_id": pid, "agent_id": agent_id, "operation": operation,
        })
        return pid

    def end_profile(self, profile_id: str) -> float:
        """End profiling. Returns elapsed seconds, or -1.0 on error."""
        p = self._profiles.get(profile_id)
        if not p or p.completed:
            return -1.0

        now = time.time()
        p.ended_at = now
        p.elapsed = now - p.started_at
        p.completed = True
        self._stats["total_profiles_completed"] += 1
        self._log.debug("profile_ended", profile_id=profile_id,
                        elapsed=round(p.elapsed, 4))
        self._fire("profile_ended", {
            "profile_id": profile_id, "agent_id": p.agent_id,
            "operation": p.operation, "elapsed": p.elapsed,
        })
        return p.elapsed

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_average_time(self, agent_id: str, operation: str = "") -> float:
        """Average execution time in seconds for an agent (optionally per operation)."""
        values = self._completed_times(agent_id, operation)
        if not values:
            return 0.0
        return sum(values) / len(values)

    def get_profile_count(self, agent_id: str) -> int:
        """Count of completed profiles for an agent."""
        return sum(
            1 for p in self._profiles.values()
            if p.agent_id == agent_id and p.completed
        )

    def get_summary(self, agent_id: str) -> Dict[str, Any]:
        """Performance summary for an agent.

        Returns dict with total_profiles, avg_time, min_time, max_time.
        """
        values = self._completed_times(agent_id)
        if not values:
            return {
                "total_profiles": 0,
                "avg_time": 0.0,
                "min_time": 0.0,
                "max_time": 0.0,
            }
        return {
            "total_profiles": len(values),
            "avg_time": round(sum(values) / len(values), 6),
            "min_time": round(min(values), 6),
            "max_time": round(max(values), 6),
        }

    def list_agents(self) -> List[str]:
        """List all agent IDs that have profiles."""
        agents: set[str] = set()
        for p in self._profiles.values():
            agents.add(p.agent_id)
        return sorted(agents)

    def get_total_profiles(self) -> int:
        """Total number of completed profiles across all agents."""
        return sum(1 for p in self._profiles.values() if p.completed)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
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

    def get_stats(self) -> Dict[str, Any]:
        """Return internal statistics."""
        return {
            **self._stats,
            "current_profiles": len(self._profiles),
            "current_completed": self.get_total_profiles(),
            "registered_callbacks": len(self._callbacks),
            "unique_agents": len(self.list_agents()),
        }

    def reset(self) -> None:
        """Clear all profiles and reset counters."""
        self._profiles.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _completed_times(self, agent_id: str,
                         operation: str = "") -> List[float]:
        """Collect elapsed times for completed profiles matching filters."""
        result: List[float] = []
        for p in self._profiles.values():
            if p.agent_id != agent_id or not p.completed:
                continue
            if operation and p.operation != operation:
                continue
            result.append(p.elapsed)
        return result

    def _prune(self) -> None:
        """Remove oldest quarter of profiles."""
        items = list(self._profiles.items())
        items.sort(key=lambda x: x[1].seq)
        to_remove = len(items) // 4
        for k, _ in items[:to_remove]:
            del self._profiles[k]
