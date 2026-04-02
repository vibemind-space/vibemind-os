"""Pipeline Log Aggregator – centralised log collection and querying.

Collects log entries from pipeline components with structured metadata,
supports severity filtering, source filtering, and time-range queries.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _LogEntry:
    entry_id: str
    source: str
    level: str
    message: str
    data: Dict[str, Any]
    tags: List[str]
    timestamp: float


class PipelineLogAggregator:
    """Centralised log collection and querying."""

    LEVELS = {"debug": 0, "info": 1, "warn": 2, "error": 3, "critical": 4}

    def __init__(self, max_entries: int = 200000, min_level: str = "debug"):
        self._entries: List[_LogEntry] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._min_level = min_level
        self._seq = 0
        self._total_logged = 0
        self._level_counts: Dict[str, int] = {k: 0 for k in self.LEVELS}

    def log(self, source: str, level: str, message: str, data: Optional[Dict[str, Any]] = None, tags: Optional[List[str]] = None) -> str:
        if not source or not message:
            return ""
        if level not in self.LEVELS:
            return ""
        if self.LEVELS[level] < self.LEVELS.get(self._min_level, 0):
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{source}-{level}-{now}-{self._seq}"
        eid = "log-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        entry = _LogEntry(entry_id=eid, source=source, level=level, message=message, data=data or {}, tags=tags or [], timestamp=now)
        if len(self._entries) >= self._max_entries:
            self._entries.pop(0)
        self._entries.append(entry)
        self._total_logged += 1
        self._level_counts[level] = self._level_counts.get(level, 0) + 1
        self._fire("log_entry", {"source": source, "level": level, "message": message})
        return eid

    def debug(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "debug", message, **kwargs)

    def info(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "info", message, **kwargs)

    def warn(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "warn", message, **kwargs)

    def error(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "error", message, **kwargs)

    def critical(self, source: str, message: str, **kwargs) -> str:
        return self.log(source, "critical", message, **kwargs)

    def query(self, source: str = "", level: str = "", min_level: str = "", search: str = "", tag: str = "", limit: int = 100, since: float = 0.0) -> List[Dict[str, Any]]:
        results = []
        min_sev = self.LEVELS.get(min_level, 0)
        for entry in reversed(self._entries):
            if since > 0 and entry.timestamp < since:
                continue
            if source and entry.source != source:
                continue
            if level and entry.level != level:
                continue
            if min_level and self.LEVELS.get(entry.level, 0) < min_sev:
                continue
            if search and search.lower() not in entry.message.lower():
                continue
            if tag and tag not in entry.tags:
                continue
            results.append(self._entry_to_dict(entry))
            if len(results) >= limit:
                break
        return results

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        for entry in reversed(self._entries):
            if entry.entry_id == entry_id:
                return self._entry_to_dict(entry)
        return None

    def get_sources(self) -> List[str]:
        return sorted(set(e.source for e in self._entries))

    def get_level_counts(self) -> Dict[str, int]:
        return dict(self._level_counts)

    def set_min_level(self, level: str) -> bool:
        if level not in self.LEVELS:
            return False
        self._min_level = level
        return True

    def clear(self) -> int:
        count = len(self._entries)
        self._entries.clear()
        return count

    def _entry_to_dict(self, e: _LogEntry) -> Dict[str, Any]:
        return {"entry_id": e.entry_id, "source": e.source, "level": e.level, "message": e.message, "data": dict(e.data), "tags": list(e.tags), "timestamp": e.timestamp}

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        return {"current_entries": len(self._entries), "total_logged": self._total_logged, "level_counts": dict(self._level_counts), "min_level": self._min_level}

    def reset(self) -> None:
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_logged = 0
        self._level_counts = {k: 0 for k in self.LEVELS}
