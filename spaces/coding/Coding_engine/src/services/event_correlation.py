"""
Event Correlation Engine — detects patterns, cascading failures,
and provides root-cause analysis across pipeline events.

Features:
- Correlation rules: define patterns that link events together
- Sliding time-window grouping
- Cascading failure detection (A→B→C chains)
- Root-cause candidate ranking
- Event frequency / anomaly detection
- Correlation history for forensics
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & data structures
# ---------------------------------------------------------------------------

class CorrelationStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    ESCALATED = "escalated"


class RulePriority(int, Enum):
    LOW = 30
    MEDIUM = 50
    HIGH = 70
    CRITICAL = 90


@dataclass
class CorrelationRule:
    """A rule that groups related events together."""
    name: str
    event_types: Set[str]  # event types this rule matches
    time_window: float = 30.0  # seconds
    min_events: int = 2
    priority: int = RulePriority.MEDIUM
    condition: Optional[Callable] = None  # extra guard (events) -> bool
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorrelatedGroup:
    """A group of events that are correlated."""
    group_id: str
    rule_name: str
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: CorrelationStatus = CorrelationStatus.OPEN
    created_at: float = 0.0
    closed_at: float = 0.0
    root_cause: Optional[Dict[str, Any]] = None
    priority: int = RulePriority.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class EventCorrelationEngine:
    """Correlates events across the pipeline to detect patterns and failures."""

    def __init__(
        self,
        default_window: float = 30.0,
        max_groups: int = 500,
        max_events: int = 5000,
    ):
        self._default_window = default_window
        self._max_groups = max_groups
        self._max_events = max_events

        # Rule registry: name → CorrelationRule
        self._rules: Dict[str, CorrelationRule] = {}

        # Open correlation groups: group_id → CorrelatedGroup
        self._groups: Dict[str, CorrelatedGroup] = {}

        # Closed groups archive (for forensics)
        self._archive: List[CorrelatedGroup] = []

        # Raw event buffer for windowed matching
        self._event_buffer: List[Dict[str, Any]] = []

        # Cascade chain definitions: (source_type, target_type) → weight
        self._cascade_edges: Dict[tuple, float] = {}

        # Frequency tracking: event_type → [timestamps]
        self._frequency: Dict[str, List[float]] = {}

        # Stats
        self._stats = {
            "total_events": 0,
            "total_rules": 0,
            "total_groups_created": 0,
            "total_groups_closed": 0,
            "total_escalated": 0,
            "total_root_causes": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def register_rule(
        self,
        name: str,
        event_types: Set[str],
        time_window: float = 0.0,
        min_events: int = 2,
        priority: int = RulePriority.MEDIUM,
        condition: Optional[Callable] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Register a correlation rule. Returns False if name exists."""
        if name in self._rules:
            return False
        self._rules[name] = CorrelationRule(
            name=name,
            event_types=set(event_types),
            time_window=time_window or self._default_window,
            min_events=min_events,
            priority=priority,
            condition=condition,
            tags=tags or set(),
            metadata=metadata or {},
        )
        self._stats["total_rules"] += 1
        return True

    def unregister_rule(self, name: str) -> bool:
        """Remove a rule."""
        if name not in self._rules:
            return False
        del self._rules[name]
        return True

    def get_rule(self, name: str) -> Optional[Dict]:
        """Get rule info."""
        r = self._rules.get(name)
        if not r:
            return None
        return {
            "name": r.name,
            "event_types": sorted(r.event_types),
            "time_window": r.time_window,
            "min_events": r.min_events,
            "priority": r.priority,
            "tags": sorted(r.tags),
            "metadata": r.metadata,
        }

    def list_rules(self) -> List[Dict]:
        """List all rules."""
        return [self.get_rule(n) for n in sorted(self._rules)]

    # ------------------------------------------------------------------
    # Cascade chain definitions
    # ------------------------------------------------------------------

    def define_cascade(self, source_type: str, target_type: str, weight: float = 1.0) -> None:
        """Define a causal edge: source_type can cause target_type."""
        self._cascade_edges[(source_type, target_type)] = weight

    def get_cascade_chain(self, event_type: str, max_depth: int = 10) -> List[str]:
        """Trace the cascade chain forward from an event type."""
        chain: List[str] = [event_type]
        visited: Set[str] = {event_type}
        current = event_type
        for _ in range(max_depth):
            nexts = [t for (s, t), _ in self._cascade_edges.items()
                     if s == current and t not in visited]
            if not nexts:
                break
            # Pick highest-weight next
            best = max(nexts, key=lambda t: self._cascade_edges.get((current, t), 0))
            chain.append(best)
            visited.add(best)
            current = best
        return chain

    def get_cascade_roots(self, event_type: str, max_depth: int = 10) -> List[str]:
        """Trace backward to find root causes of an event type."""
        roots: List[str] = [event_type]
        visited: Set[str] = {event_type}
        current = event_type
        for _ in range(max_depth):
            parents = [s for (s, t), _ in self._cascade_edges.items()
                       if t == current and s not in visited]
            if not parents:
                break
            best = max(parents, key=lambda s: self._cascade_edges.get((s, current), 0))
            roots.insert(0, best)
            visited.add(best)
            current = best
        return roots

    # ------------------------------------------------------------------
    # Event ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        event_type: str,
        source: str = "",
        data: Optional[Dict] = None,
        timestamp: float = 0.0,
    ) -> List[str]:
        """
        Ingest an event and return IDs of any correlated groups it was added to.
        """
        ts = timestamp or time.time()
        event = {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}",
            "event_type": event_type,
            "source": source,
            "data": data or {},
            "timestamp": ts,
        }

        self._event_buffer.append(event)
        self._stats["total_events"] += 1

        # Update frequency tracking
        self._frequency.setdefault(event_type, []).append(ts)

        # Match against rules
        matched_groups: List[str] = []
        for rule in self._rules.values():
            if event_type not in rule.event_types:
                continue

            # Find events in window matching this rule
            cutoff = ts - rule.time_window
            window_events = [
                e for e in self._event_buffer
                if e["event_type"] in rule.event_types
                and e["timestamp"] >= cutoff
            ]

            if len(window_events) < rule.min_events:
                continue

            # Check condition guard
            if rule.condition and not rule.condition(window_events):
                continue

            # Find or create group
            group = self._find_open_group(rule.name, cutoff)
            if not group:
                group = self._create_group(rule)

            # Add event to group (avoid duplicates)
            existing_ids = {e["event_id"] for e in group.events}
            for we in window_events:
                if we["event_id"] not in existing_ids:
                    group.events.append(we)
                    existing_ids.add(we["event_id"])

            matched_groups.append(group.group_id)

        # Prune old events
        self._prune_buffer()

        return matched_groups

    def _find_open_group(self, rule_name: str, cutoff: float) -> Optional[CorrelatedGroup]:
        """Find an existing open group for this rule within the time window."""
        for g in self._groups.values():
            if (g.rule_name == rule_name
                    and g.status == CorrelationStatus.OPEN
                    and g.created_at >= cutoff):
                return g
        return None

    def _create_group(self, rule: CorrelationRule) -> CorrelatedGroup:
        """Create a new correlated group."""
        gid = f"grp-{uuid.uuid4().hex[:8]}"
        group = CorrelatedGroup(
            group_id=gid,
            rule_name=rule.name,
            created_at=time.time(),
            priority=rule.priority,
        )
        self._groups[gid] = group
        self._stats["total_groups_created"] += 1

        # Prune old groups if over limit
        if len(self._groups) > self._max_groups:
            self._prune_groups()

        return group

    # ------------------------------------------------------------------
    # Group management
    # ------------------------------------------------------------------

    def close_group(self, group_id: str) -> bool:
        """Close a correlation group."""
        g = self._groups.get(group_id)
        if not g or g.status != CorrelationStatus.OPEN:
            return False
        g.status = CorrelationStatus.CLOSED
        g.closed_at = time.time()
        self._stats["total_groups_closed"] += 1
        # Move to archive
        self._archive.append(g)
        del self._groups[group_id]
        return True

    def escalate_group(self, group_id: str) -> bool:
        """Escalate a correlation group."""
        g = self._groups.get(group_id)
        if not g or g.status != CorrelationStatus.OPEN:
            return False
        g.status = CorrelationStatus.ESCALATED
        self._stats["total_escalated"] += 1
        return True

    def set_root_cause(self, group_id: str, root_cause: Dict[str, Any]) -> bool:
        """Set the root cause for a correlated group."""
        g = self._groups.get(group_id)
        if not g:
            # Check archive
            for ag in self._archive:
                if ag.group_id == group_id:
                    ag.root_cause = root_cause
                    self._stats["total_root_causes"] += 1
                    return True
            return False
        g.root_cause = root_cause
        self._stats["total_root_causes"] += 1
        return True

    def get_group(self, group_id: str) -> Optional[Dict]:
        """Get group details."""
        g = self._groups.get(group_id)
        if not g:
            # Check archive
            for ag in self._archive:
                if ag.group_id == group_id:
                    g = ag
                    break
        if not g:
            return None
        return {
            "group_id": g.group_id,
            "rule_name": g.rule_name,
            "status": g.status.value,
            "event_count": len(g.events),
            "events": g.events,
            "created_at": g.created_at,
            "closed_at": g.closed_at,
            "root_cause": g.root_cause,
            "priority": g.priority,
            "metadata": g.metadata,
        }

    def get_open_groups(self, rule_name: Optional[str] = None, min_priority: int = 0) -> List[Dict]:
        """Get all open correlation groups."""
        results = []
        for g in self._groups.values():
            if g.status != CorrelationStatus.OPEN:
                continue
            if rule_name and g.rule_name != rule_name:
                continue
            if g.priority < min_priority:
                continue
            results.append({
                "group_id": g.group_id,
                "rule_name": g.rule_name,
                "status": g.status.value,
                "event_count": len(g.events),
                "created_at": g.created_at,
                "priority": g.priority,
            })
        return sorted(results, key=lambda x: x["priority"], reverse=True)

    def get_archived_groups(self, rule_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get closed/archived groups."""
        results = []
        for g in reversed(self._archive):
            if rule_name and g.rule_name != rule_name:
                continue
            results.append({
                "group_id": g.group_id,
                "rule_name": g.rule_name,
                "status": g.status.value,
                "event_count": len(g.events),
                "created_at": g.created_at,
                "closed_at": g.closed_at,
                "root_cause": g.root_cause,
                "priority": g.priority,
            })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Root-cause analysis
    # ------------------------------------------------------------------

    def analyze_root_cause(self, group_id: str) -> Optional[Dict]:
        """
        Analyze a group to suggest root cause candidates.
        Uses cascade chains and event ordering.
        """
        g = self._groups.get(group_id)
        if not g:
            return None

        if not g.events:
            return {"candidates": [], "chain": []}

        # Sort events by timestamp
        sorted_events = sorted(g.events, key=lambda e: e["timestamp"])
        first_event = sorted_events[0]

        # Find cascade roots for the earliest event
        roots = self.get_cascade_roots(first_event["event_type"])

        # Score candidates: earlier = more likely root cause
        candidates = []
        for evt in sorted_events:
            score = 1.0
            # Earlier events get higher score
            if evt == first_event:
                score += 0.5
            # Events in cascade root chain get bonus
            if evt["event_type"] in roots:
                score += 0.3
            candidates.append({
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "source": evt["source"],
                "timestamp": evt["timestamp"],
                "score": round(score, 2),
            })

        candidates.sort(key=lambda c: c["score"], reverse=True)

        return {
            "group_id": group_id,
            "candidates": candidates,
            "chain": roots,
            "first_event": first_event["event_type"],
            "event_count": len(sorted_events),
        }

    # ------------------------------------------------------------------
    # Frequency / anomaly detection
    # ------------------------------------------------------------------

    def get_event_frequency(
        self,
        event_type: str,
        window: float = 60.0,
    ) -> Dict:
        """Get event frequency stats within a time window."""
        now = time.time()
        cutoff = now - window
        timestamps = self._frequency.get(event_type, [])
        recent = [t for t in timestamps if t >= cutoff]

        count = len(recent)
        rate = count / window if window > 0 else 0

        return {
            "event_type": event_type,
            "count": count,
            "window_seconds": window,
            "rate_per_second": round(rate, 4),
            "rate_per_minute": round(rate * 60, 2),
        }

    def detect_frequency_anomalies(
        self,
        window: float = 60.0,
        threshold_multiplier: float = 3.0,
    ) -> List[Dict]:
        """Detect event types with abnormally high frequency."""
        now = time.time()
        anomalies = []

        # Calculate average rate across all event types
        rates = []
        for et in self._frequency:
            cutoff = now - window
            count = len([t for t in self._frequency[et] if t >= cutoff])
            rate = count / window if window > 0 else 0
            rates.append((et, count, rate))

        if not rates:
            return []

        avg_rate = sum(r for _, _, r in rates) / len(rates)
        threshold = avg_rate * threshold_multiplier

        for et, count, rate in rates:
            if rate > threshold and count >= 3:
                anomalies.append({
                    "event_type": et,
                    "count": count,
                    "rate_per_second": round(rate, 4),
                    "avg_rate": round(avg_rate, 4),
                    "multiplier": round(rate / avg_rate, 2) if avg_rate > 0 else 0,
                })

        return sorted(anomalies, key=lambda a: a["count"], reverse=True)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_buffer(self) -> None:
        """Remove old events from the buffer."""
        if len(self._event_buffer) <= self._max_events:
            return
        # Keep only recent half
        keep = self._max_events // 2
        removed = len(self._event_buffer) - keep
        self._event_buffer = self._event_buffer[-keep:]
        self._stats["total_pruned"] += removed

    def _prune_groups(self) -> None:
        """Remove oldest low-priority open groups."""
        if len(self._groups) <= self._max_groups:
            return
        # Sort by priority (low first), then creation time (oldest first)
        sorted_groups = sorted(
            self._groups.values(),
            key=lambda g: (g.priority, g.created_at),
        )
        # Remove bottom quarter
        to_remove = len(self._groups) // 4
        for g in sorted_groups[:to_remove]:
            g.status = CorrelationStatus.CLOSED
            g.closed_at = time.time()
            self._archive.append(g)
            del self._groups[g.group_id]
            self._stats["total_groups_closed"] += 1

    def cleanup_frequency(self, max_age: float = 3600.0) -> int:
        """Remove old frequency entries. Returns count removed."""
        cutoff = time.time() - max_age
        removed = 0
        for et in list(self._frequency.keys()):
            before = len(self._frequency[et])
            self._frequency[et] = [t for t in self._frequency[et] if t >= cutoff]
            removed += before - len(self._frequency[et])
            if not self._frequency[et]:
                del self._frequency[et]
        return removed

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Get engine statistics."""
        return {
            **self._stats,
            "open_groups": len(self._groups),
            "archived_groups": len(self._archive),
            "buffer_size": len(self._event_buffer),
            "event_types_tracked": len(self._frequency),
            "cascade_edges": len(self._cascade_edges),
            "rules_registered": len(self._rules),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._rules.clear()
        self._groups.clear()
        self._archive.clear()
        self._event_buffer.clear()
        self._cascade_edges.clear()
        self._frequency.clear()
        self._stats = {k: 0 for k in self._stats}
