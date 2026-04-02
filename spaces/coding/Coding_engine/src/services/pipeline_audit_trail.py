"""Pipeline audit trail.

Records an immutable audit trail of all significant actions and state
changes within the pipeline. Supports compliance, debugging, and
forensic analysis.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _AuditEntry:
    """A single audit trail entry."""
    entry_id: str = ""
    action: str = ""
    actor: str = ""
    target: str = ""
    target_type: str = ""  # component, agent, pipeline, config, data
    details: str = ""
    old_value: str = ""
    new_value: str = ""
    source: str = ""  # api, ui, system, agent
    severity: str = "info"  # debug, info, warning, error, critical
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class PipelineAuditTrail:
    """Immutable audit trail for pipeline operations."""

    SEVERITIES = ("debug", "info", "warning", "error", "critical")
    TARGET_TYPES = ("component", "agent", "pipeline", "config", "data")
    SOURCES = ("api", "ui", "system", "agent")

    def __init__(self, max_entries: int = 1000000):
        self._max_entries = max_entries
        self._entries: Dict[str, _AuditEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_entries_created": 0,
        }

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, action: str, actor: str = "",
               target: str = "", target_type: str = "",
               details: str = "", old_value: str = "",
               new_value: str = "", source: str = "",
               severity: str = "info",
               tags: Optional[List[str]] = None,
               metadata: Optional[Dict] = None) -> str:
        if not action or not action.strip():
            return ""
        if severity and severity not in self.SEVERITIES:
            return ""
        if target_type and target_type not in self.TARGET_TYPES:
            return ""
        if source and source not in self.SOURCES:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{action}-{actor}-{now}-{self._seq}-{len(self._entries)}"
        eid = "aud-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._entries[eid] = _AuditEntry(
            entry_id=eid,
            action=action,
            actor=actor,
            target=target,
            target_type=target_type,
            details=details,
            old_value=old_value,
            new_value=new_value,
            source=source or "",
            severity=severity or "info",
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            created_at=now,
            seq=self._seq,
        )
        self._stats["total_entries_created"] += 1
        self._fire("entry_recorded", {"entry_id": eid, "action": action})
        return eid

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        e = self._entries.get(entry_id)
        if not e:
            return None
        return {
            "entry_id": e.entry_id, "action": e.action,
            "actor": e.actor, "target": e.target,
            "target_type": e.target_type, "details": e.details,
            "old_value": e.old_value, "new_value": e.new_value,
            "source": e.source, "severity": e.severity,
            "tags": list(e.tags), "metadata": dict(e.metadata),
            "created_at": e.created_at,
        }

    def remove_entry(self, entry_id: str) -> bool:
        if entry_id not in self._entries:
            return False
        del self._entries[entry_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search(self, action: str = "", actor: str = "",
               target: str = "", target_type: str = "",
               source: str = "", severity: str = "",
               tag: str = "", limit: int = 100) -> List[Dict]:
        results = []
        for e in self._entries.values():
            if action and e.action != action:
                continue
            if actor and e.actor != actor:
                continue
            if target and e.target != target:
                continue
            if target_type and e.target_type != target_type:
                continue
            if source and e.source != source:
                continue
            if severity and e.severity != severity:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_entry(e.entry_id))
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    def get_actor_history(self, actor: str,
                          limit: int = 100) -> List[Dict]:
        """Get audit history for a specific actor."""
        return self.search(actor=actor, limit=limit)

    def get_target_history(self, target: str,
                            limit: int = 100) -> List[Dict]:
        """Get audit history for a specific target."""
        return self.search(target=target, limit=limit)

    def get_severity_counts(self) -> Dict[str, int]:
        counts = {s: 0 for s in self.SEVERITIES}
        for e in self._entries.values():
            if e.severity in counts:
                counts[e.severity] += 1
        return counts

    def get_action_counts(self, limit: int = 20) -> List[Dict]:
        """Get most frequent actions."""
        counts: Dict[str, int] = {}
        for e in self._entries.values():
            counts[e.action] = counts.get(e.action, 0) + 1
        results = [{"action": a, "count": c}
                    for a, c in counts.items()]
        results.sort(key=lambda x: x["count"], reverse=True)
        return results[:limit]

    def get_active_actors(self, limit: int = 20) -> List[Dict]:
        """Get most active actors."""
        counts: Dict[str, int] = {}
        for e in self._entries.values():
            if e.actor:
                counts[e.actor] = counts.get(e.actor, 0) + 1
        results = [{"actor": a, "entry_count": c}
                    for a, c in counts.items()]
        results.sort(key=lambda x: x["entry_count"], reverse=True)
        return results[:limit]

    def get_recent(self, limit: int = 50) -> List[Dict]:
        """Get most recent entries."""
        entries = list(self._entries.values())
        entries.sort(key=lambda x: x.seq, reverse=True)
        return [self.get_entry(e.entry_id) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_entries": len(self._entries),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
