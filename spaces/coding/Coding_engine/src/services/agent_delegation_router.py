"""Agent Delegation Router – routes tasks to the most suitable agent.

Manages agent registrations with capabilities and capacity, then routes
incoming tasks to the best available agent based on capability matching,
load balancing, and priority. Supports routing strategies and fallback agents.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _AgentRegistration:
    reg_id: str
    agent: str
    capabilities: List[str]
    max_concurrent: int
    current_load: int
    total_routed: int
    total_completed: int
    total_failed: int
    enabled: bool
    priority: int
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _RoutingRecord:
    record_id: str
    task_id: str
    agent: str
    capability: str
    strategy: str
    timestamp: float


class AgentDelegationRouter:
    """Routes tasks to the best available agent."""

    STRATEGIES = ("capability", "round_robin", "least_loaded", "priority")

    def __init__(self, max_agents: int = 1000, max_history: int = 100000):
        self._agents: Dict[str, _AgentRegistration] = {}
        self._name_index: Dict[str, str] = {}
        self._cap_index: Dict[str, List[str]] = {}
        self._history: List[_RoutingRecord] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_agents = max_agents
        self._max_history = max_history
        self._seq = 0
        self._rr_counter = 0

        self._total_registered = 0
        self._total_routed = 0
        self._total_no_match = 0

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent: str,
        capabilities: Optional[List[str]] = None,
        max_concurrent: int = 10,
        priority: int = 0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not agent:
            return ""
        if agent in self._name_index:
            return ""
        if len(self._agents) >= self._max_agents:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{now}-{self._seq}"
        rid = "dlg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        reg = _AgentRegistration(
            reg_id=rid,
            agent=agent,
            capabilities=capabilities or [],
            max_concurrent=max_concurrent,
            current_load=0,
            total_routed=0,
            total_completed=0,
            total_failed=0,
            enabled=True,
            priority=priority,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._agents[rid] = reg
        self._name_index[agent] = rid
        for cap in reg.capabilities:
            self._cap_index.setdefault(cap, []).append(rid)
        self._total_registered += 1
        self._fire("agent_registered", {"reg_id": rid, "agent": agent})
        return rid

    def get_agent(self, reg_id: str) -> Optional[Dict[str, Any]]:
        r = self._agents.get(reg_id)
        if not r:
            return None
        avail = r.current_load < r.max_concurrent and r.enabled
        return {
            "reg_id": r.reg_id,
            "agent": r.agent,
            "capabilities": list(r.capabilities),
            "max_concurrent": r.max_concurrent,
            "current_load": r.current_load,
            "available": avail,
            "enabled": r.enabled,
            "priority": r.priority,
            "total_routed": r.total_routed,
            "total_completed": r.total_completed,
            "total_failed": r.total_failed,
            "tags": list(r.tags),
            "created_at": r.created_at,
        }

    def get_by_name(self, agent: str) -> Optional[Dict[str, Any]]:
        rid = self._name_index.get(agent)
        if not rid:
            return None
        return self.get_agent(rid)

    def unregister_agent(self, reg_id: str) -> bool:
        r = self._agents.pop(reg_id, None)
        if not r:
            return False
        self._name_index.pop(r.agent, None)
        for cap in r.capabilities:
            cap_list = self._cap_index.get(cap, [])
            if reg_id in cap_list:
                cap_list.remove(reg_id)
        return True

    def enable_agent(self, reg_id: str) -> bool:
        r = self._agents.get(reg_id)
        if not r or r.enabled:
            return False
        r.enabled = True
        r.updated_at = time.time()
        return True

    def disable_agent(self, reg_id: str) -> bool:
        r = self._agents.get(reg_id)
        if not r or not r.enabled:
            return False
        r.enabled = False
        r.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(
        self,
        task_id: str,
        capability: str,
        strategy: str = "least_loaded",
    ) -> Optional[str]:
        if not task_id or not capability:
            return None
        if strategy not in self.STRATEGIES:
            strategy = "least_loaded"

        candidates = self._get_candidates(capability)
        if not candidates:
            self._total_no_match += 1
            return None

        selected = self._select(candidates, strategy)
        if not selected:
            self._total_no_match += 1
            return None

        selected.current_load += 1
        selected.total_routed += 1
        selected.updated_at = time.time()
        self._total_routed += 1

        self._seq += 1
        now = time.time()
        raw = f"{task_id}-{selected.agent}-{now}-{self._seq}"
        rec_id = "rte-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        record = _RoutingRecord(
            record_id=rec_id,
            task_id=task_id,
            agent=selected.agent,
            capability=capability,
            strategy=strategy,
            timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(record)

        self._fire("task_routed", {
            "task_id": task_id, "agent": selected.agent,
            "capability": capability, "strategy": strategy,
        })
        return selected.agent

    def complete_task(self, agent: str) -> bool:
        rid = self._name_index.get(agent)
        if not rid:
            return False
        r = self._agents.get(rid)
        if not r:
            return False
        r.current_load = max(0, r.current_load - 1)
        r.total_completed += 1
        r.updated_at = time.time()
        return True

    def fail_task(self, agent: str) -> bool:
        rid = self._name_index.get(agent)
        if not rid:
            return False
        r = self._agents.get(rid)
        if not r:
            return False
        r.current_load = max(0, r.current_load - 1)
        r.total_failed += 1
        r.updated_at = time.time()
        return True

    def _get_candidates(self, capability: str) -> List[_AgentRegistration]:
        rids = self._cap_index.get(capability, [])
        candidates = []
        for rid in rids:
            r = self._agents.get(rid)
            if r and r.enabled and r.current_load < r.max_concurrent:
                candidates.append(r)
        return candidates

    def _select(self, candidates: List[_AgentRegistration], strategy: str) -> Optional[_AgentRegistration]:
        if not candidates:
            return None

        if strategy == "least_loaded":
            return min(candidates, key=lambda r: r.current_load)
        elif strategy == "priority":
            return max(candidates, key=lambda r: r.priority)
        elif strategy == "round_robin":
            self._rr_counter += 1
            idx = self._rr_counter % len(candidates)
            return candidates[idx]
        elif strategy == "capability":
            return candidates[0]
        return candidates[0]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_available_agents(self, capability: str = "") -> List[Dict[str, Any]]:
        results = []
        for r in self._agents.values():
            if not r.enabled or r.current_load >= r.max_concurrent:
                continue
            if capability and capability not in r.capabilities:
                continue
            results.append(self.get_agent(r.reg_id))
        return results

    def list_agents(self, capability: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for r in self._agents.values():
            if capability and capability not in r.capabilities:
                continue
            if tag and tag not in r.tags:
                continue
            results.append(self.get_agent(r.reg_id))
        return results

    def get_history(self, agent: str = "", capability: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for rec in reversed(self._history):
            if agent and rec.agent != agent:
                continue
            if capability and rec.capability != capability:
                continue
            results.append({
                "record_id": rec.record_id,
                "task_id": rec.task_id,
                "agent": rec.agent,
                "capability": rec.capability,
                "strategy": rec.strategy,
                "timestamp": rec.timestamp,
            })
            if len(results) >= limit:
                break
        return results

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
            "current_agents": len(self._agents),
            "total_registered": self._total_registered,
            "total_routed": self._total_routed,
            "total_no_match": self._total_no_match,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._name_index.clear()
        self._cap_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._rr_counter = 0
        self._total_registered = 0
        self._total_routed = 0
        self._total_no_match = 0
