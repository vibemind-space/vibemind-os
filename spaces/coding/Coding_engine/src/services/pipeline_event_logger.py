"""Pipeline Event Logger — records and queries pipeline execution events.

Features:
- Structured event logging with severity levels
- Filtering by event type, source, and severity
- Aggregation summaries (by severity, source, type)
- Timeline queries with optional source filtering
- Purge by timestamp for retention management
- Collision-free IDs via SHA256 + sequence counter
- Change callbacks for reactive integrations
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"debug", "info", "warning", "error", "critical"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EventEntry:
    """A single pipeline execution event."""
    event_id: str
    event_type: str
    source: str
    severity: str
    data: Dict[str, Any]
    tags: List[str]
    timestamp: float
    seq: int


# ---------------------------------------------------------------------------
# Pipeline Event Logger
# ---------------------------------------------------------------------------

class PipelineEventLogger:
    """Records and queries pipeline execution events with filtering
    and aggregation capabilities."""

    def __init__(self, max_entries: int = 10000) -> None:
        """Initialise the event logger.

        Args:
            max_entries: Maximum number of events to retain before pruning
                the oldest entries.
        """
        self._max_entries = max_entries
        self._entries: Dict[str, EventEntry] = {}
        self._ordered_ids: List[str] = []
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_events_logged": 0,
            "total_events_purged": 0,
            "total_events_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with the ``pel-`` prefix."""
        self._seq += 1
        raw = f"{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pel-{digest}_{self._seq}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.

        Args:
            name: Unique name for the callback registration.
            callback: A callable accepting ``(action: str, data: dict)``.

        Returns:
            ``True`` if registered, ``False`` if *name* already exists.
        """
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.

        Returns:
            ``True`` if removed, ``False`` if *name* was not found.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Notify all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when the store exceeds *max_entries*."""
        if len(self._entries) <= self._max_entries:
            return
        overflow = len(self._entries) - self._max_entries
        to_remove = self._ordered_ids[:overflow]
        for eid in to_remove:
            self._entries.pop(eid, None)
        self._ordered_ids = self._ordered_ids[overflow:]
        self._stats["total_events_pruned"] += overflow

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def log_event(
        self,
        event_type: str,
        source: str,
        data: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Log a pipeline execution event.

        Args:
            event_type: Category of the event (e.g. ``"build_started"``).
            source: Originating component (e.g. ``"compiler"``).
            data: Arbitrary payload dict.
            severity: One of ``"debug"``, ``"info"``, ``"warning"``,
                ``"error"``, ``"critical"``.
            tags: Optional list of string tags for the event.

        Returns:
            The generated *event_id* string.
        """
        if severity not in VALID_SEVERITIES:
            severity = "info"

        event_id = self._next_id(f"{event_type}-{source}")
        entry = EventEntry(
            event_id=event_id,
            event_type=event_type,
            source=source,
            severity=severity,
            data=dict(data) if data else {},
            tags=list(tags) if tags else [],
            timestamp=time.time(),
            seq=self._seq,
        )
        self._entries[event_id] = entry
        self._ordered_ids.append(event_id)
        self._stats["total_events_logged"] += 1

        logger.debug(
            "event_logged",
            event_id=event_id,
            event_type=event_type,
            source=source,
            severity=severity,
        )

        self._prune()
        self._fire("event_logged", {
            "event_id": event_id,
            "event_type": event_type,
            "source": source,
            "severity": severity,
        })
        return event_id

    def get_event(self, event_id: str) -> Optional[Dict]:
        """Retrieve a single event by its ID.

        Args:
            event_id: The ID returned by :meth:`log_event`.

        Returns:
            Event dict or ``None`` if not found.
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    def query(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query events with optional filters.

        Filters are combined with AND logic.  Results are returned most-recent
        first, up to *limit* entries.

        Args:
            event_type: Filter by event type string.
            source: Filter by source string.
            severity: Filter by severity level.
            limit: Maximum number of results to return.

        Returns:
            A list of event dicts matching the criteria.
        """
        results: List[Dict] = []
        for eid in reversed(self._ordered_ids):
            entry = self._entries.get(eid)
            if entry is None:
                continue
            if event_type and entry.event_type != event_type:
                continue
            if source and entry.source != source:
                continue
            if severity and entry.severity != severity:
                continue
            results.append(self._entry_to_dict(entry))
            if len(results) >= limit:
                break
        return results

    def get_by_source(self, source: str) -> List[Dict]:
        """Return all events originating from *source*.

        Args:
            source: The source component to filter by.

        Returns:
            List of matching event dicts, most-recent first.
        """
        return self.query(source=source, limit=len(self._entries) or 1)

    def get_by_severity(self, severity: str) -> List[Dict]:
        """Return all events at the given *severity* level.

        Args:
            severity: One of the valid severity levels.

        Returns:
            List of matching event dicts, most-recent first.
        """
        return self.query(severity=severity, limit=len(self._entries) or 1)

    # ------------------------------------------------------------------
    # Summary & aggregation
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict:
        """Return an aggregated summary of all stored events.

        Returns:
            A dict with keys ``total_events``, ``by_severity``,
            ``by_source``, and ``by_type``, each containing counts.
        """
        by_severity: Dict[str, int] = defaultdict(int)
        by_source: Dict[str, int] = defaultdict(int)
        by_type: Dict[str, int] = defaultdict(int)

        for entry in self._entries.values():
            by_severity[entry.severity] += 1
            by_source[entry.source] += 1
            by_type[entry.event_type] += 1

        return {
            "total_events": len(self._entries),
            "by_severity": dict(sorted(by_severity.items())),
            "by_source": dict(sorted(by_source.items())),
            "by_type": dict(sorted(by_type.items())),
        }

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    def get_timeline(
        self,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Return events sorted chronologically (oldest first).

        Args:
            source: Optionally restrict to events from this source.
            limit: Maximum number of events to return.

        Returns:
            List of event dicts in ascending timestamp order.
        """
        candidates: List[EventEntry] = []
        for eid in self._ordered_ids:
            entry = self._entries.get(eid)
            if entry is None:
                continue
            if source and entry.source != source:
                continue
            candidates.append(entry)

        candidates.sort(key=lambda e: e.timestamp)
        return [self._entry_to_dict(e) for e in candidates[-limit:]]

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Remove events older than *before_timestamp*.

        If *before_timestamp* is ``None`` all events are purged.

        Args:
            before_timestamp: Unix epoch threshold; events with a
                timestamp strictly less than this value are removed.

        Returns:
            The number of events purged.
        """
        if before_timestamp is None:
            count = len(self._entries)
            self._entries.clear()
            self._ordered_ids.clear()
            self._stats["total_events_purged"] += count
            self._fire("events_purged", {"count": count})
            return count

        to_remove: List[str] = []
        for eid in self._ordered_ids:
            entry = self._entries.get(eid)
            if entry is not None and entry.timestamp < before_timestamp:
                to_remove.append(eid)

        for eid in to_remove:
            self._entries.pop(eid, None)
        self._ordered_ids = [
            eid for eid in self._ordered_ids if eid not in set(to_remove)
        ]

        count = len(to_remove)
        self._stats["total_events_purged"] += count
        if count:
            self._fire("events_purged", {"count": count,
                                          "before_timestamp": before_timestamp})
        return count

    # ------------------------------------------------------------------
    # Listing helpers
    # ------------------------------------------------------------------

    def list_sources(self) -> List[str]:
        """Return a sorted list of unique source strings."""
        return sorted({e.source for e in self._entries.values()})

    def list_event_types(self) -> List[str]:
        """Return a sorted list of unique event type strings."""
        return sorted({e.event_type for e in self._entries.values()})

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return internal counters and current sizes.

        Returns:
            Dict with lifetime counters and current entry/callback counts.
        """
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "current_callbacks": len(self._callbacks),
            "current_seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all events, callbacks, and counters."""
        self._entries.clear()
        self._ordered_ids.clear()
        self._seq = 0
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, e: EventEntry) -> Dict:
        """Convert an internal dataclass to a plain dict."""
        return {
            "event_id": e.event_id,
            "event_type": e.event_type,
            "source": e.source,
            "severity": e.severity,
            "data": e.data,
            "tags": list(e.tags),
            "timestamp": e.timestamp,
            "seq": e.seq,
        }
