"""Agent Pool Manager – manages pools of reusable agent instances.

Provides agent pooling with configurable pool sizes, idle timeout,
and health-based eviction.  Agents are acquired from the pool and
released back when done.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _PoolEntry:
    entry_id: str
    pool_name: str
    agent_id: str
    status: str  # idle, acquired, unhealthy
    acquired_by: str
    acquired_at: float
    idle_since: float
    health_score: float  # 0-100
    tags: List[str]
    created_at: float


@dataclass
class _PoolEvent:
    event_id: str
    pool_name: str
    agent_id: str
    action: str  # added, acquired, released, evicted
    timestamp: float


class AgentPoolManager:
    """Manages pools of reusable agent instances."""

    def __init__(
        self,
        max_pools: int = 100,
        max_agents_per_pool: int = 50,
        max_history: int = 100000,
        idle_timeout: float = 300.0,
        min_health: float = 20.0,
    ):
        self._pools: Dict[str, Dict[str, _PoolEntry]] = {}  # pool_name -> {entry_id: entry}
        self._pool_tags: Dict[str, List[str]] = {}
        self._history: List[_PoolEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_pools = max_pools
        self._max_agents_per_pool = max_agents_per_pool
        self._max_history = max_history
        self._idle_timeout = idle_timeout
        self._min_health = min_health
        self._seq = 0

        # stats
        self._total_added = 0
        self._total_acquired = 0
        self._total_released = 0
        self._total_evicted = 0

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def create_pool(self, pool_name: str, tags: Optional[List[str]] = None) -> bool:
        if not pool_name or pool_name in self._pools:
            return False
        if len(self._pools) >= self._max_pools:
            return False
        self._pools[pool_name] = {}
        self._pool_tags[pool_name] = tags or []
        self._fire("pool_created", {"pool_name": pool_name})
        return True

    def remove_pool(self, pool_name: str) -> bool:
        if pool_name not in self._pools:
            return False
        self._pools.pop(pool_name)
        self._pool_tags.pop(pool_name, None)
        return True

    def list_pools(self) -> List[Dict[str, Any]]:
        results = []
        for name, entries in self._pools.items():
            idle = sum(1 for e in entries.values() if e.status == "idle")
            acquired = sum(1 for e in entries.values() if e.status == "acquired")
            results.append({
                "pool_name": name,
                "size": len(entries),
                "idle": idle,
                "acquired": acquired,
                "tags": list(self._pool_tags.get(name, [])),
            })
        return results

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def add_agent(self, pool_name: str, agent_id: str, tags: Optional[List[str]] = None) -> str:
        if pool_name not in self._pools:
            return ""
        if not agent_id:
            return ""
        pool = self._pools[pool_name]
        if len(pool) >= self._max_agents_per_pool:
            return ""
        # Check duplicate agent_id in pool
        for e in pool.values():
            if e.agent_id == agent_id:
                return ""

        self._seq += 1
        now = time.time()
        raw = f"{pool_name}-{agent_id}-{now}-{self._seq}"
        eid = "pe-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _PoolEntry(
            entry_id=eid,
            pool_name=pool_name,
            agent_id=agent_id,
            status="idle",
            acquired_by="",
            acquired_at=0.0,
            idle_since=now,
            health_score=100.0,
            tags=tags or [],
            created_at=now,
        )
        pool[eid] = entry
        self._total_added += 1
        self._record_event(pool_name, agent_id, "added")
        self._fire("agent_added", {"pool_name": pool_name, "agent_id": agent_id})
        return eid

    def acquire(self, pool_name: str, requester: str = "") -> Optional[Dict[str, Any]]:
        """Acquire an idle agent from the pool."""
        pool = self._pools.get(pool_name)
        if not pool:
            return None

        # Find best idle agent (highest health score)
        best = None
        for e in pool.values():
            if e.status == "idle" and e.health_score >= self._min_health:
                if best is None or e.health_score > best.health_score:
                    best = e

        if not best:
            return None

        best.status = "acquired"
        best.acquired_by = requester
        best.acquired_at = time.time()
        self._total_acquired += 1
        self._record_event(pool_name, best.agent_id, "acquired")
        self._fire("agent_acquired", {"pool_name": pool_name, "agent_id": best.agent_id, "requester": requester})

        return {
            "entry_id": best.entry_id,
            "agent_id": best.agent_id,
            "pool_name": best.pool_name,
            "health_score": best.health_score,
        }

    def release(self, pool_name: str, entry_id: str) -> bool:
        """Release an acquired agent back to the pool."""
        pool = self._pools.get(pool_name)
        if not pool:
            return False
        entry = pool.get(entry_id)
        if not entry or entry.status != "acquired":
            return False

        entry.status = "idle"
        entry.acquired_by = ""
        entry.acquired_at = 0.0
        entry.idle_since = time.time()
        self._total_released += 1
        self._record_event(pool_name, entry.agent_id, "released")
        self._fire("agent_released", {"pool_name": pool_name, "agent_id": entry.agent_id})
        return True

    def evict(self, pool_name: str, entry_id: str) -> bool:
        """Remove an agent from the pool."""
        pool = self._pools.get(pool_name)
        if not pool:
            return False
        entry = pool.pop(entry_id, None)
        if not entry:
            return False
        self._total_evicted += 1
        self._record_event(pool_name, entry.agent_id, "evicted")
        self._fire("agent_evicted", {"pool_name": pool_name, "agent_id": entry.agent_id})
        return True

    def update_health(self, pool_name: str, entry_id: str, health: float) -> bool:
        pool = self._pools.get(pool_name)
        if not pool:
            return False
        entry = pool.get(entry_id)
        if not entry:
            return False
        entry.health_score = max(0.0, min(100.0, health))
        if entry.health_score < self._min_health:
            entry.status = "unhealthy"
        return True

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def evict_idle(self, pool_name: str = "") -> int:
        """Evict agents that have been idle too long."""
        now = time.time()
        count = 0
        pools = [pool_name] if pool_name else list(self._pools.keys())
        for pn in pools:
            pool = self._pools.get(pn)
            if not pool:
                continue
            to_evict = []
            for eid, e in pool.items():
                if e.status == "idle" and (now - e.idle_since) > self._idle_timeout:
                    to_evict.append(eid)
            for eid in to_evict:
                self.evict(pn, eid)
                count += 1
        return count

    def evict_unhealthy(self, pool_name: str = "") -> int:
        """Evict unhealthy agents."""
        count = 0
        pools = [pool_name] if pool_name else list(self._pools.keys())
        for pn in pools:
            pool = self._pools.get(pn)
            if not pool:
                continue
            to_evict = [eid for eid, e in pool.items() if e.status == "unhealthy"]
            for eid in to_evict:
                self.evict(pn, eid)
                count += 1
        return count

    def get_pool_info(self, pool_name: str) -> Optional[Dict[str, Any]]:
        pool = self._pools.get(pool_name)
        if pool is None:
            return None
        agents = []
        for e in pool.values():
            agents.append({
                "entry_id": e.entry_id,
                "agent_id": e.agent_id,
                "status": e.status,
                "health_score": e.health_score,
                "acquired_by": e.acquired_by,
            })
        return {
            "pool_name": pool_name,
            "size": len(pool),
            "agents": agents,
            "tags": list(self._pool_tags.get(pool_name, [])),
        }

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        pool_name: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if pool_name and ev.pool_name != pool_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "pool_name": ev.pool_name,
                "agent_id": ev.agent_id,
                "action": ev.action,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, pool_name: str, agent_id: str, action: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{pool_name}-{agent_id}-{action}-{now}-{self._seq}"
        evid = "pev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _PoolEvent(
            event_id=evid, pool_name=pool_name, agent_id=agent_id,
            action=action, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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
        total_agents = sum(len(p) for p in self._pools.values())
        total_idle = sum(1 for p in self._pools.values() for e in p.values() if e.status == "idle")
        total_acquired = sum(1 for p in self._pools.values() for e in p.values() if e.status == "acquired")
        return {
            "total_pools": len(self._pools),
            "total_agents": total_agents,
            "total_idle": total_idle,
            "total_acquired_now": total_acquired,
            "total_added": self._total_added,
            "total_acquired": self._total_acquired,
            "total_released": self._total_released,
            "total_evicted": self._total_evicted,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._pools.clear()
        self._pool_tags.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_added = 0
        self._total_acquired = 0
        self._total_released = 0
        self._total_evicted = 0
