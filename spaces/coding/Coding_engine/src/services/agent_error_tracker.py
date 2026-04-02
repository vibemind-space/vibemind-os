"""Agent error tracker.

Tracks errors raised by agents across the pipeline, categorizes them,
manages error patterns, and provides analytics for debugging and
reliability improvement.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ErrorEntry:
    """An error entry."""
    error_id: str = ""
    agent: str = ""
    error_type: str = ""
    message: str = ""
    severity: str = "error"
    source: str = ""
    stack_trace: str = ""
    context: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    status: str = "open"  # open, acknowledged, resolved, ignored
    resolution: str = ""
    timestamp: float = 0.0
    resolved_at: float = 0.0
    seq: int = 0


@dataclass
class _ErrorPattern:
    """A recurring error pattern."""
    pattern_id: str = ""
    name: str = ""
    error_type: str = ""
    message_pattern: str = ""
    severity: str = "error"
    tags: List[str] = field(default_factory=list)
    occurrence_count: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    status: str = "active"  # active, suppressed
    created_at: float = 0.0


class AgentErrorTracker:
    """Tracks and manages agent errors."""

    SEVERITIES = ("debug", "info", "warning", "error", "critical")
    ERROR_STATUSES = ("open", "acknowledged", "resolved", "ignored")
    PATTERN_STATUSES = ("active", "suppressed")

    def __init__(self, max_errors: int = 200000,
                 max_patterns: int = 5000):
        self._max_errors = max_errors
        self._max_patterns = max_patterns
        self._errors: Dict[str, _ErrorEntry] = {}
        self._patterns: Dict[str, _ErrorPattern] = {}
        self._error_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_errors_logged": 0,
            "total_acknowledged": 0,
            "total_resolved": 0,
            "total_ignored": 0,
            "total_patterns_created": 0,
        }

    # ------------------------------------------------------------------
    # Error Logging
    # ------------------------------------------------------------------

    def log_error(self, agent: str, error_type: str, message: str,
                  severity: str = "error", source: str = "",
                  stack_trace: str = "", context: Optional[Dict] = None,
                  tags: Optional[List[str]] = None) -> str:
        """Log an error."""
        if not agent or not error_type or not message:
            return ""
        if severity not in self.SEVERITIES:
            return ""
        if len(self._errors) >= self._max_errors:
            self._prune_errors()

        self._error_seq += 1
        eid = "err-" + hashlib.md5(
            f"{agent}{error_type}{time.time()}{self._error_seq}".encode()
        ).hexdigest()[:12]

        self._errors[eid] = _ErrorEntry(
            error_id=eid,
            agent=agent,
            error_type=error_type,
            message=message,
            severity=severity,
            source=source,
            stack_trace=stack_trace,
            context=context or {},
            tags=tags or [],
            timestamp=time.time(),
            seq=self._error_seq,
        )
        self._stats["total_errors_logged"] += 1

        # Auto-match patterns
        for p in self._patterns.values():
            if p.status != "active":
                continue
            if p.error_type and p.error_type != error_type:
                continue
            if p.message_pattern and p.message_pattern not in message:
                continue
            p.occurrence_count += 1
            p.last_seen = time.time()

        self._fire("error_logged", {
            "error_id": eid, "agent": agent,
            "error_type": error_type, "severity": severity,
        })
        return eid

    def get_error(self, error_id: str) -> Optional[Dict]:
        """Get error info."""
        e = self._errors.get(error_id)
        if not e:
            return None
        return {
            "error_id": e.error_id,
            "agent": e.agent,
            "error_type": e.error_type,
            "message": e.message,
            "severity": e.severity,
            "source": e.source,
            "stack_trace": e.stack_trace,
            "status": e.status,
            "resolution": e.resolution,
            "tags": list(e.tags),
            "timestamp": e.timestamp,
            "seq": e.seq,
        }

    def acknowledge_error(self, error_id: str) -> bool:
        """Acknowledge an error."""
        e = self._errors.get(error_id)
        if not e or e.status != "open":
            return False
        e.status = "acknowledged"
        self._stats["total_acknowledged"] += 1
        return True

    def resolve_error(self, error_id: str, resolution: str = "") -> bool:
        """Resolve an error."""
        e = self._errors.get(error_id)
        if not e or e.status in ("resolved", "ignored"):
            return False
        e.status = "resolved"
        e.resolution = resolution
        e.resolved_at = time.time()
        self._stats["total_resolved"] += 1
        return True

    def ignore_error(self, error_id: str) -> bool:
        """Ignore an error."""
        e = self._errors.get(error_id)
        if not e or e.status in ("resolved", "ignored"):
            return False
        e.status = "ignored"
        self._stats["total_ignored"] += 1
        return True

    def remove_error(self, error_id: str) -> bool:
        """Remove an error."""
        if error_id not in self._errors:
            return False
        del self._errors[error_id]
        return True

    # ------------------------------------------------------------------
    # Error Patterns
    # ------------------------------------------------------------------

    def create_pattern(self, name: str, error_type: str = "",
                       message_pattern: str = "",
                       severity: str = "error",
                       tags: Optional[List[str]] = None) -> str:
        """Create an error pattern for tracking recurring errors."""
        if not name:
            return ""
        if severity not in self.SEVERITIES:
            return ""
        if len(self._patterns) >= self._max_patterns:
            return ""

        pid = "epat-" + hashlib.md5(
            f"{name}{time.time()}{len(self._patterns)}".encode()
        ).hexdigest()[:12]

        self._patterns[pid] = _ErrorPattern(
            pattern_id=pid,
            name=name,
            error_type=error_type,
            message_pattern=message_pattern,
            severity=severity,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_patterns_created"] += 1
        return pid

    def get_pattern(self, pattern_id: str) -> Optional[Dict]:
        """Get pattern info."""
        p = self._patterns.get(pattern_id)
        if not p:
            return None
        return {
            "pattern_id": p.pattern_id,
            "name": p.name,
            "error_type": p.error_type,
            "message_pattern": p.message_pattern,
            "severity": p.severity,
            "occurrence_count": p.occurrence_count,
            "status": p.status,
            "tags": list(p.tags),
        }

    def suppress_pattern(self, pattern_id: str) -> bool:
        """Suppress pattern."""
        p = self._patterns.get(pattern_id)
        if not p or p.status == "suppressed":
            return False
        p.status = "suppressed"
        return True

    def activate_pattern(self, pattern_id: str) -> bool:
        """Activate pattern."""
        p = self._patterns.get(pattern_id)
        if not p or p.status == "active":
            return False
        p.status = "active"
        return True

    def remove_pattern(self, pattern_id: str) -> bool:
        """Remove pattern."""
        if pattern_id not in self._patterns:
            return False
        del self._patterns[pattern_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_errors(self, agent: Optional[str] = None,
                      error_type: Optional[str] = None,
                      severity: Optional[str] = None,
                      status: Optional[str] = None,
                      source: Optional[str] = None,
                      tag: Optional[str] = None,
                      limit: int = 100) -> List[Dict]:
        """Search errors."""
        result = []
        for e in self._errors.values():
            if agent and e.agent != agent:
                continue
            if error_type and e.error_type != error_type:
                continue
            if severity and e.severity != severity:
                continue
            if status and e.status != status:
                continue
            if source and e.source != source:
                continue
            if tag and tag not in e.tags:
                continue
            result.append({
                "error_id": e.error_id,
                "agent": e.agent,
                "error_type": e.error_type,
                "severity": e.severity,
                "status": e.status,
                "message": e.message,
                "seq": e.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_agent_error_summary(self, agent: str) -> Dict:
        """Get error summary for an agent."""
        total = 0
        by_severity = {s: 0 for s in self.SEVERITIES}
        by_status = {s: 0 for s in self.ERROR_STATUSES}
        by_type: Dict[str, int] = {}

        for e in self._errors.values():
            if e.agent != agent:
                continue
            total += 1
            by_severity[e.severity] += 1
            by_status[e.status] += 1
            by_type[e.error_type] = by_type.get(e.error_type, 0) + 1

        return {
            "agent": agent,
            "total_errors": total,
            "by_severity": by_severity,
            "by_status": by_status,
            "by_type": by_type,
        }

    def get_error_rate(self, agent: Optional[str] = None) -> Dict:
        """Get error rate stats."""
        total = 0
        resolved = 0
        open_count = 0
        for e in self._errors.values():
            if agent and e.agent != agent:
                continue
            total += 1
            if e.status == "resolved":
                resolved += 1
            elif e.status == "open":
                open_count += 1

        return {
            "total": total,
            "open": open_count,
            "resolved": resolved,
            "resolution_rate": round(
                (resolved / total * 100) if total > 0 else 0.0, 1
            ),
        }

    def get_severity_counts(self) -> Dict[str, int]:
        """Get error counts by severity."""
        counts = {s: 0 for s in self.SEVERITIES}
        for e in self._errors.values():
            counts[e.severity] += 1
        return counts

    def get_top_error_types(self, limit: int = 10) -> List[Dict]:
        """Get most frequent error types."""
        type_counts: Dict[str, int] = {}
        for e in self._errors.values():
            type_counts[e.error_type] = type_counts.get(e.error_type, 0) + 1

        result = [
            {"error_type": t, "count": c}
            for t, c in type_counts.items()
        ]
        result.sort(key=lambda x: -x["count"])
        return result[:limit]

    def get_error_prone_agents(self, limit: int = 10) -> List[Dict]:
        """Get agents with most errors."""
        agent_counts: Dict[str, int] = {}
        for e in self._errors.values():
            agent_counts[e.agent] = agent_counts.get(e.agent, 0) + 1

        result = [
            {"agent": a, "error_count": c}
            for a, c in agent_counts.items()
        ]
        result.sort(key=lambda x: -x["error_count"])
        return result[:limit]

    def list_patterns(self, status: Optional[str] = None,
                      tag: Optional[str] = None) -> List[Dict]:
        """List error patterns."""
        result = []
        for p in self._patterns.values():
            if status and p.status != status:
                continue
            if tag and tag not in p.tags:
                continue
            result.append({
                "pattern_id": p.pattern_id,
                "name": p.name,
                "error_type": p.error_type,
                "occurrence_count": p.occurrence_count,
                "status": p.status,
            })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_errors(self) -> None:
        """Remove oldest resolved/ignored errors."""
        prunable = [(k, v) for k, v in self._errors.items()
                    if v.status in ("resolved", "ignored")]
        prunable.sort(key=lambda x: x[1].seq)
        to_remove = max(len(prunable) // 2, len(self._errors) // 4)
        for k, _ in prunable[:to_remove]:
            del self._errors[k]

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
            "current_errors": len(self._errors),
            "open_errors": sum(
                1 for e in self._errors.values() if e.status == "open"
            ),
            "current_patterns": len(self._patterns),
            "active_patterns": sum(
                1 for p in self._patterns.values() if p.status == "active"
            ),
        }

    def reset(self) -> None:
        self._errors.clear()
        self._patterns.clear()
        self._error_seq = 0
        self._stats = {k: 0 for k in self._stats}
