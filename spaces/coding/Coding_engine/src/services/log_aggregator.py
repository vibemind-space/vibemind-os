"""
Log Aggregator — Centralized log collection and search for pipeline runs.

Provides:
- Structured log collection from all pipeline components
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Per-run and per-agent log streams
- Full-text search across logs
- Time-range queries
- Log retention with configurable max entries
- Export and summary generation

Usage:
    logs = LogAggregator()

    # Log from a component
    logs.log("Builder", "info", "Starting code generation", run_id="run-001")

    # Search logs
    results = logs.search("error", level="error")

    # Get run logs
    run_logs = logs.get_run_logs("run-001")
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class LogLevel(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


LOG_LEVEL_MAP = {
    "debug": LogLevel.DEBUG,
    "info": LogLevel.INFO,
    "warning": LogLevel.WARNING,
    "error": LogLevel.ERROR,
    "critical": LogLevel.CRITICAL,
}


@dataclass
class LogEntry:
    """A single log entry."""
    entry_id: str
    source: str          # Component/agent name
    level: str
    level_num: int
    message: str
    run_id: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "source": self.source,
            "level": self.level,
            "message": self.message,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class LogAggregator:
    """Centralized log collection and search."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._entries: List[LogEntry] = []

        # Indexes for fast lookup
        self._by_run: Dict[str, List[int]] = {}     # run_id -> [idx]
        self._by_source: Dict[str, List[int]] = {}   # source -> [idx]

        # Stats
        self._total_logged = 0
        self._total_pruned = 0
        self._level_counts: Dict[str, int] = {}

    # ── Logging ──────────────────────────────────────────────────────

    def log(
        self,
        source: str,
        level: str,
        message: str,
        run_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a log entry."""
        level_lower = level.lower()
        level_num = LOG_LEVEL_MAP.get(level_lower, LogLevel.INFO)

        entry_id = f"log-{uuid.uuid4().hex[:8]}"
        entry = LogEntry(
            entry_id=entry_id,
            source=source,
            level=level_lower,
            level_num=level_num,
            message=message,
            run_id=run_id,
            metadata=metadata or {},
        )

        idx = len(self._entries)
        self._entries.append(entry)
        self._total_logged += 1
        self._level_counts[level_lower] = self._level_counts.get(level_lower, 0) + 1

        # Update indexes
        if run_id:
            if run_id not in self._by_run:
                self._by_run[run_id] = []
            self._by_run[run_id].append(idx)

        if source not in self._by_source:
            self._by_source[source] = []
        self._by_source[source].append(idx)

        # Prune if over limit
        if len(self._entries) > self._max_entries:
            self._prune()

        return entry_id

    def debug(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "debug", message, **kwargs)

    def info(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "info", message, **kwargs)

    def warning(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "warning", message, **kwargs)

    def error(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "error", message, **kwargs)

    def critical(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "critical", message, **kwargs)

    # ── Queries ──────────────────────────────────────────────────────

    def get_run_logs(
        self,
        run_id: str,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get logs for a specific pipeline run."""
        indices = self._by_run.get(run_id, [])
        min_level = LOG_LEVEL_MAP.get(level, 0) if level else 0

        results = []
        for idx in indices:
            if idx < len(self._entries):
                entry = self._entries[idx]
                if entry.level_num >= min_level:
                    results.append(entry.to_dict())

        return results[-limit:]

    def get_source_logs(
        self,
        source: str,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get logs from a specific source/agent."""
        indices = self._by_source.get(source, [])
        min_level = LOG_LEVEL_MAP.get(level, 0) if level else 0

        results = []
        for idx in indices:
            if idx < len(self._entries):
                entry = self._entries[idx]
                if entry.level_num >= min_level:
                    results.append(entry.to_dict())

        return results[-limit:]

    def get_recent(
        self,
        level: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get most recent log entries."""
        min_level = LOG_LEVEL_MAP.get(level, 0) if level else 0

        results = []
        for entry in reversed(self._entries):
            if entry.level_num >= min_level:
                results.append(entry.to_dict())
                if len(results) >= limit:
                    break

        results.reverse()  # Chronological order
        return results

    def get_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent error and critical entries."""
        return self.get_recent(level="error", limit=limit)

    # ── Search ───────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        source: Optional[str] = None,
        level: Optional[str] = None,
        run_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Full-text search across logs."""
        query_lower = query.lower()
        min_level = LOG_LEVEL_MAP.get(level, 0) if level else 0

        results = []
        for entry in self._entries:
            if entry.level_num < min_level:
                continue
            if source and entry.source != source:
                continue
            if run_id and entry.run_id != run_id:
                continue
            if since and entry.timestamp < since:
                continue
            if until and entry.timestamp > until:
                continue

            if query_lower in entry.message.lower() or query_lower in entry.source.lower():
                results.append(entry.to_dict())
                if len(results) >= limit:
                    break

        return results

    # ── Time-Range Queries ───────────────────────────────────────────

    def get_logs_in_range(
        self,
        since: float,
        until: Optional[float] = None,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get logs within a time range."""
        end = until or time.time()
        min_level = LOG_LEVEL_MAP.get(level, 0) if level else 0

        results = []
        for entry in self._entries:
            if entry.timestamp < since:
                continue
            if entry.timestamp > end:
                continue
            if entry.level_num < min_level:
                continue
            results.append(entry.to_dict())
            if len(results) >= limit:
                break

        return results

    # ── Summary ──────────────────────────────────────────────────────

    def get_run_summary(self, run_id: str) -> Dict[str, Any]:
        """Get a summary of a pipeline run's logs."""
        indices = self._by_run.get(run_id, [])
        if not indices:
            return {"run_id": run_id, "total_entries": 0}

        level_counts = {}
        sources = set()
        first_ts = float("inf")
        last_ts = 0.0
        errors = []

        for idx in indices:
            if idx < len(self._entries):
                entry = self._entries[idx]
                level_counts[entry.level] = level_counts.get(entry.level, 0) + 1
                sources.add(entry.source)
                first_ts = min(first_ts, entry.timestamp)
                last_ts = max(last_ts, entry.timestamp)
                if entry.level_num >= LogLevel.ERROR:
                    errors.append(entry.message)

        return {
            "run_id": run_id,
            "total_entries": len(indices),
            "level_counts": level_counts,
            "sources": sorted(sources),
            "duration_seconds": round(last_ts - first_ts, 2) if last_ts > first_ts else 0,
            "error_count": len(errors),
            "recent_errors": errors[-5:],
        }

    def list_runs(self) -> List[str]:
        """List all run IDs with logs."""
        return sorted(self._by_run.keys())

    def list_sources(self) -> List[str]:
        """List all sources with logs."""
        return sorted(self._by_source.keys())

    # ── Export ────────────────────────────────────────────────────────

    def export_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Export all logs for a run."""
        return self.get_run_logs(run_id, limit=self._max_entries)

    # ── Stats ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregator statistics."""
        return {
            "total_entries": len(self._entries),
            "total_logged": self._total_logged,
            "total_pruned": self._total_pruned,
            "level_counts": dict(self._level_counts),
            "run_count": len(self._by_run),
            "source_count": len(self._by_source),
        }

    def reset(self):
        """Reset all logs."""
        self._entries.clear()
        self._by_run.clear()
        self._by_source.clear()
        self._total_logged = 0
        self._total_pruned = 0
        self._level_counts.clear()

    # ── Internal ─────────────────────────────────────────────────────

    def _prune(self):
        """Remove oldest entries to stay under limit."""
        to_remove = len(self._entries) - self._max_entries
        if to_remove <= 0:
            return

        # Remove from front (oldest)
        self._entries = self._entries[to_remove:]
        self._total_pruned += to_remove

        # Rebuild indexes (shifted by to_remove)
        self._by_run.clear()
        self._by_source.clear()
        for idx, entry in enumerate(self._entries):
            if entry.run_id:
                if entry.run_id not in self._by_run:
                    self._by_run[entry.run_id] = []
                self._by_run[entry.run_id].append(idx)
            if entry.source not in self._by_source:
                self._by_source[entry.source] = []
            self._by_source[entry.source].append(idx)
