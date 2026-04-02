"""Agent metric collector for recording and querying agent runtime metrics.

Collects metrics such as cpu_usage, memory_usage, request_count, error_count,
latency, and any other named metric per agent.  Provides filtering, averaging,
and latest-value lookups.

Usage::

    collector = AgentMetricCollector()
    mid = collector.record_metric("agent-1", "cpu_usage", 72.5)
    avg = collector.get_average("agent-1", "cpu_usage")
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentMetricCollector:
    """Collects and queries per-agent runtime metrics."""

    max_entries: int = 10000
    _metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_recorded: int = field(default=0)

    def _next_id(self, agent_id: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{agent_id}{self._seq}".encode()).hexdigest()[:12]
        return f"amc-{raw}"

    def _prune(self) -> None:
        while len(self._metrics) > self.max_entries:
            oldest_id = min(
                self._metrics,
                key=lambda mid: (
                    self._metrics[mid]["created_at"],
                    self._metrics[mid]["seq"],
                ),
            )
            del self._metrics[oldest_id]
            logger.debug("agent_metric_collector.pruned", metric_id=oldest_id)

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "agent_metric_collector.callback_error",
                    callback=name,
                    event=event,
                )

    # -- public API ----------------------------------------------------------

    def record_metric(
        self, agent_id: str, metric_name: str, value: float
    ) -> str:
        """Record a metric value for an agent. Returns the metric ID."""
        metric_id = self._next_id(agent_id)
        now = time.time()
        entry: Dict[str, Any] = {
            "metric_id": metric_id,
            "agent_id": agent_id,
            "metric_name": metric_name,
            "value": value,
            "created_at": now,
            "seq": self._seq,
        }
        self._metrics[metric_id] = entry
        self._total_recorded += 1
        self._prune()
        logger.info(
            "agent_metric_collector.metric_recorded",
            metric_id=metric_id,
            agent_id=agent_id,
            metric_name=metric_name,
            value=value,
        )
        self._fire(
            "metric_recorded",
            {
                "metric_id": metric_id,
                "agent_id": agent_id,
                "metric_name": metric_name,
                "value": value,
            },
        )
        return metric_id

    def get_metrics(
        self, agent_id: str, metric_name: str = ""
    ) -> List[Dict[str, Any]]:
        """Return metrics for an agent, optionally filtered by metric_name."""
        results = [
            dict(m)
            for m in self._metrics.values()
            if m["agent_id"] == agent_id
            and (not metric_name or m["metric_name"] == metric_name)
        ]
        results.sort(key=lambda m: (m["created_at"], m["seq"]))
        return results

    def get_latest_metric(
        self, agent_id: str, metric_name: str
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent metric dict for a given agent and name, or None."""
        matches = [
            m
            for m in self._metrics.values()
            if m["agent_id"] == agent_id and m["metric_name"] == metric_name
        ]
        if not matches:
            return None
        latest = max(matches, key=lambda m: (m["created_at"], m["seq"]))
        return dict(latest)

    def get_average(self, agent_id: str, metric_name: str) -> float:
        """Return the average value for a given agent and metric name."""
        values = [
            m["value"]
            for m in self._metrics.values()
            if m["agent_id"] == agent_id and m["metric_name"] == metric_name
        ]
        if not values:
            return 0.0
        return sum(values) / len(values)

    def get_metric_count(self, agent_id: str = "") -> int:
        """Return total metric count, or count for a specific agent."""
        if not agent_id:
            return len(self._metrics)
        return sum(
            1 for m in self._metrics.values() if m["agent_id"] == agent_id
        )

    def list_agents(self) -> List[str]:
        """Return a list of unique agent IDs that have recorded metrics."""
        seen: set[str] = set()
        result: List[str] = []
        for m in self._metrics.values():
            aid = m["agent_id"]
            if aid not in seen:
                seen.add(aid)
                result.append(aid)
        return result

    def get_total_metrics(self) -> int:
        """Return the total number of stored metrics."""
        return len(self._metrics)

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback
        logger.debug("agent_metric_collector.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("agent_metric_collector.callback_removed", name=name)
            return True
        return False

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_metrics": len(self._metrics),
            "total_recorded": self._total_recorded,
            "max_entries": self.max_entries,
            "agents": len(self.list_agents()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._metrics.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_recorded = 0
        logger.info("agent_metric_collector.reset")
