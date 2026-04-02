"""Agent Workload Predictor – predict agent workload and capacity planning.

Records task completion times, estimates future workloads based on moving
averages, identifies bottlenecks, and suggests scaling recommendations.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _WorkloadAgent:
    agent_id_hash: str = ""
    agent_id: str = ""
    capacity: float = 100.0
    current_load: float = 0.0
    total_tasks: int = 0
    total_duration: float = 0.0
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0


@dataclass
class _TaskRecord:
    record_id: str = ""
    agent_id: str = ""
    task_name: str = ""
    duration: float = 0.0
    complexity: int = 5
    timestamp: float = 0.0


@dataclass
class _WorkloadEvent:
    event_id: str = ""
    agent_id: str = ""
    action: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class AgentWorkloadPredictor:
    """Predict agent workload and plan capacity based on historical data."""

    def __init__(self, max_agents: int = 5000, max_history: int = 100000):
        self._max_agents = max_agents
        self._max_history = max_history
        self._agents: Dict[str, _WorkloadAgent] = {}
        self._tasks: Dict[str, _TaskRecord] = {}
        self._agent_tasks: Dict[str, List[str]] = {}
        self._history: List[_WorkloadEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._total_agents_registered = 0
        self._total_tasks_recorded = 0
        self._total_load_assigned = 0
        self._total_load_released = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, prefix: str, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, capacity: float = 100.0,
                       tags: Optional[List[str]] = None) -> str:
        """Register an agent for workload tracking. Returns internal hash ID."""
        if not agent_id or capacity <= 0:
            return ""
        if len(self._agents) >= self._max_agents:
            return ""

        aid = self._make_id("wpa-", agent_id)
        self._agents[aid] = _WorkloadAgent(
            agent_id_hash=aid,
            agent_id=agent_id,
            capacity=capacity,
            current_load=0.0,
            total_tasks=0,
            total_duration=0.0,
            tags=tags or [],
            created_at=time.time(),
        )
        self._agent_tasks[aid] = []
        self._total_agents_registered += 1
        self._record_event(aid, "agent_registered", {"agent_id": agent_id, "capacity": capacity})
        self._fire("agent_registered", {"agent_id_hash": aid, "agent_id": agent_id})
        return aid

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Get agent info including predicted metrics."""
        a = self._agents.get(agent_id)
        if not a:
            return None
        avg_dur = (a.total_duration / a.total_tasks) if a.total_tasks > 0 else 0.0
        cap_pct = (a.current_load / a.capacity) * 100 if a.capacity > 0 else 0.0
        predicted = avg_dur  # time to complete one more task
        return {
            "agent_id_hash": a.agent_id_hash,
            "agent_id": a.agent_id,
            "capacity": a.capacity,
            "current_load": a.current_load,
            "avg_task_duration": round(avg_dur, 6),
            "task_count": a.total_tasks,
            "capacity_pct_used": round(cap_pct, 4),
            "predicted_completion_time": round(predicted, 6),
            "tags": list(a.tags),
            "created_at": a.created_at,
        }

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from tracking."""
        if agent_id not in self._agents:
            return False
        # Clean up associated task records
        task_ids = self._agent_tasks.pop(agent_id, [])
        for tid in task_ids:
            self._tasks.pop(tid, None)
        del self._agents[agent_id]
        self._record_event(agent_id, "agent_removed", {})
        self._fire("agent_removed", {"agent_id_hash": agent_id})
        return True

    def list_agents(self, tag: str = "") -> List[Dict]:
        """List all agents, optionally filtered by tag."""
        result = []
        for a in self._agents.values():
            if tag and tag not in a.tags:
                continue
            avg_dur = (a.total_duration / a.total_tasks) if a.total_tasks > 0 else 0.0
            cap_pct = (a.current_load / a.capacity) * 100 if a.capacity > 0 else 0.0
            result.append({
                "agent_id_hash": a.agent_id_hash,
                "agent_id": a.agent_id,
                "capacity": a.capacity,
                "current_load": a.current_load,
                "avg_task_duration": round(avg_dur, 6),
                "task_count": a.total_tasks,
                "capacity_pct_used": round(cap_pct, 4),
                "tags": list(a.tags),
            })
        return result

    # ------------------------------------------------------------------
    # Task recording
    # ------------------------------------------------------------------

    def record_task(self, agent_id: str, task_name: str, duration: float,
                    complexity: int = 5) -> str:
        """Record a completed task with its duration. Returns record ID."""
        if agent_id not in self._agents:
            return ""
        if not task_name or duration < 0:
            return ""
        complexity = max(1, min(10, complexity))

        rid = self._make_id("wpt-", f"{agent_id}-{task_name}")
        now = time.time()
        self._tasks[rid] = _TaskRecord(
            record_id=rid,
            agent_id=agent_id,
            task_name=task_name,
            duration=duration,
            complexity=complexity,
            timestamp=now,
        )
        self._agent_tasks.setdefault(agent_id, []).append(rid)

        # Trim if over limit
        if len(self._tasks) > self._max_history:
            oldest_keys = sorted(self._tasks, key=lambda k: self._tasks[k].timestamp)
            for k in oldest_keys[:len(self._tasks) - self._max_history]:
                removed = self._tasks.pop(k)
                if removed.agent_id in self._agent_tasks:
                    try:
                        self._agent_tasks[removed.agent_id].remove(k)
                    except ValueError:
                        pass

        agent = self._agents[agent_id]
        agent.total_tasks += 1
        agent.total_duration += duration
        self._total_tasks_recorded += 1
        self._record_event(agent_id, "task_recorded", {
            "record_id": rid, "task_name": task_name,
            "duration": duration, "complexity": complexity,
        })
        self._fire("task_recorded", {"agent_id_hash": agent_id, "record_id": rid})
        return rid

    # ------------------------------------------------------------------
    # Load management
    # ------------------------------------------------------------------

    def assign_load(self, agent_id: str, load_amount: float) -> bool:
        """Add load to an agent's current workload."""
        a = self._agents.get(agent_id)
        if not a or load_amount <= 0:
            return False
        a.current_load += load_amount
        self._total_load_assigned += 1
        self._record_event(agent_id, "load_assigned", {"amount": load_amount})
        self._fire("load_assigned", {"agent_id_hash": agent_id, "amount": load_amount})
        return True

    def release_load(self, agent_id: str, load_amount: float) -> bool:
        """Subtract load from an agent's current workload."""
        a = self._agents.get(agent_id)
        if not a or load_amount <= 0:
            return False
        a.current_load = max(0.0, a.current_load - load_amount)
        self._total_load_released += 1
        self._record_event(agent_id, "load_released", {"amount": load_amount})
        self._fire("load_released", {"agent_id_hash": agent_id, "amount": load_amount})
        return True

    # ------------------------------------------------------------------
    # Prediction and analysis
    # ------------------------------------------------------------------

    def predict_completion(self, agent_id: str, remaining_tasks: int) -> float:
        """Estimate time to complete N tasks based on avg_task_duration."""
        a = self._agents.get(agent_id)
        if not a or remaining_tasks <= 0:
            return 0.0
        if a.total_tasks == 0:
            return 0.0
        avg_dur = a.total_duration / a.total_tasks
        return round(remaining_tasks * avg_dur, 6)

    def get_bottlenecks(self, threshold: float = 80.0) -> List[Dict]:
        """Return agents whose capacity_pct_used exceeds threshold."""
        result = []
        for a in self._agents.values():
            cap_pct = (a.current_load / a.capacity) * 100 if a.capacity > 0 else 0.0
            if cap_pct > threshold:
                result.append({
                    "agent_id_hash": a.agent_id_hash,
                    "agent_id": a.agent_id,
                    "capacity": a.capacity,
                    "current_load": a.current_load,
                    "capacity_pct_used": round(cap_pct, 4),
                })
        result.sort(key=lambda x: -x["capacity_pct_used"])
        return result

    def suggest_scaling(self) -> Dict:
        """Analyze all agents and suggest scaling actions."""
        overloaded = []
        underloaded = []
        for a in self._agents.values():
            cap_pct = (a.current_load / a.capacity) * 100 if a.capacity > 0 else 0.0
            info = {
                "agent_id_hash": a.agent_id_hash,
                "agent_id": a.agent_id,
                "capacity": a.capacity,
                "current_load": a.current_load,
                "capacity_pct_used": round(cap_pct, 4),
            }
            if cap_pct > 80.0:
                overloaded.append(info)
            elif cap_pct < 20.0:
                underloaded.append(info)

        recommended_rebalance: List[Dict] = []
        # Try to pair overloaded agents with underloaded ones
        over_copy = list(overloaded)
        under_copy = list(underloaded)
        for over in over_copy:
            if not under_copy:
                break
            under = under_copy[0]
            excess = over["current_load"] - (over["capacity"] * 0.5)
            available = under["capacity"] - under["current_load"]
            if excess > 0 and available > 0:
                transfer = min(excess, available)
                recommended_rebalance.append({
                    "from": over["agent_id_hash"],
                    "to": under["agent_id_hash"],
                    "amount": round(transfer, 4),
                })
                under_copy.pop(0)

        return {
            "overloaded": overloaded,
            "underloaded": underloaded,
            "recommended_rebalance": recommended_rebalance,
        }

    def get_agent_trend(self, agent_id: str, window: int = 10) -> Dict:
        """Compute moving average of last N task durations and trend direction."""
        a = self._agents.get(agent_id)
        if not a:
            return {}

        task_ids = self._agent_tasks.get(agent_id, [])
        # Get durations sorted by timestamp
        records = []
        for tid in task_ids:
            rec = self._tasks.get(tid)
            if rec:
                records.append(rec)
        records.sort(key=lambda r: r.timestamp)

        # Take last `window` records
        recent = records[-window:] if len(records) >= window else records
        if not recent:
            return {
                "agent_id_hash": agent_id,
                "window": window,
                "sample_count": 0,
                "moving_avg": 0.0,
                "trend": "stable",
            }

        durations = [r.duration for r in recent]
        moving_avg = sum(durations) / len(durations)

        # Determine trend: compare first half avg vs second half avg
        mid = len(durations) // 2
        if mid == 0:
            trend = "stable"
        else:
            first_half = durations[:mid]
            second_half = durations[mid:]
            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)
            diff = second_avg - first_avg
            threshold = first_avg * 0.1 if first_avg > 0 else 0.01
            if diff > threshold:
                trend = "increasing"
            elif diff < -threshold:
                trend = "decreasing"
            else:
                trend = "stable"

        return {
            "agent_id_hash": agent_id,
            "window": window,
            "sample_count": len(durations),
            "moving_avg": round(moving_avg, 6),
            "trend": trend,
        }

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_event(self, agent_id: str, action: str, data: Dict) -> None:
        eid = self._make_id("wpe-", f"{agent_id}-{action}")
        self._history.append(_WorkloadEvent(
            event_id=eid,
            agent_id=agent_id,
            action=action,
            data=data,
            timestamp=time.time(),
        ))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Return the most recent history events."""
        limit = max(1, min(limit, len(self._history)))
        result = []
        for evt in self._history[-limit:]:
            result.append({
                "event_id": evt.event_id,
                "agent_id": evt.agent_id,
                "action": evt.action,
                "data": dict(evt.data),
                "timestamp": evt.timestamp,
            })
        return result

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
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
        """Return current statistics."""
        return {
            "total_agents_registered": self._total_agents_registered,
            "total_tasks_recorded": self._total_tasks_recorded,
            "total_load_assigned": self._total_load_assigned,
            "total_load_released": self._total_load_released,
            "current_agents": len(self._agents),
            "current_task_records": len(self._tasks),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._agents.clear()
        self._tasks.clear()
        self._agent_tasks.clear()
        self._history.clear()
        self._seq = 0
        self._total_agents_registered = 0
        self._total_tasks_recorded = 0
        self._total_load_assigned = 0
        self._total_load_released = 0
