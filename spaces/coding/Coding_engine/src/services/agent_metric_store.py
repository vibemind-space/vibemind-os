"""Agent Metric Store – stores and queries per-agent metrics with time-series data.

Provides recording, retrieval, aggregation, and pruning of numeric metrics
keyed by agent ID and metric name.  Supports history queries, per-agent
summaries, and configurable entry limits with automatic pruning.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _MetricEntry:
    """A single recorded metric data point."""

    metric_id: str
    agent_id: str
    metric_name: str
    value: float
    tags: List[str]
    timestamp: float


@dataclass
class _StoreState:
    """Internal state for the metric store."""

    entries: Dict[str, _MetricEntry] = field(default_factory=dict)
    # agent_id -> metric_name -> list of metric_ids (chronological order)
    agent_index: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    seq: int = 0
    total_recorded: int = 0
    total_pruned: int = 0


class AgentMetricStore:
    """Stores and queries per-agent metrics with time-series data."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._state = _StoreState()
        logger.info("agent_metric_store.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, metric_name: str) -> str:
        self._state.seq += 1
        now = time.time()
        raw = f"{agent_id}-{metric_name}-{now}-{self._state.seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"ams-{digest}"

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent_id: str,
        metric_name: str,
        value: float,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Record a metric value for an agent. Returns the metric_id."""
        if not agent_id or not metric_name:
            logger.warning("agent_metric_store.record.invalid_args")
            return ""

        # Prune if at capacity
        if len(self._state.entries) >= self._max_entries:
            self._prune_oldest()

        mid = self._generate_id(agent_id, metric_name)
        now = time.time()

        entry = _MetricEntry(
            metric_id=mid,
            agent_id=agent_id,
            metric_name=metric_name,
            value=value,
            tags=list(tags) if tags else [],
            timestamp=now,
        )
        self._state.entries[mid] = entry

        # Update agent index
        if agent_id not in self._state.agent_index:
            self._state.agent_index[agent_id] = {}
        agent_metrics = self._state.agent_index[agent_id]
        if metric_name not in agent_metrics:
            agent_metrics[metric_name] = []
        agent_metrics[metric_name].append(mid)

        self._state.total_recorded += 1
        logger.debug(
            "agent_metric_store.recorded",
            metric_id=mid,
            agent_id=agent_id,
            metric_name=metric_name,
            value=value,
        )
        self._fire("recorded", {"metric_id": mid, "agent_id": agent_id, "metric_name": metric_name, "value": value})
        return mid

    def _prune_oldest(self) -> None:
        """Remove the oldest 10% of entries when at capacity."""
        count = max(1, self._max_entries // 10)
        sorted_ids = sorted(
            self._state.entries.keys(),
            key=lambda k: self._state.entries[k].timestamp,
        )
        for mid in sorted_ids[:count]:
            self._remove_entry(mid)
            self._state.total_pruned += 1

    def _remove_entry(self, metric_id: str) -> None:
        """Remove a single entry from entries and agent index."""
        entry = self._state.entries.pop(metric_id, None)
        if not entry:
            return
        agent_metrics = self._state.agent_index.get(entry.agent_id, {})
        name_list = agent_metrics.get(entry.metric_name, [])
        if metric_id in name_list:
            name_list.remove(metric_id)
        # Clean up empty structures
        if not name_list and entry.metric_name in agent_metrics:
            del agent_metrics[entry.metric_name]
        if not agent_metrics and entry.agent_id in self._state.agent_index:
            del self._state.agent_index[entry.agent_id]

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: _MetricEntry) -> Dict[str, Any]:
        """Convert a metric entry to a dict representation."""
        return {
            "metric_id": entry.metric_id,
            "agent_id": entry.agent_id,
            "metric_name": entry.metric_name,
            "value": entry.value,
            "tags": list(entry.tags),
            "timestamp": entry.timestamp,
        }

    def get_metric(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """Return a single metric entry by ID, or None."""
        entry = self._state.entries.get(metric_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    def get_latest(
        self, agent_id: str, metric_name: str
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent metric value for an agent+metric_name."""
        agent_metrics = self._state.agent_index.get(agent_id, {})
        id_list = agent_metrics.get(metric_name, [])
        if not id_list:
            return None
        latest_id = id_list[-1]
        entry = self._state.entries.get(latest_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    def get_history(
        self, agent_id: str, metric_name: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* most recent values for an agent+metric_name."""
        agent_metrics = self._state.agent_index.get(agent_id, {})
        id_list = agent_metrics.get(metric_name, [])
        if not id_list:
            return []
        # Take the last `limit` entries
        selected = id_list[-limit:] if limit < len(id_list) else id_list
        results: List[Dict[str, Any]] = []
        for mid in selected:
            entry = self._state.entries.get(mid)
            if entry:
                results.append(self._entry_to_dict(entry))
        return results

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def get_average(self, agent_id: str, metric_name: str) -> float:
        """Return the average value for an agent+metric_name, or 0.0."""
        agent_metrics = self._state.agent_index.get(agent_id, {})
        id_list = agent_metrics.get(metric_name, [])
        if not id_list:
            return 0.0
        total = 0.0
        count = 0
        for mid in id_list:
            entry = self._state.entries.get(mid)
            if entry:
                total += entry.value
                count += 1
        return total / count if count > 0 else 0.0

    def get_agent_summary(self, agent_id: str) -> Dict[str, Any]:
        """Return a summary of all metrics for an agent.

        Returns::

            {
                "agent_id": "...",
                "metrics": {
                    "<name>": {
                        "count": int,
                        "avg": float,
                        "min": float,
                        "max": float,
                        "latest": float,
                    },
                    ...
                },
            }
        """
        agent_metrics = self._state.agent_index.get(agent_id, {})
        metrics_summary: Dict[str, Dict[str, Any]] = {}

        for metric_name, id_list in agent_metrics.items():
            values: List[float] = []
            for mid in id_list:
                entry = self._state.entries.get(mid)
                if entry:
                    values.append(entry.value)
            if not values:
                continue
            metrics_summary[metric_name] = {
                "count": len(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "latest": values[-1],
            }

        return {
            "agent_id": agent_id,
            "metrics": metrics_summary,
        }

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return a list of all agent IDs that have recorded metrics."""
        return list(self._state.agent_index.keys())

    def list_metrics(self, agent_id: Optional[str] = None) -> List[str]:
        """Return unique metric names, optionally filtered by agent_id."""
        if agent_id is not None:
            agent_metrics = self._state.agent_index.get(agent_id, {})
            return list(agent_metrics.keys())
        # All unique metric names across all agents
        names: set[str] = set()
        for agent_metrics in self._state.agent_index.values():
            names.update(agent_metrics.keys())
        return sorted(names)

    # ------------------------------------------------------------------
    # Purging
    # ------------------------------------------------------------------

    def purge(
        self,
        agent_id: Optional[str] = None,
        before_timestamp: Optional[float] = None,
    ) -> int:
        """Remove entries matching the filter criteria.

        Returns the number of entries removed.
        """
        to_remove: List[str] = []

        for mid, entry in self._state.entries.items():
            if agent_id is not None and entry.agent_id != agent_id:
                continue
            if before_timestamp is not None and entry.timestamp >= before_timestamp:
                continue
            # If neither filter is set, match everything
            if agent_id is None and before_timestamp is None:
                to_remove.append(mid)
                continue
            to_remove.append(mid)

        for mid in to_remove:
            self._remove_entry(mid)

        removed = len(to_remove)
        if removed:
            self._state.total_pruned += removed
            logger.info(
                "agent_metric_store.purged",
                count=removed,
                agent_id=agent_id,
                before_timestamp=before_timestamp,
            )
            self._fire("purged", {"count": removed, "agent_id": agent_id})
        return removed

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if it existed."""
        return self._state.callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("agent_metric_store.callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        unique_agents = len(self._state.agent_index)
        unique_metrics: set[str] = set()
        for agent_metrics in self._state.agent_index.values():
            unique_metrics.update(agent_metrics.keys())

        return {
            "current_entries": len(self._state.entries),
            "max_entries": self._max_entries,
            "total_recorded": self._state.total_recorded,
            "total_pruned": self._state.total_pruned,
            "unique_agents": unique_agents,
            "unique_metrics": len(unique_metrics),
            "callbacks": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all data and reset counters."""
        self._state = _StoreState()
        logger.info("agent_metric_store.reset")
