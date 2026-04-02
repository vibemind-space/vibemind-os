"""Aggregate and display agent metrics in dashboard format."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentMetricDashboardState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentMetricDashboard:
    """Aggregate and display agent metrics in dashboard format."""

    PREFIX = "amd-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentMetricDashboardState()
        self._callbacks: dict = {}
        logger.info("AgentMetricDashboard initialised")

    # ── ID generation ──────────────────────────────────────────────

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Callback machinery ─────────────────────────────────────────

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        return self._callbacks.pop(cb_id, None) is not None

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self):
        entries = self._state.entries
        if len(entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                entries,
                key=lambda k: entries[k].get("updated_at", 0),
            )
            to_remove = len(entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del entries[k]
            logger.info("Pruned %d metric entries", to_remove)

    # ── Core helpers ───────────────────────────────────────────────

    def _metric_key(self, agent_id: str, metric_name: str) -> str:
        return f"{agent_id}::{metric_name}"

    # ── Public API ─────────────────────────────────────────────────

    def register_metric(
        self, agent_id: str, metric_name: str, metric_type: str = "gauge"
    ) -> str:
        if metric_type not in ("gauge", "counter", "histogram"):
            raise ValueError(f"Invalid metric_type: {metric_type}")

        key = self._metric_key(agent_id, metric_name)
        metric_id = self._generate_id(key)
        now = time.time()

        self._state.entries[metric_id] = {
            "metric_id": metric_id,
            "agent_id": agent_id,
            "metric_name": metric_name,
            "metric_type": metric_type,
            "values": [],
            "current": None,
            "min": None,
            "max": None,
            "sum": 0.0,
            "count": 0,
            "created_at": now,
            "updated_at": now,
        }

        self._prune()
        self._fire("metric_registered", {"metric_id": metric_id, "agent_id": agent_id, "metric_name": metric_name})
        logger.info("Registered metric %s for agent %s", metric_name, agent_id)
        return metric_id

    def record_value(self, agent_id: str, metric_name: str, value) -> bool:
        key = self._metric_key(agent_id, metric_name)
        entry = self._find_entry(agent_id, metric_name)
        if entry is None:
            logger.warning("No metric registered for %s / %s", agent_id, metric_name)
            return False

        now = time.time()
        numeric = float(value)
        entry["values"].append(numeric)
        entry["current"] = numeric
        entry["count"] += 1
        entry["sum"] += numeric

        if entry["min"] is None or numeric < entry["min"]:
            entry["min"] = numeric
        if entry["max"] is None or numeric > entry["max"]:
            entry["max"] = numeric

        entry["updated_at"] = now

        self._fire("value_recorded", {"agent_id": agent_id, "metric_name": metric_name, "value": numeric})
        return True

    def get_metric(self, agent_id: str, metric_name: str) -> dict:
        entry = self._find_entry(agent_id, metric_name)
        if entry is None:
            return {}
        avg = entry["sum"] / entry["count"] if entry["count"] > 0 else None
        return {
            "current": entry["current"],
            "min": entry["min"],
            "max": entry["max"],
            "avg": avg,
            "count": entry["count"],
        }

    def get_dashboard(self, agent_id: str) -> dict:
        dashboard: dict = {}
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                name = entry["metric_name"]
                avg = entry["sum"] / entry["count"] if entry["count"] > 0 else None
                dashboard[name] = {
                    "current": entry["current"],
                    "min": entry["min"],
                    "max": entry["max"],
                    "avg": avg,
                    "count": entry["count"],
                    "metric_type": entry["metric_type"],
                }
        return dashboard

    def get_all_dashboards(self) -> dict:
        agents = self.list_agents()
        return {aid: self.get_dashboard(aid) for aid in agents}

    def get_metric_entry(self, metric_id: str):
        return self._state.entries.get(metric_id)

    def get_metric_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def list_agents(self) -> list:
        agents = list({e["agent_id"] for e in self._state.entries.values()})
        agents.sort()
        return agents

    def get_stats(self) -> dict:
        return {
            "total_metrics": len(self._state.entries),
            "total_agents": len(self.list_agents()),
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        self._state = AgentMetricDashboardState()
        self._callbacks.clear()
        logger.info("AgentMetricDashboard reset")

    # ── Internal helpers ───────────────────────────────────────────

    def _find_entry(self, agent_id: str, metric_name: str):
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id and entry["metric_name"] == metric_name:
                return entry
        return None
