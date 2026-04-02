"""Agent Log Store -- structured log storage per agent with search and filtering.

Provides a centralized store for structured agent logs with level-based
filtering, substring search, per-agent queries, and time-based purging.
All data lives in-memory with automatic pruning when the entry limit is
reached.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _LogEntry:
    """A single structured log entry."""
    log_id: str = ""
    agent_id: str = ""
    level: str = "info"
    message: str = ""
    context: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentLogStore:
    """In-memory structured log store for agent-level logs."""

    LEVELS = ("debug", "info", "warning", "error", "critical")

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._logs: Dict[str, _LogEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}

        # indexes for fast lookup
        self._agent_index: Dict[str, List[str]] = {}   # agent_id -> [log_id]
        self._level_index: Dict[str, List[str]] = {}   # level -> [log_id]

        # stats counters
        self._stats = {
            "total_logged": 0,
            "total_pruned": 0,
            "total_purged": 0,
            "total_searches": 0,
        }

        logger.debug("agent_log_store.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(
        self,
        agent_id: str,
        level: str,
        message: str,
        context: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Store a structured log entry and return its log_id."""
        if not agent_id or not message:
            return ""
        if level not in self.LEVELS:
            return ""

        # prune if at capacity
        if len(self._logs) >= self._max_entries:
            self._prune()

        self._seq += 1
        now = time.time()
        raw = f"{agent_id}-{level}-{now}-{self._seq}"
        lid = "als-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _LogEntry(
            log_id=lid,
            agent_id=agent_id,
            level=level,
            message=message,
            context=dict(context) if context else {},
            tags=list(tags) if tags else [],
            created_at=now,
            seq=self._seq,
        )
        self._logs[lid] = entry

        # update indexes
        self._agent_index.setdefault(agent_id, []).append(lid)
        self._level_index.setdefault(level, []).append(lid)

        self._stats["total_logged"] += 1

        logger.debug(
            "agent_log_store.log",
            log_id=lid,
            agent_id=agent_id,
            level=level,
        )
        self._fire("log_added", {
            "log_id": lid,
            "agent_id": agent_id,
            "level": level,
        })
        return lid

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_log(self, log_id: str) -> Optional[Dict]:
        """Return a single log entry as a dict, or None."""
        e = self._logs.get(log_id)
        if not e:
            return None
        return self._to_dict(e)

    def get_agent_logs(
        self,
        agent_id: str,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Return logs for a specific agent, newest first."""
        ids = self._agent_index.get(agent_id, [])
        entries = [self._logs[lid] for lid in ids if lid in self._logs]

        if level is not None:
            entries = [e for e in entries if e.level == level]

        entries.sort(key=lambda e: e.seq, reverse=True)
        return [self._to_dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_logs(
        self,
        query: str,
        agent_id: Optional[str] = None,
    ) -> List[Dict]:
        """Substring search in log messages. Returns newest first."""
        self._stats["total_searches"] += 1

        if not query:
            return []

        if agent_id is not None:
            ids = self._agent_index.get(agent_id, [])
            pool = [self._logs[lid] for lid in ids if lid in self._logs]
        else:
            pool = list(self._logs.values())

        query_lower = query.lower()
        matched = [e for e in pool if query_lower in e.message.lower()]

        matched.sort(key=lambda e: e.seq, reverse=True)
        return [self._to_dict(e) for e in matched]

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_log_count(
        self,
        agent_id: Optional[str] = None,
        level: Optional[str] = None,
    ) -> int:
        """Count log entries matching the given filters."""
        if agent_id is None and level is None:
            return len(self._logs)

        candidates: Optional[set] = None

        if agent_id is not None:
            ids = self._agent_index.get(agent_id, [])
            candidates = set(lid for lid in ids if lid in self._logs)

        if level is not None:
            ids = set(
                lid for lid in self._level_index.get(level, [])
                if lid in self._logs
            )
            candidates = ids if candidates is None else candidates & ids

        return len(candidates) if candidates is not None else 0

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one log entry."""
        return [
            aid for aid, ids in self._agent_index.items()
            if any(lid in self._logs for lid in ids)
        ]

    # ------------------------------------------------------------------
    # Purging
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Remove log entries older than the given timestamp.

        If no timestamp is provided, purge all entries.
        Returns count of purged entries.
        """
        to_remove: List[str] = []

        for lid, e in self._logs.items():
            if before_timestamp is not None:
                if e.created_at < before_timestamp:
                    to_remove.append(lid)
            else:
                to_remove.append(lid)

        for lid in to_remove:
            self._remove_log(lid)

        self._stats["total_purged"] += len(to_remove)

        if to_remove:
            logger.debug("agent_log_store.purge", count=len(to_remove))
            self._fire("logs_purged", {"count": len(to_remove)})

        return len(to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
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
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_logs": len(self._logs),
            "unique_agents": len([
                a for a, ids in self._agent_index.items()
                if any(lid in self._logs for lid in ids)
            ]),
            "unique_levels": len([
                lv for lv, ids in self._level_index.items()
                if any(lid in self._logs for lid in ids)
            ]),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._logs.clear()
        self._agent_index.clear()
        self._level_index.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_log_store.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, e: _LogEntry) -> Dict:
        """Convert a log entry to a plain dict."""
        return {
            "log_id": e.log_id,
            "agent_id": e.agent_id,
            "level": e.level,
            "message": e.message,
            "context": dict(e.context),
            "tags": list(e.tags),
            "created_at": e.created_at,
            "seq": e.seq,
        }

    def _remove_log(self, log_id: str) -> None:
        """Remove a single log entry from store and indexes."""
        e = self._logs.pop(log_id, None)
        if not e:
            return
        # clean agent index
        ids = self._agent_index.get(e.agent_id)
        if ids:
            try:
                ids.remove(log_id)
            except ValueError:
                pass
        # clean level index
        ids = self._level_index.get(e.level)
        if ids:
            try:
                ids.remove(log_id)
            except ValueError:
                pass

    def _prune(self) -> None:
        """Remove oldest entries when at capacity."""
        entries = sorted(self._logs.values(), key=lambda e: e.seq)
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            self._remove_log(e.log_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("agent_log_store.prune", removed=to_remove)
