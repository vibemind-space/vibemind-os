"""Pipeline Event Journal -- records and queries pipeline events.

Provides an append-only, in-memory event journal for pipeline execution.
Every recorded event captures the pipeline, event type, severity level,
optional data payload, and a monotonic sequence number.  The journal
supports filtering by pipeline, event type, and severity, as well as
cross-pipeline recent-event queries and per-pipeline statistics.

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

_VALID_SEVERITIES = {"info", "warning", "error", "critical"}


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _EventEntry:
    """A single recorded pipeline event."""

    event_id: str = ""
    pipeline_id: str = ""
    event_type: str = ""
    data: Any = None
    severity: str = "info"
    created_at: float = 0.0
    seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class PipelineEventJournal:
    """In-memory event journal for pipeline execution.

    Parameters
    ----------
    max_entries:
        Maximum number of events to keep.  When the limit is reached the
        oldest quarter of events is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, _EventEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}

        # indexes for fast lookup
        self._pipeline_index: Dict[str, List[str]] = {}     # pipeline_id -> [event_id]
        self._type_index: Dict[str, List[str]] = {}         # event_type  -> [event_id]
        self._severity_index: Dict[str, List[str]] = {}     # severity    -> [event_id]

        # stats counters
        self._stats: Dict[str, int] = {
            "total_recorded": 0,
            "total_pruned": 0,
            "total_cleared": 0,
            "total_queries": 0,
        }

        logger.debug("pipeline_event_journal.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_event(
        self,
        pipeline_id: str,
        event_type: str,
        data: Any = None,
        severity: str = "info",
    ) -> str:
        """Record a pipeline event and return its ``event_id``.

        Returns an empty string when *pipeline_id* or *event_type* is falsy,
        or when *severity* is not one of the accepted values.
        """
        if not pipeline_id or not event_type:
            return ""
        if severity not in _VALID_SEVERITIES:
            return ""

        with self._lock:
            # prune if at capacity
            if len(self._entries) >= self._max_entries:
                self._prune()

            self._seq += 1
            now = time.time()
            raw = f"{pipeline_id}-{event_type}-{now}-{self._seq}"
            event_id = "pej-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            entry = _EventEntry(
                event_id=event_id,
                pipeline_id=pipeline_id,
                event_type=event_type,
                data=data,
                severity=severity,
                created_at=now,
                seq=self._seq,
            )
            self._entries[event_id] = entry

            # update indexes
            self._pipeline_index.setdefault(pipeline_id, []).append(event_id)
            self._type_index.setdefault(event_type, []).append(event_id)
            self._severity_index.setdefault(severity, []).append(event_id)

            self._stats["total_recorded"] += 1

        logger.debug(
            "pipeline_event_journal.record_event event_id=%s pipeline_id=%s "
            "event_type=%s severity=%s",
            event_id,
            pipeline_id,
            event_type,
            severity,
        )
        self._fire("event_recorded", {
            "event_id": event_id,
            "pipeline_id": pipeline_id,
            "event_type": event_type,
            "severity": severity,
        })
        return event_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Return a single event as a dict, or ``None``."""
        with self._lock:
            e = self._entries.get(event_id)
            if e is None:
                return None
            return self._to_dict(e)

    def get_pipeline_events(
        self,
        pipeline_id: str,
        event_type: str = "",
        severity: str = "",
    ) -> List[Dict[str, Any]]:
        """Return events for *pipeline_id*, optionally filtered.

        Results are sorted newest-first (by seq descending).
        """
        with self._lock:
            self._stats["total_queries"] += 1
            ids = self._pipeline_index.get(pipeline_id, [])
            entries = [self._entries[eid] for eid in ids if eid in self._entries]

            if event_type:
                entries = [e for e in entries if e.event_type == event_type]
            if severity:
                entries = [e for e in entries if e.severity == severity]

            entries.sort(key=lambda e: e.seq, reverse=True)
            return [self._to_dict(e) for e in entries]

    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent events across all pipelines.

        Sorted by ``created_at`` descending, then ``seq`` descending.
        """
        with self._lock:
            self._stats["total_queries"] += 1
            entries = sorted(
                self._entries.values(),
                key=lambda e: (e.created_at, e.seq),
                reverse=True,
            )
            return [self._to_dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # Counting / Summaries
    # ------------------------------------------------------------------

    def get_event_count_by_type(self, pipeline_id: str) -> Dict[str, int]:
        """Return ``{event_type: count}`` for *pipeline_id*."""
        with self._lock:
            ids = self._pipeline_index.get(pipeline_id, [])
            entries = [self._entries[eid] for eid in ids if eid in self._entries]
            summary: Dict[str, int] = {}
            for e in entries:
                summary[e.event_type] = summary.get(e.event_type, 0) + 1
            return summary

    def get_event_count_by_severity(self, pipeline_id: str) -> Dict[str, int]:
        """Return ``{severity: count}`` for *pipeline_id*."""
        with self._lock:
            ids = self._pipeline_index.get(pipeline_id, [])
            entries = [self._entries[eid] for eid in ids if eid in self._entries]
            summary: Dict[str, int] = {}
            for e in entries:
                summary[e.severity] = summary.get(e.severity, 0) + 1
            return summary

    def get_event_count(self) -> int:
        """Return the total number of events in the journal."""
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Clearing
    # ------------------------------------------------------------------

    def clear_pipeline(self, pipeline_id: str) -> int:
        """Remove all events for *pipeline_id*.  Returns the count removed."""
        with self._lock:
            ids = list(self._pipeline_index.get(pipeline_id, []))
            removed = 0
            for eid in ids:
                if eid in self._entries:
                    self._remove_entry(eid)
                    removed += 1

            self._stats["total_cleared"] += removed

        if removed:
            logger.debug(
                "pipeline_event_journal.clear_pipeline pipeline_id=%s count=%d",
                pipeline_id,
                removed,
            )
            self._fire("pipeline_cleared", {
                "pipeline_id": pipeline_id,
                "count": removed,
            })

        return removed

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return all unique pipeline IDs that have at least one event."""
        with self._lock:
            return [
                pid
                for pid, ids in self._pipeline_index.items()
                if any(eid in self._entries for eid in ids)
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
            return {
                **self._stats,
                "current_entries": len(self._entries),
                "unique_pipelines": len([
                    p for p, ids in self._pipeline_index.items()
                    if any(eid in self._entries for eid in ids)
                ]),
                "unique_event_types": len([
                    t for t, ids in self._type_index.items()
                    if any(eid in self._entries for eid in ids)
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._entries.clear()
            self._pipeline_index.clear()
            self._type_index.clear()
            self._severity_index.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("pipeline_event_journal.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, e: _EventEntry) -> Dict[str, Any]:
        """Convert an event entry to a plain dict."""
        return {
            "event_id": e.event_id,
            "pipeline_id": e.pipeline_id,
            "event_type": e.event_type,
            "data": e.data,
            "severity": e.severity,
            "created_at": e.created_at,
            "seq": e.seq,
        }

    def _remove_entry(self, event_id: str) -> None:
        """Remove a single entry from the journal and all indexes."""
        e = self._entries.pop(event_id, None)
        if e is None:
            return

        # clean pipeline index
        ids = self._pipeline_index.get(e.pipeline_id)
        if ids:
            try:
                ids.remove(event_id)
            except ValueError:
                pass

        # clean type index
        ids = self._type_index.get(e.event_type)
        if ids:
            try:
                ids.remove(event_id)
            except ValueError:
                pass

        # clean severity index
        ids = self._severity_index.get(e.severity)
        if ids:
            try:
                ids.remove(event_id)
            except ValueError:
                pass

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries = sorted(self._entries.values(), key=lambda e: e.seq)
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            self._remove_entry(e.event_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("pipeline_event_journal.prune removed=%d", to_remove)
