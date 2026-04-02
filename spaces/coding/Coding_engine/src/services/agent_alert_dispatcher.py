"""Agent Alert Dispatcher -- dispatches alerts to agents based on severity and type.

Provides an in-memory alert dispatching system that routes alerts to agents
based on severity level and alert type.  Each alert captures the target agent,
severity, message, type, acknowledgement status, and creation metadata.  The
dispatcher supports per-agent querying, severity filtering, acknowledgement
tracking, and automatic pruning when the entry limit is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"info", "warning", "critical"}


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _Alert:
    """A single dispatched alert."""

    alert_id: str = ""
    agent_id: str = ""
    severity: str = "info"
    message: str = ""
    alert_type: str = "general"
    acknowledged: bool = False
    created_at: float = 0.0
    seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentAlertDispatcher:
    """In-memory alert dispatcher for agents.

    Parameters
    ----------
    max_entries:
        Maximum number of alerts to keep.  When the limit is reached the
        oldest quarter of alerts is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._alerts: Dict[str, _Alert] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}

        # indexes for fast lookup
        self._agent_index: Dict[str, List[str]] = {}      # agent_id -> [alert_id]
        self._severity_index: Dict[str, List[str]] = {}   # severity  -> [alert_id]
        self._type_index: Dict[str, List[str]] = {}       # alert_type -> [alert_id]

        # stats counters
        self._stats: Dict[str, int] = {
            "total_sent": 0,
            "total_acknowledged": 0,
            "total_pruned": 0,
            "total_queries": 0,
        }

        logger.debug("agent_alert_dispatcher.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # Sending alerts
    # ------------------------------------------------------------------

    def send_alert(
        self,
        agent_id: str,
        severity: str,
        message: str,
        alert_type: str = "general",
    ) -> str:
        """Dispatch an alert to an agent and return its ``alert_id``.

        Returns an empty string when *agent_id* or *message* is falsy,
        or when *severity* is not one of ``info``, ``warning``, ``critical``.
        """
        if not agent_id or not message:
            return ""
        if severity not in VALID_SEVERITIES:
            return ""

        with self._lock:
            # prune if at capacity
            if len(self._alerts) >= self._max_entries:
                self._prune()

            self._seq += 1
            now = time.time()
            raw = f"{agent_id}-{severity}-{now}-{self._seq}"
            alert_id = "aad-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            alert = _Alert(
                alert_id=alert_id,
                agent_id=agent_id,
                severity=severity,
                message=message,
                alert_type=alert_type,
                acknowledged=False,
                created_at=now,
                seq=self._seq,
            )
            self._alerts[alert_id] = alert

            # update indexes
            self._agent_index.setdefault(agent_id, []).append(alert_id)
            self._severity_index.setdefault(severity, []).append(alert_id)
            self._type_index.setdefault(alert_type, []).append(alert_id)

            self._stats["total_sent"] += 1

        logger.debug(
            "agent_alert_dispatcher.send_alert alert_id=%s agent_id=%s severity=%s type=%s",
            alert_id,
            agent_id,
            severity,
            alert_type,
        )
        self._fire("alert_sent", {
            "alert_id": alert_id,
            "agent_id": agent_id,
            "severity": severity,
            "alert_type": alert_type,
        })
        return alert_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_alerts(
        self,
        agent_id: str,
        severity: str = "",
    ) -> List[Dict[str, Any]]:
        """Return alerts for *agent_id*, optionally filtered by *severity*.

        Results are returned newest-first.
        """
        with self._lock:
            self._stats["total_queries"] += 1
            ids = self._agent_index.get(agent_id, [])
            alerts = [self._alerts[aid] for aid in ids if aid in self._alerts]
            if severity:
                alerts = [a for a in alerts if a.severity == severity]
            alerts.sort(key=lambda a: (a.created_at, a.seq), reverse=True)
            return [self._to_dict(a) for a in alerts]

    def get_latest_alert(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent alert for *agent_id*, or ``None``."""
        with self._lock:
            self._stats["total_queries"] += 1
            ids = self._agent_index.get(agent_id, [])
            alerts = [self._alerts[aid] for aid in ids if aid in self._alerts]
            if not alerts:
                return None
            alerts.sort(key=lambda a: (a.created_at, a.seq), reverse=True)
            return self._to_dict(alerts[0])

    # ------------------------------------------------------------------
    # Acknowledgement
    # ------------------------------------------------------------------

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert.  Returns ``False`` if not found or already acknowledged."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return False
            if alert.acknowledged:
                return False
            alert.acknowledged = True
            self._stats["total_acknowledged"] += 1

        logger.debug("agent_alert_dispatcher.acknowledge alert_id=%s", alert_id)
        self._fire("alert_acknowledged", {"alert_id": alert_id})
        return True

    def get_unacknowledged_count(self, agent_id: str = "") -> int:
        """Count unacknowledged alerts, optionally filtered to a single agent."""
        with self._lock:
            if agent_id:
                ids = self._agent_index.get(agent_id, [])
                return sum(
                    1
                    for aid in ids
                    if aid in self._alerts and not self._alerts[aid].acknowledged
                )
            return sum(
                1 for a in self._alerts.values() if not a.acknowledged
            )

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_alert_count(self) -> int:
        """Return the total number of alerts currently stored."""
        with self._lock:
            return len(self._alerts)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one alert."""
        with self._lock:
            return [
                aid
                for aid, ids in self._agent_index.items()
                if any(eid in self._alerts for eid in ids)
            ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns ``False`` if *name* is taken."""
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            return {
                **self._stats,
                "current_alerts": len(self._alerts),
                "unique_agents": len([
                    a for a, ids in self._agent_index.items()
                    if any(eid in self._alerts for eid in ids)
                ]),
                "unique_severities": len([
                    s for s, ids in self._severity_index.items()
                    if any(eid in self._alerts for eid in ids)
                ]),
                "unique_types": len([
                    t for t, ids in self._type_index.items()
                    if any(eid in self._alerts for eid in ids)
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._alerts.clear()
            self._agent_index.clear()
            self._severity_index.clear()
            self._type_index.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_alert_dispatcher.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, a: _Alert) -> Dict[str, Any]:
        """Convert an alert to a plain dict."""
        return {
            "alert_id": a.alert_id,
            "agent_id": a.agent_id,
            "severity": a.severity,
            "message": a.message,
            "alert_type": a.alert_type,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at,
            "seq": a.seq,
        }

    def _remove_alert(self, alert_id: str) -> None:
        """Remove a single alert from the store and all indexes."""
        a = self._alerts.pop(alert_id, None)
        if a is None:
            return

        # clean agent index
        ids = self._agent_index.get(a.agent_id)
        if ids:
            try:
                ids.remove(alert_id)
            except ValueError:
                pass

        # clean severity index
        ids = self._severity_index.get(a.severity)
        if ids:
            try:
                ids.remove(alert_id)
            except ValueError:
                pass

        # clean type index
        ids = self._type_index.get(a.alert_type)
        if ids:
            try:
                ids.remove(alert_id)
            except ValueError:
                pass

    def _prune(self) -> None:
        """Remove the oldest quarter of alerts when at capacity."""
        alerts = sorted(self._alerts.values(), key=lambda a: a.seq)
        to_remove = max(len(alerts) // 4, 1)
        for a in alerts[:to_remove]:
            self._remove_alert(a.alert_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("agent_alert_dispatcher.prune removed=%d", to_remove)
