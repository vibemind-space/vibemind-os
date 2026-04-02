"""Pipeline Audit Logger -- structured audit logging for pipeline operations.

Provides immutable audit entries with actor/resource tracking, severity levels,
querying by multiple dimensions, and summary analytics.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _AuditEntry:
    entry_id: str
    action: str
    actor: str
    resource: str
    details: Optional[Dict[str, Any]]
    severity: str
    tags: List[str]
    created_at: float


_SEVERITIES = {"debug", "info", "warning", "error", "critical"}


class PipelineAuditLogger:
    """Structured audit logger for pipeline operations."""

    def __init__(self, max_entries: int = 50000, max_history: int = 100000) -> None:
        self._entries: Dict[str, _AuditEntry] = {}
        self._order: List[str] = []  # insertion-ordered entry IDs
        self._callbacks: Dict[str, Callable] = {}
        self._history: List[Dict[str, Any]] = []
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0

        # indexes
        self._by_actor: Dict[str, List[str]] = {}
        self._by_resource: Dict[str, List[str]] = {}
        self._by_action: Dict[str, List[str]] = {}
        self._by_severity: Dict[str, List[str]] = {}

        # counters
        self._total_logged = 0
        self._total_purged = 0
        self._total_queries = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, action: str) -> str:
        self._seq += 1
        raw = f"{action}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pal-{digest}"

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        entry = {"action": action, "detail": detail, "ts": time.time()}
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self._history[-limit:])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, fn: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = fn
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        while len(self._order) > self._max_entries:
            oldest_id = self._order.pop(0)
            entry = self._entries.pop(oldest_id, None)
            if entry is None:
                continue
            self._remove_from_index(self._by_actor, entry.actor, oldest_id)
            self._remove_from_index(self._by_resource, entry.resource, oldest_id)
            self._remove_from_index(self._by_action, entry.action, oldest_id)
            self._remove_from_index(self._by_severity, entry.severity, oldest_id)

    @staticmethod
    def _remove_from_index(index: Dict[str, List[str]], key: str, eid: str) -> None:
        lst = index.get(key)
        if lst is not None:
            try:
                lst.remove(eid)
            except ValueError:
                pass
            if not lst:
                del index[key]

    # ------------------------------------------------------------------
    # Core: log
    # ------------------------------------------------------------------

    def log(
        self,
        action: str,
        actor: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Log an audit entry. Returns entry ID (pal-...)."""
        if severity not in _SEVERITIES:
            severity = "info"

        eid = self._generate_id(action)
        now = time.time()

        entry = _AuditEntry(
            entry_id=eid,
            action=action,
            actor=actor,
            resource=resource,
            details=details,
            severity=severity,
            tags=list(tags) if tags else [],
            created_at=now,
        )

        self._entries[eid] = entry
        self._order.append(eid)

        # update indexes
        self._by_actor.setdefault(actor, []).append(eid)
        self._by_resource.setdefault(resource, []).append(eid)
        self._by_action.setdefault(action, []).append(eid)
        self._by_severity.setdefault(severity, []).append(eid)

        self._total_logged += 1
        self._prune()

        self._record_history("log", {"entry_id": eid, "action": action, "actor": actor})
        self._fire("log", {"entry_id": eid, "action": action, "severity": severity})

        return eid

    # ------------------------------------------------------------------
    # get_entry
    # ------------------------------------------------------------------

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific audit entry by ID."""
        entry = self._entries.get(entry_id)
        if entry is None:
            return None
        return self._to_dict(entry)

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------

    def query(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit log with optional filters."""
        self._total_queries += 1

        # pick the smallest candidate set via indexes
        candidate_ids: Optional[List[str]] = None

        if actor is not None and actor in self._by_actor:
            candidate_ids = self._by_actor[actor]
        if action is not None and action in self._by_action:
            ids = self._by_action[action]
            if candidate_ids is None or len(ids) < len(candidate_ids):
                candidate_ids = ids
        if resource is not None and resource in self._by_resource:
            ids = self._by_resource[resource]
            if candidate_ids is None or len(ids) < len(candidate_ids):
                candidate_ids = ids
        if severity is not None and severity in self._by_severity:
            ids = self._by_severity[severity]
            if candidate_ids is None or len(ids) < len(candidate_ids):
                candidate_ids = ids

        if candidate_ids is None:
            candidate_ids = self._order

        results: List[Dict[str, Any]] = []
        for eid in reversed(candidate_ids):
            entry = self._entries.get(eid)
            if entry is None:
                continue
            if actor is not None and entry.actor != actor:
                continue
            if action is not None and entry.action != action:
                continue
            if resource is not None and entry.resource != resource:
                continue
            if severity is not None and entry.severity != severity:
                continue
            if since is not None and entry.created_at < since:
                continue
            if until is not None and entry.created_at > until:
                continue
            results.append(self._to_dict(entry))
            if len(results) >= limit:
                break

        return results

    # ------------------------------------------------------------------
    # get_actor_history
    # ------------------------------------------------------------------

    def get_actor_history(self, actor: str, limit: int = 50) -> List[Dict[str, Any]]:
        """All actions by a specific actor."""
        ids = self._by_actor.get(actor, [])
        results: List[Dict[str, Any]] = []
        for eid in reversed(ids):
            entry = self._entries.get(eid)
            if entry is not None:
                results.append(self._to_dict(entry))
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # get_resource_history
    # ------------------------------------------------------------------

    def get_resource_history(self, resource: str, limit: int = 50) -> List[Dict[str, Any]]:
        """All actions on a specific resource."""
        ids = self._by_resource.get(resource, [])
        results: List[Dict[str, Any]] = []
        for eid in reversed(ids):
            entry = self._entries.get(eid)
            if entry is not None:
                results.append(self._to_dict(entry))
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # get_summary
    # ------------------------------------------------------------------

    def get_summary(self, since: Optional[float] = None) -> Dict[str, Any]:
        """Summary stats: total_entries, by_severity, by_action, top_actors."""
        by_severity: Dict[str, int] = {}
        by_action: Dict[str, int] = {}
        actor_counts: Dict[str, int] = {}
        total = 0

        for eid in self._order:
            entry = self._entries.get(eid)
            if entry is None:
                continue
            if since is not None and entry.created_at < since:
                continue
            total += 1
            by_severity[entry.severity] = by_severity.get(entry.severity, 0) + 1
            by_action[entry.action] = by_action.get(entry.action, 0) + 1
            actor_counts[entry.actor] = actor_counts.get(entry.actor, 0) + 1

        top_actors = sorted(actor_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_entries": total,
            "by_severity": by_severity,
            "by_action": by_action,
            "top_actors": [{"actor": a, "count": c} for a, c in top_actors],
        }

    # ------------------------------------------------------------------
    # list_actors / list_actions
    # ------------------------------------------------------------------

    def list_actors(self) -> List[str]:
        """All known actors."""
        return list(self._by_actor.keys())

    def list_actions(self) -> List[str]:
        """All known action types."""
        return list(self._by_action.keys())

    # ------------------------------------------------------------------
    # purge_before
    # ------------------------------------------------------------------

    def purge_before(self, timestamp: float) -> int:
        """Remove entries before timestamp. Returns count of removed entries."""
        to_remove: List[str] = []
        for eid in self._order:
            entry = self._entries.get(eid)
            if entry is not None and entry.created_at < timestamp:
                to_remove.append(eid)

        for eid in to_remove:
            entry = self._entries.pop(eid, None)
            if entry is None:
                continue
            self._order.remove(eid)
            self._remove_from_index(self._by_actor, entry.actor, eid)
            self._remove_from_index(self._by_resource, entry.resource, eid)
            self._remove_from_index(self._by_action, entry.action, eid)
            self._remove_from_index(self._by_severity, entry.severity, eid)

        count = len(to_remove)
        if count > 0:
            self._total_purged += count
            self._record_history("purge_before", {"timestamp": timestamp, "removed": count})
            self._fire("purge", {"timestamp": timestamp, "removed": count})

        return count

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_logged": self._total_logged,
            "total_purged": self._total_purged,
            "total_queries": self._total_queries,
            "current_entries": len(self._entries),
            "unique_actors": len(self._by_actor),
            "unique_actions": len(self._by_action),
            "unique_resources": len(self._by_resource),
            "callbacks": len(self._callbacks),
            "history_size": len(self._history),
            "max_entries": self._max_entries,
            "max_history": self._max_history,
        }

    def reset(self) -> None:
        self._entries.clear()
        self._order.clear()
        self._by_actor.clear()
        self._by_resource.clear()
        self._by_action.clear()
        self._by_severity.clear()
        self._callbacks.clear()
        self._history.clear()
        self._seq = 0
        self._total_logged = 0
        self._total_purged = 0
        self._total_queries = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(entry: _AuditEntry) -> Dict[str, Any]:
        return {
            "entry_id": entry.entry_id,
            "action": entry.action,
            "actor": entry.actor,
            "resource": entry.resource,
            "details": entry.details,
            "severity": entry.severity,
            "tags": list(entry.tags),
            "created_at": entry.created_at,
        }
