"""Aggregate health signals from multiple agents into overall system health view."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class AgentHealthAggregatorState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentHealthAggregator:
    """Aggregates health reports from multiple agents into a system-wide health view."""

    VALID_STATUSES = ("healthy", "degraded", "unhealthy")

    def __init__(self):
        self._state = AgentHealthAggregatorState()
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "aha-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        entries = self._state.entries
        if len(entries) > MAX_ENTRIES:
            sorted_keys = sorted(entries, key=lambda k: entries[k].get("timestamp", 0))
            to_remove = len(entries) - MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del entries[key]

    def on_change(self, callback_id: str, callback):
        """Register a callback to be fired on health report changes."""
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a registered callback. Returns True if it existed."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def _fire(self, event: str, data: dict):
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("Callback %s failed", cb_id)

    def report_health(self, agent_id: str, component: str, status: str = "healthy", details=None) -> str:
        """Report health for a specific component of an agent. Returns report_id."""
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {self.VALID_STATUSES}")

        report_id = self._generate_id(f"{agent_id}:{component}:{status}")
        entry = {
            "report_id": report_id,
            "agent_id": agent_id,
            "component": component,
            "status": status,
            "details": details,
            "timestamp": time.time(),
        }
        self._state.entries[report_id] = entry
        self._prune()
        self._fire("health_reported", entry)
        return report_id

    def get_report(self, report_id: str):
        """Get a specific report by ID, or None if not found."""
        return self._state.entries.get(report_id)

    def get_report_count(self, agent_id: str = "") -> int:
        """Get count of reports, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def list_agents(self) -> list:
        """List all known agent IDs."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_agent_health(self, agent_id: str) -> dict:
        """Get health summary for a specific agent.

        Returns dict with 'overall' status and 'components' mapping.
        The overall status is the worst status among all components.
        """
        components = {}
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            comp = entry["component"]
            # Keep the latest report per component
            if comp not in components or entry["timestamp"] >= components[comp]["timestamp"]:
                components[comp] = entry

        if not components:
            return {"overall": "healthy", "components": {}}

        comp_statuses = {}
        for comp, entry in components.items():
            comp_statuses[comp] = entry["status"]

        overall = self._worst_status(list(comp_statuses.values()))
        return {"overall": overall, "components": comp_statuses}

    def get_system_health(self) -> dict:
        """Get system-wide health summary across all agents."""
        agents = self.list_agents()
        agent_health = {}
        healthy_count = 0
        degraded_count = 0
        unhealthy_count = 0

        for agent_id in agents:
            health = self.get_agent_health(agent_id)
            agent_health[agent_id] = health
            overall = health["overall"]
            if overall == "healthy":
                healthy_count += 1
            elif overall == "degraded":
                degraded_count += 1
            else:
                unhealthy_count += 1

        if not agents:
            system_overall = "healthy"
        else:
            system_overall = self._worst_status([h["overall"] for h in agent_health.values()])

        return {
            "overall": system_overall,
            "healthy_count": healthy_count,
            "degraded_count": degraded_count,
            "unhealthy_count": unhealthy_count,
            "agents": agent_health,
        }

    def get_unhealthy_agents(self) -> list:
        """Get list of agent IDs that have an unhealthy overall status."""
        result = []
        for agent_id in self.list_agents():
            health = self.get_agent_health(agent_id)
            if health["overall"] == "unhealthy":
                result.append(agent_id)
        return result

    def get_stats(self) -> dict:
        """Get aggregator statistics."""
        return {
            "total_reports": len(self._state.entries),
            "agent_count": len(self.list_agents()),
            "seq": self._state._seq,
            "callback_count": len(self._callbacks),
        }

    def reset(self):
        """Reset all state."""
        self._state = AgentHealthAggregatorState()
        self._callbacks = {}

    @staticmethod
    def _worst_status(statuses: list) -> str:
        """Return the worst status from a list of statuses."""
        if "unhealthy" in statuses:
            return "unhealthy"
        if "degraded" in statuses:
            return "degraded"
        return "healthy"
