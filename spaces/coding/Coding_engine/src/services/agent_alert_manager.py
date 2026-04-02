"""Agent Alert Manager -- manages alerts for agent conditions.

Provides an in-memory alert management system where agents can trigger alerts
with severity levels, acknowledge them, and query active alerts.  Each alert
captures the agent ID, alert type, message, severity, acknowledgement status,
and creation metadata.  The manager supports per-agent querying, severity and
acknowledgement filtering, and automatic pruning when the entry limit is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

VALID_SEVERITIES = {"info", "warning", "error", "critical"}


# ------------------------------------------------------------------
# State dataclass
# ------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the alert manager."""

    alerts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentAlertManager:
    """In-memory alert manager for agents.

    Parameters
    ----------
    max_entries:
        Maximum number of alerts to keep.  When the limit is reached the
        oldest quarter of alerts is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = _State()
        self._callbacks: Dict[str, Callable] = {}

        logger.debug("agent_alert_manager.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # Raising alerts
    # ------------------------------------------------------------------

    def raise_alert(
        self,
        agent_id: str,
        alert_type: str,
        message: str,
        severity: str = "warning",
    ) -> str:
        """Raise an alert for an agent and return its ``alert_id``.

        *severity* must be one of ``info``, ``warning``, ``error``, ``critical``.
        Returns the alert ID (``aam-xxx``).
        """
        if severity not in VALID_SEVERITIES:
            severity = "warning"

        with self._lock:
            # prune if at capacity
            if len(self._state.alerts) >= self._max_entries:
                self._prune()

            self._state._seq += 1
            now = time.time()
            raw = f"{agent_id}-{alert_type}-{now}-{self._state._seq}"
            alert_id = "aam-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            alert = {
                "alert_id": alert_id,
                "agent_id": agent_id,
                "alert_type": alert_type,
                "message": message,
                "severity": severity,
                "acknowledged": False,
                "created_at": now,
                "seq": self._state._seq,
            }
            self._state.alerts[alert_id] = alert

        logger.debug(
            "agent_alert_manager.raise_alert",
            alert_id=alert_id,
            agent_id=agent_id,
            alert_type=alert_type,
            severity=severity,
        )
        self._fire("alert_raised", {
            "alert_id": alert_id,
            "agent_id": agent_id,
            "alert_type": alert_type,
            "severity": severity,
        })
        return alert_id

    # ------------------------------------------------------------------
    # Acknowledgement
    # ------------------------------------------------------------------

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged.  Returns ``False`` if not found."""
        with self._lock:
            alert = self._state.alerts.get(alert_id)
            if alert is None:
                return False
            alert["acknowledged"] = True

        logger.debug("agent_alert_manager.acknowledge_alert", alert_id=alert_id)
        self._fire("alert_acknowledged", {"alert_id": alert_id})
        return True

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get a single alert by ID, or ``None`` if not found."""
        with self._lock:
            alert = self._state.alerts.get(alert_id)
            if alert is None:
                return None
            return dict(alert)

    def get_alerts(
        self,
        agent_id: str,
        severity: str = "",
        acknowledged: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Get alerts for *agent_id*, optionally filtered by severity and/or acknowledged status."""
        with self._lock:
            results = [
                a for a in self._state.alerts.values()
                if a["agent_id"] == agent_id
            ]
            if severity:
                results = [a for a in results if a["severity"] == severity]
            if acknowledged is not None:
                results = [a for a in results if a["acknowledged"] == acknowledged]
            results.sort(key=lambda a: (a["created_at"], a["seq"]), reverse=True)
            return [dict(a) for a in results]

    def get_active_alerts(self, agent_id: str = "") -> List[Dict[str, Any]]:
        """Get all unacknowledged alerts, optionally for a specific agent."""
        with self._lock:
            results = [
                a for a in self._state.alerts.values()
                if not a["acknowledged"]
            ]
            if agent_id:
                results = [a for a in results if a["agent_id"] == agent_id]
            results.sort(key=lambda a: (a["created_at"], a["seq"]), reverse=True)
            return [dict(a) for a in results]

    # ------------------------------------------------------------------
    # Dismissal
    # ------------------------------------------------------------------

    def dismiss_alert(self, alert_id: str) -> bool:
        """Remove an alert entirely.  Returns ``False`` if not found."""
        with self._lock:
            if alert_id not in self._state.alerts:
                return False
            del self._state.alerts[alert_id]

        logger.debug("agent_alert_manager.dismiss_alert", alert_id=alert_id)
        self._fire("alert_dismissed", {"alert_id": alert_id})
        return True

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_alert_count(self, agent_id: str = "") -> int:
        """Count alerts.  If *agent_id* is given, count only for that agent."""
        with self._lock:
            if agent_id:
                return sum(
                    1 for a in self._state.alerts.values()
                    if a["agent_id"] == agent_id
                )
            return len(self._state.alerts)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one alert."""
        with self._lock:
            agents = set()
            for a in self._state.alerts.values():
                agents.add(a["agent_id"])
            return sorted(agents)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._callbacks:
                del self._callbacks[name]
                return True
            return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            agents = set()
            severities = set()
            ack_count = 0
            for a in self._state.alerts.values():
                agents.add(a["agent_id"])
                severities.add(a["severity"])
                if a["acknowledged"]:
                    ack_count += 1
            return {
                "total_alerts": len(self._state.alerts),
                "acknowledged_count": ack_count,
                "unacknowledged_count": len(self._state.alerts) - ack_count,
                "unique_agents": len(agents),
                "unique_severities": len(severities),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.alerts.clear()
            self._state._seq = 0
            self._callbacks.clear()
        logger.debug("agent_alert_manager.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of alerts when at capacity."""
        alerts = sorted(self._state.alerts.values(), key=lambda a: a["seq"])
        to_remove = max(len(alerts) // 4, 1)
        for a in alerts[:to_remove]:
            del self._state.alerts[a["alert_id"]]
        logger.debug("agent_alert_manager.prune", removed=to_remove)
