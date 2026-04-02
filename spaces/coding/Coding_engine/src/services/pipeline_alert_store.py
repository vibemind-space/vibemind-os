"""Pipeline alert store.

Manages pipeline alerts including thresholds, firing conditions,
alert history, and acknowledgment tracking. Provides query and
summary utilities for monitoring pipeline health.
"""

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"info", "warning", "error", "critical"}
VALID_STATUSES = {"open", "acknowledged", "resolved"}


@dataclass
class AlertEntry:
    """A single pipeline alert record."""
    alert_id: str = ""
    pipeline_name: str = ""
    alert_type: str = ""
    severity: str = "warning"
    message: str = ""
    status: str = "open"
    acknowledged_by: Optional[str] = None
    created_at: float = 0.0
    acknowledged_at: Optional[float] = None
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline Alert Store
# ---------------------------------------------------------------------------

class PipelineAlertStore:
    """Manages pipeline alerts with acknowledgment and history tracking."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._alerts: Dict[str, AlertEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_created": 0,
            "total_acknowledged": 0,
            "total_resolved": 0,
            "total_purged": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'pas-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pas-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._alerts) < self._max_entries:
            return
        sorted_alerts = sorted(
            self._alerts.values(), key=lambda a: a.created_at
        )
        remove_count = len(self._alerts) - self._max_entries + 1
        for entry in sorted_alerts[:remove_count]:
            del self._alerts[entry.alert_id]
            logger.debug("alert_pruned", alert_id=entry.alert_id)

    # ------------------------------------------------------------------
    # Alert creation
    # ------------------------------------------------------------------

    def create_alert(
        self,
        pipeline_name: str,
        alert_type: str,
        severity: str,
        message: str,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new alert. Returns the alert_id.

        The alert starts with status 'open'. Severity must be one of
        info, warning, error, critical (defaults to warning if invalid).
        """
        if not pipeline_name or not alert_type or not message:
            logger.warning(
                "create_alert_invalid_input",
                pipeline_name=pipeline_name,
                alert_type=alert_type,
            )
            return ""

        if severity not in VALID_SEVERITIES:
            severity = "warning"

        self._prune_if_needed()

        alert_id = self._next_id(f"{pipeline_name}:{alert_type}")
        now = time.time()

        entry = AlertEntry(
            alert_id=alert_id,
            pipeline_name=pipeline_name,
            alert_type=alert_type,
            severity=severity,
            message=message,
            status="open",
            acknowledged_by=None,
            created_at=now,
            acknowledged_at=None,
            tags=list(tags) if tags else [],
        )

        self._alerts[alert_id] = entry
        self._stats["total_created"] += 1

        logger.info(
            "alert_created",
            alert_id=alert_id,
            pipeline_name=pipeline_name,
            alert_type=alert_type,
            severity=severity,
        )
        self._fire("alert_created", self._entry_to_dict(entry))
        return alert_id

    # ------------------------------------------------------------------
    # Alert retrieval
    # ------------------------------------------------------------------

    def get_alert(self, alert_id: str) -> Optional[Dict]:
        """Get a single alert by ID. Returns None if not found."""
        self._stats["total_lookups"] += 1
        entry = self._alerts.get(alert_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # Alert lifecycle
    # ------------------------------------------------------------------

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an open alert. Returns True on success."""
        entry = self._alerts.get(alert_id)
        if not entry:
            logger.warning("acknowledge_alert_not_found", alert_id=alert_id)
            return False
        if entry.status != "open":
            logger.warning(
                "acknowledge_alert_invalid_status",
                alert_id=alert_id,
                status=entry.status,
            )
            return False
        if not acknowledged_by:
            return False

        entry.status = "acknowledged"
        entry.acknowledged_by = acknowledged_by
        entry.acknowledged_at = time.time()
        self._stats["total_acknowledged"] += 1

        logger.info(
            "alert_acknowledged",
            alert_id=alert_id,
            acknowledged_by=acknowledged_by,
        )
        self._fire("alert_acknowledged", self._entry_to_dict(entry))
        return True

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert (from open or acknowledged). Returns True on success."""
        entry = self._alerts.get(alert_id)
        if not entry:
            logger.warning("resolve_alert_not_found", alert_id=alert_id)
            return False
        if entry.status == "resolved":
            logger.warning("resolve_alert_already_resolved", alert_id=alert_id)
            return False

        entry.status = "resolved"
        self._stats["total_resolved"] += 1

        logger.info("alert_resolved", alert_id=alert_id)
        self._fire("alert_resolved", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_open_alerts(
        self,
        pipeline_name: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[Dict]:
        """Get all open alerts, optionally filtered by pipeline and severity."""
        self._stats["total_lookups"] += 1
        results = []
        for entry in self._alerts.values():
            if entry.status != "open":
                continue
            if pipeline_name and entry.pipeline_name != pipeline_name:
                continue
            if severity and entry.severity != severity:
                continue
            results.append(self._entry_to_dict(entry))
        results.sort(key=lambda x: -x["created_at"])
        return results

    def get_alert_history(
        self,
        pipeline_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get alert history (all statuses), most recent first.

        Optionally filtered by pipeline_name. Limited to *limit* entries.
        """
        self._stats["total_lookups"] += 1
        entries = list(self._alerts.values())
        if pipeline_name:
            entries = [e for e in entries if e.pipeline_name == pipeline_name]
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return [self._entry_to_dict(e) for e in entries[:limit]]

    def get_alert_summary(self) -> Dict:
        """Get a summary dict with counts by status and severity.

        Returns dict with keys: total, open, acknowledged, resolved,
        by_severity.
        """
        status_counts: Dict[str, int] = defaultdict(int)
        severity_counts: Dict[str, int] = defaultdict(int)

        for entry in self._alerts.values():
            status_counts[entry.status] += 1
            severity_counts[entry.severity] += 1

        return {
            "total": len(self._alerts),
            "open": status_counts.get("open", 0),
            "acknowledged": status_counts.get("acknowledged", 0),
            "resolved": status_counts.get("resolved", 0),
            "by_severity": dict(sorted(severity_counts.items())),
        }

    def list_pipelines_with_alerts(self) -> List[str]:
        """Return sorted list of unique pipeline names that have alerts."""
        pipelines: Set[str] = set()
        for entry in self._alerts.values():
            pipelines.add(entry.pipeline_name)
        return sorted(pipelines)

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Purge resolved alerts. If *before_timestamp* is given, only
        purge alerts created before that time. Returns count removed."""
        to_remove: List[str] = []
        for alert_id, entry in self._alerts.items():
            if entry.status != "resolved":
                continue
            if before_timestamp is not None and entry.created_at >= before_timestamp:
                continue
            to_remove.append(alert_id)

        for alert_id in to_remove:
            del self._alerts[alert_id]

        removed = len(to_remove)
        self._stats["total_purged"] += removed

        if removed:
            logger.info("alerts_purged", count=removed)
            self._fire("alerts_purged", {"count": removed})
        return removed

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

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: AlertEntry) -> Dict:
        """Convert an AlertEntry to a plain dict."""
        return {
            "alert_id": entry.alert_id,
            "pipeline_name": entry.pipeline_name,
            "alert_type": entry.alert_type,
            "severity": entry.severity,
            "message": entry.message,
            "status": entry.status,
            "acknowledged_by": entry.acknowledged_by,
            "created_at": entry.created_at,
            "acknowledged_at": entry.acknowledged_at,
            "tags": list(entry.tags),
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        status_counts: Dict[str, int] = defaultdict(int)
        for entry in self._alerts.values():
            status_counts[entry.status] += 1

        return {
            **self._stats,
            "current_alerts": len(self._alerts),
            "current_open": status_counts.get("open", 0),
            "current_acknowledged": status_counts.get("acknowledged", 0),
            "current_resolved": status_counts.get("resolved", 0),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._alerts.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("store_reset")
