"""Agent workload monitor - monitors agent workload levels and detects overload conditions."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class AgentWorkloadMonitorState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentWorkloadMonitor:
    """Monitor agent workload levels and detect overload conditions."""

    def __init__(self):
        self._state = AgentWorkloadMonitorState()
        self._callbacks = {}
        # Tracks agent workload: agent_id -> {active_tasks, max_concurrent, registered_at}
        self._agents = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "awm-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del self._state.entries[key]

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self._callbacks:
            del self._callbacks[cb_id]
            return True
        return False

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def register_agent(self, agent_id: str, max_concurrent: int = 10) -> str:
        """Register an agent for workload monitoring."""
        monitor_id = self._generate_id(f"agent-{agent_id}")
        now = time.time()
        self._agents[agent_id] = {
            "monitor_id": monitor_id,
            "active_tasks": 0,
            "max_concurrent": max_concurrent,
            "registered_at": now,
        }
        self._state.entries[monitor_id] = {
            "agent_id": agent_id,
            "monitor_id": monitor_id,
            "active_tasks": 0,
            "max_concurrent": max_concurrent,
            "created_at": now,
        }
        self._prune()
        self._fire("agent_registered", {"agent_id": agent_id, "monitor_id": monitor_id})
        logger.info("Registered agent %s with monitor_id %s", agent_id, monitor_id)
        return monitor_id

    def record_task_start(self, agent_id: str) -> bool:
        """Record that an agent started a task. Returns True if successful."""
        if agent_id not in self._agents:
            logger.warning("Agent %s not registered", agent_id)
            return False
        agent = self._agents[agent_id]
        agent["active_tasks"] += 1
        # Update entry
        monitor_id = agent["monitor_id"]
        if monitor_id in self._state.entries:
            self._state.entries[monitor_id]["active_tasks"] = agent["active_tasks"]
        self._fire("task_started", {"agent_id": agent_id, "active_tasks": agent["active_tasks"]})
        return True

    def record_task_end(self, agent_id: str) -> bool:
        """Record that an agent finished a task. Returns True if successful."""
        if agent_id not in self._agents:
            logger.warning("Agent %s not registered", agent_id)
            return False
        agent = self._agents[agent_id]
        if agent["active_tasks"] <= 0:
            logger.warning("Agent %s has no active tasks to end", agent_id)
            return False
        agent["active_tasks"] -= 1
        monitor_id = agent["monitor_id"]
        if monitor_id in self._state.entries:
            self._state.entries[monitor_id]["active_tasks"] = agent["active_tasks"]
        self._fire("task_ended", {"agent_id": agent_id, "active_tasks": agent["active_tasks"]})
        return True

    def get_workload(self, agent_id: str) -> dict:
        """Get workload info for an agent."""
        if agent_id not in self._agents:
            return {}
        agent = self._agents[agent_id]
        active = agent["active_tasks"]
        max_c = agent["max_concurrent"]
        utilization = (active / max_c * 100) if max_c > 0 else 0.0
        return {
            "active_tasks": active,
            "max_concurrent": max_c,
            "utilization_percent": utilization,
            "is_overloaded": active >= max_c,
        }

    def get_least_loaded(self, limit: int = 5) -> list:
        """Get the least loaded agents sorted by utilization ascending."""
        results = []
        for agent_id, agent in self._agents.items():
            max_c = agent["max_concurrent"]
            active = agent["active_tasks"]
            utilization = (active / max_c * 100) if max_c > 0 else 0.0
            results.append({
                "agent_id": agent_id,
                "active_tasks": active,
                "utilization_percent": utilization,
            })
        results.sort(key=lambda x: x["utilization_percent"])
        return results[:limit]

    def get_monitor(self, monitor_id: str) -> dict:
        """Get a monitor entry by ID, or None if not found."""
        return self._state.entries.get(monitor_id)

    def get_monitor_count(self) -> int:
        """Get the total number of monitor entries."""
        return len(self._state.entries)

    def list_agents(self) -> list:
        """List all registered agent IDs."""
        return list(self._agents.keys())

    def get_stats(self) -> dict:
        """Get overall statistics."""
        total_active = sum(a["active_tasks"] for a in self._agents.values())
        total_capacity = sum(a["max_concurrent"] for a in self._agents.values())
        return {
            "total_agents": len(self._agents),
            "total_monitors": len(self._state.entries),
            "total_active_tasks": total_active,
            "total_capacity": total_capacity,
            "overall_utilization_percent": (total_active / total_capacity * 100) if total_capacity > 0 else 0.0,
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self):
        """Reset all state."""
        self._state = AgentWorkloadMonitorState()
        self._callbacks.clear()
        self._agents.clear()
        logger.info("AgentWorkloadMonitor reset")
