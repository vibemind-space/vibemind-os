"""Agent Resource Tracker – tracks resource usage per agent.

Monitors CPU, memory, tokens, and custom resource consumption per agent.
Supports quotas, usage alerts, and historical tracking for capacity planning.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ResourceEntry:
    entry_id: str
    agent: str
    resource_type: str  # cpu, memory, tokens, api_calls, custom
    current_usage: float
    peak_usage: float
    quota: float  # 0 = unlimited
    total_consumed: float
    sample_count: int
    last_recorded_at: float
    tags: List[str]
    created_at: float
    updated_at: float


class AgentResourceTracker:
    """Tracks resource usage per agent."""

    RESOURCE_TYPES = ("cpu", "memory", "tokens", "api_calls", "custom")

    def __init__(self, max_entries: int = 50000):
        self._entries: Dict[str, _ResourceEntry] = {}
        self._agent_index: Dict[str, List[str]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # stats
        self._total_tracked = 0
        self._total_recordings = 0
        self._total_quota_exceeded = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def track(
        self,
        agent: str,
        resource_type: str = "custom",
        quota: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not agent:
            return ""
        if resource_type not in self.RESOURCE_TYPES:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""

        # check for duplicate agent+resource_type
        for eid in self._agent_index.get(agent, []):
            e = self._entries.get(eid)
            if e and e.resource_type == resource_type:
                return ""

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{resource_type}-{now}-{self._seq}"
        eid = "rsc-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _ResourceEntry(
            entry_id=eid,
            agent=agent,
            resource_type=resource_type,
            current_usage=0.0,
            peak_usage=0.0,
            quota=quota,
            total_consumed=0.0,
            sample_count=0,
            last_recorded_at=0.0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._entries[eid] = entry
        self._agent_index.setdefault(agent, []).append(eid)
        self._total_tracked += 1
        self._fire("resource_tracked", {"entry_id": eid, "agent": agent, "resource_type": resource_type})
        return eid

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        e = self._entries.get(entry_id)
        if not e:
            return None
        return {
            "entry_id": e.entry_id,
            "agent": e.agent,
            "resource_type": e.resource_type,
            "current_usage": e.current_usage,
            "peak_usage": e.peak_usage,
            "quota": e.quota,
            "total_consumed": e.total_consumed,
            "sample_count": e.sample_count,
            "quota_pct": (e.current_usage / e.quota * 100.0) if e.quota > 0 else 0.0,
            "last_recorded_at": e.last_recorded_at,
            "tags": list(e.tags),
            "created_at": e.created_at,
        }

    def remove_entry(self, entry_id: str) -> bool:
        e = self._entries.pop(entry_id, None)
        if not e:
            return False
        agent_list = self._agent_index.get(e.agent, [])
        if entry_id in agent_list:
            agent_list.remove(entry_id)
        return True

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, entry_id: str, usage: float) -> bool:
        """Record current resource usage."""
        e = self._entries.get(entry_id)
        if not e:
            return False
        if usage < 0:
            return False

        e.current_usage = usage
        if usage > e.peak_usage:
            e.peak_usage = usage
        e.total_consumed += usage
        e.sample_count += 1
        now = time.time()
        e.last_recorded_at = now
        e.updated_at = now
        self._total_recordings += 1

        # check quota
        if e.quota > 0 and usage > e.quota:
            self._total_quota_exceeded += 1
            self._fire("quota_exceeded", {
                "entry_id": entry_id, "agent": e.agent,
                "usage": usage, "quota": e.quota,
            })
        return True

    def set_quota(self, entry_id: str, quota: float) -> bool:
        """Set or update quota."""
        e = self._entries.get(entry_id)
        if not e:
            return False
        if quota < 0:
            return False
        e.quota = quota
        e.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_agent_usage(self, agent: str) -> List[Dict[str, Any]]:
        """Get all resource entries for an agent."""
        eids = self._agent_index.get(agent, [])
        results = []
        for eid in eids:
            entry = self.get_entry(eid)
            if entry:
                results.append(entry)
        return results

    def get_over_quota(self) -> List[Dict[str, Any]]:
        """Get entries exceeding their quota."""
        results = []
        for e in self._entries.values():
            if e.quota > 0 and e.current_usage > e.quota:
                results.append(self.get_entry(e.entry_id))
        return results

    def list_entries(
        self,
        agent: str = "",
        resource_type: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in self._entries.values():
            if agent and e.agent != agent:
                continue
            if resource_type and e.resource_type != resource_type:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_entry(e.entry_id))
        return results

    def get_total_usage_by_type(self, resource_type: str) -> float:
        """Get total current usage across all agents for a resource type."""
        return sum(
            e.current_usage for e in self._entries.values()
            if e.resource_type == resource_type
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_entries": len(self._entries),
            "total_tracked": self._total_tracked,
            "total_recordings": self._total_recordings,
            "total_quota_exceeded": self._total_quota_exceeded,
            "unique_agents": len(self._agent_index),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._agent_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_tracked = 0
        self._total_recordings = 0
        self._total_quota_exceeded = 0
