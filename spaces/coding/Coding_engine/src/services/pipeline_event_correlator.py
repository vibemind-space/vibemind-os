"""Pipeline event correlator.

Correlates related events across the pipeline to identify patterns,
causation chains, and aggregate related occurrences into incidents.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Event:
    """Internal event record."""
    event_id: str = ""
    source: str = ""
    event_type: str = ""
    severity: str = "info"
    message: str = ""
    data: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    correlation_id: str = ""


@dataclass
class _Correlation:
    """Internal correlation group."""
    correlation_id: str = ""
    name: str = ""
    pattern: str = ""
    events: List[str] = field(default_factory=list)
    status: str = "open"  # open, closed, expired
    created_at: float = 0.0
    closed_at: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class _Rule:
    """Correlation rule."""
    rule_id: str = ""
    name: str = ""
    match_field: str = ""  # source, event_type, severity, tag
    match_value: str = ""
    window_seconds: float = 60.0
    min_events: int = 2
    enabled: bool = True
    times_triggered: int = 0
    created_at: float = 0.0


class PipelineEventCorrelator:
    """Correlates related pipeline events into groups."""

    SEVERITIES = ("debug", "info", "warning", "error", "critical")
    MATCH_FIELDS = ("source", "event_type", "severity", "tag")

    def __init__(self, max_events: int = 100000, max_correlations: int = 10000,
                 max_rules: int = 1000):
        self._max_events = max_events
        self._max_correlations = max_correlations
        self._max_rules = max_rules
        self._events: Dict[str, _Event] = {}
        self._correlations: Dict[str, _Correlation] = {}
        self._rules: Dict[str, _Rule] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_events_ingested": 0,
            "total_correlations_created": 0,
            "total_correlations_closed": 0,
            "total_rules_triggered": 0,
        }

    # ------------------------------------------------------------------
    # Event ingestion
    # ------------------------------------------------------------------

    def ingest_event(self, source: str, event_type: str,
                     severity: str = "info", message: str = "",
                     data: Optional[Dict] = None,
                     tags: Optional[List[str]] = None) -> str:
        """Ingest a new event and check correlation rules."""
        if not source or not event_type:
            return ""
        if severity not in self.SEVERITIES:
            return ""

        if len(self._events) >= self._max_events:
            self._prune_events()

        eid = "evt-" + hashlib.md5(
            f"{source}{event_type}{time.time()}".encode()
        ).hexdigest()[:12]

        evt = _Event(
            event_id=eid,
            source=source,
            event_type=event_type,
            severity=severity,
            message=message,
            data=data or {},
            tags=tags or [],
            timestamp=time.time(),
        )
        self._events[eid] = evt
        self._stats["total_events_ingested"] += 1

        self._check_rules(evt)
        self._fire("event_ingested", {"event_id": eid, "source": source,
                                       "event_type": event_type})
        return eid

    def get_event(self, event_id: str) -> Optional[Dict]:
        """Get event info."""
        e = self._events.get(event_id)
        if not e:
            return None
        return {
            "event_id": e.event_id,
            "source": e.source,
            "event_type": e.event_type,
            "severity": e.severity,
            "message": e.message,
            "data": dict(e.data),
            "tags": list(e.tags),
            "timestamp": e.timestamp,
            "correlation_id": e.correlation_id,
        }

    # ------------------------------------------------------------------
    # Correlation rules
    # ------------------------------------------------------------------

    def add_rule(self, name: str, match_field: str, match_value: str,
                 window_seconds: float = 60.0, min_events: int = 2) -> str:
        """Add a correlation rule."""
        if not name or not match_value:
            return ""
        if match_field not in self.MATCH_FIELDS:
            return ""
        if window_seconds <= 0 or min_events < 1:
            return ""
        if len(self._rules) >= self._max_rules:
            return ""

        rid = "rule-" + hashlib.md5(
            f"{name}{time.time()}".encode()
        ).hexdigest()[:12]

        self._rules[rid] = _Rule(
            rule_id=rid,
            name=name,
            match_field=match_field,
            match_value=match_value,
            window_seconds=window_seconds,
            min_events=min_events,
            created_at=time.time(),
        )
        return rid

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a correlation rule."""
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        return True

    def get_rule(self, rule_id: str) -> Optional[Dict]:
        """Get rule info."""
        r = self._rules.get(rule_id)
        if not r:
            return None
        return {
            "rule_id": r.rule_id,
            "name": r.name,
            "match_field": r.match_field,
            "match_value": r.match_value,
            "window_seconds": r.window_seconds,
            "min_events": r.min_events,
            "enabled": r.enabled,
            "times_triggered": r.times_triggered,
        }

    def enable_rule(self, rule_id: str) -> bool:
        """Enable a rule."""
        r = self._rules.get(rule_id)
        if not r or r.enabled:
            return False
        r.enabled = True
        return True

    def disable_rule(self, rule_id: str) -> bool:
        """Disable a rule."""
        r = self._rules.get(rule_id)
        if not r or not r.enabled:
            return False
        r.enabled = False
        return True

    def list_rules(self, enabled_only: bool = False) -> List[Dict]:
        """List all rules."""
        result = []
        for r in self._rules.values():
            if enabled_only and not r.enabled:
                continue
            result.append({
                "rule_id": r.rule_id,
                "name": r.name,
                "match_field": r.match_field,
                "match_value": r.match_value,
                "enabled": r.enabled,
                "times_triggered": r.times_triggered,
            })
        return result

    # ------------------------------------------------------------------
    # Manual correlation
    # ------------------------------------------------------------------

    def create_correlation(self, name: str, event_ids: Optional[List[str]] = None,
                           tags: Optional[List[str]] = None) -> str:
        """Manually create a correlation group."""
        if not name:
            return ""
        if len(self._correlations) >= self._max_correlations:
            return ""

        cid = "corr-" + hashlib.md5(
            f"{name}{time.time()}".encode()
        ).hexdigest()[:12]

        valid_events = []
        for eid in (event_ids or []):
            if eid in self._events:
                valid_events.append(eid)
                self._events[eid].correlation_id = cid

        self._correlations[cid] = _Correlation(
            correlation_id=cid,
            name=name,
            pattern="manual",
            events=valid_events,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_correlations_created"] += 1
        self._fire("correlation_created", {"correlation_id": cid, "name": name})
        return cid

    def add_event_to_correlation(self, correlation_id: str,
                                  event_id: str) -> bool:
        """Add an event to an existing correlation."""
        c = self._correlations.get(correlation_id)
        if not c or c.status != "open":
            return False
        if event_id not in self._events:
            return False
        if event_id in c.events:
            return False

        c.events.append(event_id)
        self._events[event_id].correlation_id = correlation_id
        return True

    def close_correlation(self, correlation_id: str) -> bool:
        """Close a correlation group."""
        c = self._correlations.get(correlation_id)
        if not c or c.status != "open":
            return False
        c.status = "closed"
        c.closed_at = time.time()
        self._stats["total_correlations_closed"] += 1
        return True

    def get_correlation(self, correlation_id: str) -> Optional[Dict]:
        """Get correlation info."""
        c = self._correlations.get(correlation_id)
        if not c:
            return None
        return {
            "correlation_id": c.correlation_id,
            "name": c.name,
            "pattern": c.pattern,
            "event_count": len(c.events),
            "events": list(c.events),
            "status": c.status,
            "tags": list(c.tags),
            "created_at": c.created_at,
            "closed_at": c.closed_at,
        }

    def get_correlation_events(self, correlation_id: str) -> List[Dict]:
        """Get all events in a correlation."""
        c = self._correlations.get(correlation_id)
        if not c:
            return []
        result = []
        for eid in c.events:
            e = self._events.get(eid)
            if e:
                result.append({
                    "event_id": e.event_id,
                    "source": e.source,
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "message": e.message,
                    "timestamp": e.timestamp,
                })
        result.sort(key=lambda x: x["timestamp"])
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_events(self, source: Optional[str] = None,
                      event_type: Optional[str] = None,
                      severity: Optional[str] = None,
                      tag: Optional[str] = None,
                      limit: int = 100) -> List[Dict]:
        """Search events with filters."""
        result = []
        for e in self._events.values():
            if source and e.source != source:
                continue
            if event_type and e.event_type != event_type:
                continue
            if severity and e.severity != severity:
                continue
            if tag and tag not in e.tags:
                continue
            result.append({
                "event_id": e.event_id,
                "source": e.source,
                "event_type": e.event_type,
                "severity": e.severity,
                "message": e.message,
                "timestamp": e.timestamp,
                "correlation_id": e.correlation_id,
            })
        result.sort(key=lambda x: -x["timestamp"])
        return result[:limit]

    def get_event_sources(self) -> Dict[str, int]:
        """Get event counts by source."""
        counts: Dict[str, int] = {}
        for e in self._events.values():
            counts[e.source] = counts.get(e.source, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def get_severity_counts(self) -> Dict[str, int]:
        """Get event counts by severity."""
        counts = {s: 0 for s in self.SEVERITIES}
        for e in self._events.values():
            counts[e.severity] += 1
        return counts

    def list_correlations(self, status: Optional[str] = None,
                          tag: Optional[str] = None) -> List[Dict]:
        """List correlations with filters."""
        result = []
        for c in self._correlations.values():
            if status and c.status != status:
                continue
            if tag and tag not in c.tags:
                continue
            result.append({
                "correlation_id": c.correlation_id,
                "name": c.name,
                "pattern": c.pattern,
                "event_count": len(c.events),
                "status": c.status,
            })
        return result

    def get_recent_correlations(self, limit: int = 10) -> List[Dict]:
        """Get most recent correlations."""
        items = sorted(self._correlations.values(),
                       key=lambda c: -c.created_at)
        return [
            {
                "correlation_id": c.correlation_id,
                "name": c.name,
                "event_count": len(c.events),
                "status": c.status,
                "created_at": c.created_at,
            }
            for c in items[:limit]
        ]

    # ------------------------------------------------------------------
    # Rule matching
    # ------------------------------------------------------------------

    def _check_rules(self, evt: _Event) -> None:
        """Check event against active rules."""
        now = time.time()
        for rule in self._rules.values():
            if not rule.enabled:
                continue

            if not self._event_matches_rule(evt, rule):
                continue

            # Count matching events in the window
            window_start = now - rule.window_seconds
            matching = []
            for e in self._events.values():
                if e.timestamp < window_start:
                    continue
                if e.correlation_id:
                    continue
                if self._event_matches_rule(e, rule):
                    matching.append(e)

            if len(matching) >= rule.min_events:
                self._create_rule_correlation(rule, matching)

    def _event_matches_rule(self, evt: _Event, rule: _Rule) -> bool:
        """Check if event matches a rule."""
        if rule.match_field == "source":
            return evt.source == rule.match_value
        elif rule.match_field == "event_type":
            return evt.event_type == rule.match_value
        elif rule.match_field == "severity":
            return evt.severity == rule.match_value
        elif rule.match_field == "tag":
            return rule.match_value in evt.tags
        return False

    def _create_rule_correlation(self, rule: _Rule,
                                  events: List[_Event]) -> None:
        """Create a correlation from matched events."""
        if len(self._correlations) >= self._max_correlations:
            return

        cid = "corr-" + hashlib.md5(
            f"{rule.name}{time.time()}".encode()
        ).hexdigest()[:12]

        event_ids = []
        for e in events:
            if not e.correlation_id:
                e.correlation_id = cid
                event_ids.append(e.event_id)

        if not event_ids:
            return

        self._correlations[cid] = _Correlation(
            correlation_id=cid,
            name=f"Auto: {rule.name}",
            pattern=f"rule:{rule.rule_id}",
            events=event_ids,
            created_at=time.time(),
        )
        rule.times_triggered += 1
        self._stats["total_correlations_created"] += 1
        self._stats["total_rules_triggered"] += 1
        self._fire("rule_triggered", {
            "rule_id": rule.rule_id, "correlation_id": cid,
            "event_count": len(event_ids),
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_events(self) -> None:
        """Remove oldest events."""
        items = sorted(self._events.items(), key=lambda x: x[1].timestamp)
        to_remove = len(items) // 4
        for k, _ in items[:to_remove]:
            del self._events[k]

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
            "current_events": len(self._events),
            "current_correlations": len(self._correlations),
            "open_correlations": sum(
                1 for c in self._correlations.values() if c.status == "open"
            ),
            "current_rules": len(self._rules),
            "active_rules": sum(
                1 for r in self._rules.values() if r.enabled
            ),
        }

    def reset(self) -> None:
        self._events.clear()
        self._correlations.clear()
        self._rules.clear()
        self._stats = {k: 0 for k in self._stats}
