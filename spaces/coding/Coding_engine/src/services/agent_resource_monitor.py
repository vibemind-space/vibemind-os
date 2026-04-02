"""Agent Resource Monitor -- monitors per-agent resource usage.

Tracks CPU, memory, disk, and network quota consumption per agent.
Supports thresholds, usage history, and resource summaries for
capacity planning and alerting.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ResourceSnapshot:
    """Single resource usage snapshot."""

    snapshot_id: str
    agent_id: str
    resource_type: str
    value: float
    unit: str
    timestamp: float
    tags: List[str]


class AgentResourceMonitor:
    """Monitors per-agent resource usage (CPU, memory, disk, network quotas)."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._snapshots: Dict[str, ResourceSnapshot] = {}
        self._agent_index: Dict[str, List[str]] = {}
        self._thresholds: Dict[str, Dict[str, float]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # stats counters
        self._total_recorded: int = 0
        self._total_threshold_checks: int = 0
        self._total_threshold_exceeded: int = 0
        self._total_purged: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'arm-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"arm-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest snapshots when at capacity."""
        if len(self._snapshots) < self._max_entries:
            return
        sorted_snaps = sorted(
            self._snapshots.values(), key=lambda s: s.timestamp
        )
        remove_count = len(self._snapshots) - self._max_entries + 1
        for snap in sorted_snaps[:remove_count]:
            self._remove_snapshot(snap.snapshot_id)
            logger.debug("snapshot_pruned", snapshot_id=snap.snapshot_id)

    def _remove_snapshot(self, snapshot_id: str) -> None:
        """Remove a snapshot from stores and indexes."""
        snap = self._snapshots.pop(snapshot_id, None)
        if not snap:
            return
        agent_list = self._agent_index.get(snap.agent_id, [])
        if snapshot_id in agent_list:
            agent_list.remove(snapshot_id)
        if not agent_list and snap.agent_id in self._agent_index:
            del self._agent_index[snap.agent_id]

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_usage(
        self,
        agent_id: str,
        resource_type: str,
        value: float,
        unit: str = "units",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Record a resource usage snapshot for an agent.

        Returns the snapshot_id, or '' on failure.
        """
        if not agent_id or not resource_type:
            logger.warning("record_usage_invalid", agent_id=agent_id,
                           resource_type=resource_type)
            return ""
        if value < 0:
            logger.warning("record_usage_negative_value", agent_id=agent_id,
                           value=value)
            return ""

        self._prune_if_needed()

        sid = self._next_id(f"{agent_id}:{resource_type}")
        now = time.time()

        snap = ResourceSnapshot(
            snapshot_id=sid,
            agent_id=agent_id,
            resource_type=resource_type,
            value=value,
            unit=unit,
            timestamp=now,
            tags=list(tags) if tags else [],
        )
        self._snapshots[sid] = snap
        self._agent_index.setdefault(agent_id, []).append(sid)
        self._total_recorded += 1

        logger.info("usage_recorded", snapshot_id=sid, agent_id=agent_id,
                     resource_type=resource_type, value=value, unit=unit)

        # auto-check threshold
        threshold = self._thresholds.get(agent_id, {}).get(resource_type)
        if threshold is not None and value > threshold:
            self._total_threshold_exceeded += 1
            logger.warning("threshold_exceeded", agent_id=agent_id,
                           resource_type=resource_type, value=value,
                           max_value=threshold)
            self._fire("threshold_exceeded", {
                "snapshot_id": sid,
                "agent_id": agent_id,
                "resource_type": resource_type,
                "value": value,
                "max_value": threshold,
            })

        self._fire("usage_recorded", {
            "snapshot_id": sid,
            "agent_id": agent_id,
            "resource_type": resource_type,
            "value": value,
            "unit": unit,
        })
        return sid

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _snap_to_dict(self, snap: ResourceSnapshot) -> Dict[str, Any]:
        """Convert a snapshot dataclass to a plain dict."""
        return {
            "snapshot_id": snap.snapshot_id,
            "agent_id": snap.agent_id,
            "resource_type": snap.resource_type,
            "value": snap.value,
            "unit": snap.unit,
            "timestamp": snap.timestamp,
            "tags": list(snap.tags),
        }

    def get_latest_usage(
        self, agent_id: str, resource_type: str
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent usage snapshot for an agent and resource type.

        Returns None if no matching snapshot exists.
        """
        sids = self._agent_index.get(agent_id, [])
        latest: Optional[ResourceSnapshot] = None
        for sid in sids:
            snap = self._snapshots.get(sid)
            if not snap or snap.resource_type != resource_type:
                continue
            if latest is None or snap.timestamp > latest.timestamp:
                latest = snap

        if latest is None:
            return None
        return self._snap_to_dict(latest)

    def get_usage_history(
        self,
        agent_id: str,
        resource_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get usage history for an agent, optionally filtered by resource type.

        Results are ordered newest-first and capped at *limit*.
        """
        sids = self._agent_index.get(agent_id, [])
        results: List[ResourceSnapshot] = []
        for sid in sids:
            snap = self._snapshots.get(sid)
            if not snap:
                continue
            if resource_type is not None and snap.resource_type != resource_type:
                continue
            results.append(snap)

        results.sort(key=lambda s: s.timestamp, reverse=True)
        return [self._snap_to_dict(s) for s in results[:limit]]

    def get_agent_resource_summary(
        self, agent_id: str
    ) -> Dict[str, Any]:
        """Get a summary of the latest value for each resource type
        tracked for the given agent.

        Returns a dict keyed by resource_type with latest value and unit.
        """
        sids = self._agent_index.get(agent_id, [])
        latest_by_type: Dict[str, ResourceSnapshot] = {}

        for sid in sids:
            snap = self._snapshots.get(sid)
            if not snap:
                continue
            existing = latest_by_type.get(snap.resource_type)
            if existing is None or snap.timestamp > existing.timestamp:
                latest_by_type[snap.resource_type] = snap

        summary: Dict[str, Any] = {}
        for rtype, snap in sorted(latest_by_type.items()):
            summary[rtype] = {
                "value": snap.value,
                "unit": snap.unit,
                "timestamp": snap.timestamp,
                "snapshot_id": snap.snapshot_id,
            }

        logger.debug("agent_resource_summary", agent_id=agent_id,
                      resource_types=list(summary.keys()))
        return summary

    def list_monitored_agents(self) -> List[str]:
        """Return a sorted list of agent IDs that have recorded snapshots."""
        return sorted(self._agent_index.keys())

    # ------------------------------------------------------------------
    # Thresholds
    # ------------------------------------------------------------------

    def set_threshold(
        self, agent_id: str, resource_type: str, max_value: float
    ) -> bool:
        """Set a usage threshold for an agent's resource type.

        Returns False if inputs are invalid.
        """
        if not agent_id or not resource_type:
            return False
        if max_value < 0:
            logger.warning("set_threshold_negative", agent_id=agent_id,
                           resource_type=resource_type, max_value=max_value)
            return False

        self._thresholds.setdefault(agent_id, {})[resource_type] = max_value
        logger.info("threshold_set", agent_id=agent_id,
                     resource_type=resource_type, max_value=max_value)
        self._fire("threshold_set", {
            "agent_id": agent_id,
            "resource_type": resource_type,
            "max_value": max_value,
        })
        return True

    def check_threshold(
        self, agent_id: str, resource_type: str
    ) -> Dict[str, Any]:
        """Check whether the latest usage exceeds the configured threshold.

        Returns a dict with keys: exceeded, current, max.
        If no threshold is set, max is 0 and exceeded is False.
        """
        self._total_threshold_checks += 1

        max_value = self._thresholds.get(agent_id, {}).get(resource_type, 0.0)
        latest = self.get_latest_usage(agent_id, resource_type)
        current = latest["value"] if latest else 0.0

        exceeded = max_value > 0 and current > max_value
        if exceeded:
            self._total_threshold_exceeded += 1
            logger.warning("threshold_check_exceeded", agent_id=agent_id,
                           resource_type=resource_type, current=current,
                           max_value=max_value)

        return {
            "exceeded": exceeded,
            "current": current,
            "max": max_value,
        }

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Remove snapshots older than *before_timestamp*.

        If *before_timestamp* is None, removes all snapshots.
        Returns the number of snapshots removed.
        """
        to_remove: List[str] = []
        for sid, snap in self._snapshots.items():
            if before_timestamp is None or snap.timestamp < before_timestamp:
                to_remove.append(sid)

        for sid in to_remove:
            self._remove_snapshot(sid)

        count = len(to_remove)
        self._total_purged += count
        logger.info("purge_complete", removed=count,
                     before_timestamp=before_timestamp)
        self._fire("purged", {
            "removed": count,
            "before_timestamp": before_timestamp,
        })
        return count

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return monitor statistics."""
        unique_resource_types: set[str] = set()
        for snap in self._snapshots.values():
            unique_resource_types.add(snap.resource_type)

        return {
            "current_snapshots": len(self._snapshots),
            "monitored_agents": len(self._agent_index),
            "unique_resource_types": len(unique_resource_types),
            "total_recorded": self._total_recorded,
            "total_threshold_checks": self._total_threshold_checks,
            "total_threshold_exceeded": self._total_threshold_exceeded,
            "total_purged": self._total_purged,
            "max_entries": self._max_entries,
            "active_thresholds": sum(
                len(v) for v in self._thresholds.values()
            ),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._snapshots.clear()
        self._agent_index.clear()
        self._thresholds.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_recorded = 0
        self._total_threshold_checks = 0
        self._total_threshold_exceeded = 0
        self._total_purged = 0
        logger.info("monitor_reset")
