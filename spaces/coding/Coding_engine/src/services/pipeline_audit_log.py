"""
Pipeline Audit Log — immutable audit trail for all pipeline operations.

Features:
- Append-only event log with timestamps
- Categorized entries (action, security, config, error, access)
- Actor tracking (who did what)
- Resource tracking (what was affected)
- Searchable by time range, actor, category, resource
- Log retention and pruning
- Export for compliance reporting
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

CATEGORIES = {"action", "security", "config", "error", "access", "system"}


@dataclass
class AuditEntry:
    """A single audit log entry."""
    entry_id: str
    timestamp: float
    category: str
    action: str
    actor: str
    resource: str
    details: Dict[str, Any]
    outcome: str  # "success", "failure", "denied"
    severity: str  # "info", "warning", "critical"
    tags: Set[str]


# ---------------------------------------------------------------------------
# Pipeline Audit Log
# ---------------------------------------------------------------------------

class PipelineAuditLog:
    """Immutable audit trail for pipeline operations."""

    def __init__(
        self,
        max_entries: int = 50000,
        retention_seconds: float = 0.0,  # 0 = keep forever
    ):
        self._max_entries = max_entries
        self._retention_seconds = retention_seconds
        self._entries: List[AuditEntry] = []

        self._stats = {
            "total_logged": 0,
            "total_actions": 0,
            "total_security": 0,
            "total_errors": 0,
            "total_denied": 0,
        }

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(
        self,
        action: str,
        actor: str = "system",
        resource: str = "",
        category: str = "action",
        details: Optional[Dict] = None,
        outcome: str = "success",
        severity: str = "info",
        tags: Optional[Set[str]] = None,
        timestamp: float = 0.0,
    ) -> str:
        """Append an audit entry. Returns entry_id."""
        eid = f"audit-{uuid.uuid4().hex[:8]}"
        ts = timestamp if timestamp > 0 else time.time()

        if category not in CATEGORIES:
            category = "action"

        entry = AuditEntry(
            entry_id=eid,
            timestamp=ts,
            category=category,
            action=action,
            actor=actor,
            resource=resource,
            details=details or {},
            outcome=outcome,
            severity=severity,
            tags=tags or set(),
        )

        self._entries.append(entry)
        self._stats["total_logged"] += 1

        if category == "action":
            self._stats["total_actions"] += 1
        elif category == "security":
            self._stats["total_security"] += 1
        elif category == "error":
            self._stats["total_errors"] += 1
        if outcome == "denied":
            self._stats["total_denied"] += 1

        self._prune()
        return eid

    def log_action(
        self, action: str, actor: str, resource: str = "",
        details: Optional[Dict] = None, outcome: str = "success",
    ) -> str:
        """Convenience: log an action event."""
        return self.log(action=action, actor=actor, resource=resource,
                        category="action", details=details, outcome=outcome)

    def log_security(
        self, action: str, actor: str, resource: str = "",
        details: Optional[Dict] = None, outcome: str = "success",
        severity: str = "warning",
    ) -> str:
        """Convenience: log a security event."""
        return self.log(action=action, actor=actor, resource=resource,
                        category="security", details=details, outcome=outcome,
                        severity=severity)

    def log_error(
        self, action: str, actor: str = "system", resource: str = "",
        details: Optional[Dict] = None, severity: str = "warning",
    ) -> str:
        """Convenience: log an error event."""
        return self.log(action=action, actor=actor, resource=resource,
                        category="error", details=details, outcome="failure",
                        severity=severity)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Get a specific entry by ID."""
        for e in self._entries:
            if e.entry_id == entry_id:
                return self._entry_to_dict(e)
        return None

    def search(
        self,
        category: Optional[str] = None,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        outcome: Optional[str] = None,
        severity: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        since: float = 0.0,
        until: float = 0.0,
        limit: int = 100,
    ) -> List[Dict]:
        """Search audit entries with filters."""
        results = []
        for e in reversed(self._entries):  # Most recent first
            if category and e.category != category:
                continue
            if actor and e.actor != actor:
                continue
            if resource and e.resource != resource:
                continue
            if action and action.lower() not in e.action.lower():
                continue
            if outcome and e.outcome != outcome:
                continue
            if severity and e.severity != severity:
                continue
            if tags and not tags.issubset(e.tags):
                continue
            if since > 0 and e.timestamp < since:
                continue
            if until > 0 and e.timestamp > until:
                continue
            results.append(self._entry_to_dict(e))
            if len(results) >= limit:
                break
        return results

    def get_actor_activity(self, actor: str, limit: int = 50) -> List[Dict]:
        """Get all activity for a specific actor."""
        return self.search(actor=actor, limit=limit)

    def get_resource_history(self, resource: str, limit: int = 50) -> List[Dict]:
        """Get all activity on a specific resource."""
        return self.search(resource=resource, limit=limit)

    def get_recent(self, limit: int = 20) -> List[Dict]:
        """Get most recent entries."""
        return [
            self._entry_to_dict(e)
            for e in reversed(self._entries[-limit:])
        ]

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def get_actor_summary(self, limit: int = 20) -> List[Dict]:
        """Summary of activity per actor."""
        actor_data: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"actions": 0, "successes": 0, "failures": 0, "denied": 0}
        )
        for e in self._entries:
            d = actor_data[e.actor]
            d["actions"] += 1
            if e.outcome == "success":
                d["successes"] += 1
            elif e.outcome == "failure":
                d["failures"] += 1
            elif e.outcome == "denied":
                d["denied"] += 1

        result = []
        for actor, data in sorted(actor_data.items(),
                                    key=lambda x: x[1]["actions"], reverse=True):
            result.append({
                "actor": actor,
                **data,
            })
        return result[:limit]

    def get_category_counts(self) -> Dict[str, int]:
        """Count entries per category."""
        counts: Dict[str, int] = defaultdict(int)
        for e in self._entries:
            counts[e.category] += 1
        return dict(sorted(counts.items()))

    def get_timeline(
        self,
        bucket_seconds: float = 3600.0,
        num_buckets: int = 24,
    ) -> List[Dict]:
        """Get entry counts over time buckets."""
        now = time.time()
        buckets = []
        for i in range(num_buckets):
            start = now - (num_buckets - i) * bucket_seconds
            end = start + bucket_seconds
            count = sum(1 for e in self._entries if start <= e.timestamp < end)
            buckets.append({
                "bucket_start": round(start, 2),
                "bucket_end": round(end, 2),
                "count": count,
            })
        return buckets

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(
        self,
        since: float = 0.0,
        until: float = 0.0,
        category: Optional[str] = None,
    ) -> List[Dict]:
        """Export entries for compliance. Returns all matching entries."""
        results = []
        for e in self._entries:
            if category and e.category != category:
                continue
            if since > 0 and e.timestamp < since:
                continue
            if until > 0 and e.timestamp > until:
                continue
            results.append(self._entry_to_dict(e))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, e: AuditEntry) -> Dict:
        return {
            "entry_id": e.entry_id,
            "timestamp": e.timestamp,
            "category": e.category,
            "action": e.action,
            "actor": e.actor,
            "resource": e.resource,
            "details": e.details,
            "outcome": e.outcome,
            "severity": e.severity,
            "tags": sorted(e.tags),
        }

    def _prune(self) -> None:
        # Prune by count
        if len(self._entries) > self._max_entries:
            excess = len(self._entries) - self._max_entries
            self._entries = self._entries[excess:]

        # Prune by retention
        if self._retention_seconds > 0:
            cutoff = time.time() - self._retention_seconds
            self._entries = [e for e in self._entries if e.timestamp >= cutoff]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_entries": len(self._entries),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._stats = {k: 0 for k in self._stats}
