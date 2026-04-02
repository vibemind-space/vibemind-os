"""Pipeline Log Shipper – buffers and ships pipeline logs to destinations.

Collects log entries from pipeline components, buffers them, and ships
in batches to configured destinations. Supports multiple log levels,
structured metadata, and configurable flush intervals.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _LogEntry:
    log_id: str
    level: str
    source: str
    message: str
    metadata: Dict[str, Any]
    timestamp: float
    shipped: bool


@dataclass
class _Destination:
    dest_id: str
    name: str
    dest_type: str  # console, file, http, custom
    config: Dict[str, Any]
    handler: Optional[Callable]
    total_shipped: int
    enabled: bool
    tags: List[str]
    created_at: float


class PipelineLogShipper:
    """Buffers and ships pipeline logs to destinations."""

    LEVELS = ("debug", "info", "warning", "error", "critical")
    DEST_TYPES = ("console", "file", "http", "custom")

    def __init__(self, max_buffer: int = 100000, max_destinations: int = 100):
        self._buffer: List[_LogEntry] = []
        self._destinations: Dict[str, _Destination] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_buffer = max_buffer
        self._max_destinations = max_destinations
        self._seq = 0

        # stats
        self._total_logged = 0
        self._total_shipped = 0
        self._total_dropped = 0

    # ------------------------------------------------------------------
    # Destination management
    # ------------------------------------------------------------------

    def add_destination(
        self,
        name: str,
        dest_type: str = "custom",
        config: Optional[Dict[str, Any]] = None,
        handler: Optional[Callable] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if dest_type not in self.DEST_TYPES:
            return ""
        if len(self._destinations) >= self._max_destinations:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{dest_type}-{now}-{self._seq}"
        did = "dst-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        dest = _Destination(
            dest_id=did,
            name=name,
            dest_type=dest_type,
            config=config or {},
            handler=handler,
            total_shipped=0,
            enabled=True,
            tags=tags or [],
            created_at=now,
        )
        self._destinations[did] = dest
        self._name_index[name] = did
        self._fire("destination_added", {"dest_id": did, "name": name})
        return did

    def get_destination(self, dest_id: str) -> Optional[Dict[str, Any]]:
        d = self._destinations.get(dest_id)
        if not d:
            return None
        return {
            "dest_id": d.dest_id,
            "name": d.name,
            "dest_type": d.dest_type,
            "config": dict(d.config),
            "total_shipped": d.total_shipped,
            "enabled": d.enabled,
            "tags": list(d.tags),
            "created_at": d.created_at,
        }

    def remove_destination(self, dest_id: str) -> bool:
        d = self._destinations.pop(dest_id, None)
        if not d:
            return False
        self._name_index.pop(d.name, None)
        return True

    def enable_destination(self, dest_id: str) -> bool:
        d = self._destinations.get(dest_id)
        if not d or d.enabled:
            return False
        d.enabled = True
        return True

    def disable_destination(self, dest_id: str) -> bool:
        d = self._destinations.get(dest_id)
        if not d or not d.enabled:
            return False
        d.enabled = False
        return True

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(
        self,
        level: str,
        source: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not message:
            return ""
        if level not in self.LEVELS:
            return ""

        # evict oldest if buffer full
        if len(self._buffer) >= self._max_buffer:
            self._buffer.pop(0)
            self._total_dropped += 1

        self._seq += 1
        now = time.time()
        raw = f"{source}-{message}-{now}-{self._seq}"
        lid = "log-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _LogEntry(
            log_id=lid,
            level=level,
            source=source,
            message=message,
            metadata=metadata or {},
            timestamp=now,
            shipped=False,
        )
        self._buffer.append(entry)
        self._total_logged += 1
        return lid

    def get_buffer_size(self) -> int:
        return len(self._buffer)

    def get_unshipped_count(self) -> int:
        return sum(1 for e in self._buffer if not e.shipped)

    # ------------------------------------------------------------------
    # Shipping
    # ------------------------------------------------------------------

    def flush(self) -> int:
        """Ship all unshipped logs to enabled destinations. Returns count shipped."""
        unshipped = [e for e in self._buffer if not e.shipped]
        if not unshipped:
            return 0

        enabled_dests = [d for d in self._destinations.values() if d.enabled]
        if not enabled_dests:
            return 0

        shipped_count = 0
        for entry in unshipped:
            log_dict = {
                "log_id": entry.log_id,
                "level": entry.level,
                "source": entry.source,
                "message": entry.message,
                "metadata": entry.metadata,
                "timestamp": entry.timestamp,
            }
            for dest in enabled_dests:
                if dest.handler:
                    try:
                        dest.handler(log_dict)
                        dest.total_shipped += 1
                    except Exception:
                        pass
            entry.shipped = True
            shipped_count += 1

        self._total_shipped += shipped_count
        self._fire("logs_flushed", {"count": shipped_count})
        return shipped_count

    def clear_shipped(self) -> int:
        """Remove shipped entries from buffer. Returns count removed."""
        before = len(self._buffer)
        self._buffer = [e for e in self._buffer if not e.shipped]
        removed = before - len(self._buffer)
        return removed

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search_logs(
        self,
        level: str = "",
        source: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for e in reversed(self._buffer):
            if level and e.level != level:
                continue
            if source and e.source != source:
                continue
            results.append({
                "log_id": e.log_id,
                "level": e.level,
                "source": e.source,
                "message": e.message,
                "metadata": e.metadata,
                "timestamp": e.timestamp,
                "shipped": e.shipped,
            })
            if len(results) >= limit:
                break
        return results

    def list_destinations(self) -> List[Dict[str, Any]]:
        return [self.get_destination(d.dest_id) for d in self._destinations.values()]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "buffer_size": len(self._buffer),
            "total_logged": self._total_logged,
            "total_shipped": self._total_shipped,
            "total_dropped": self._total_dropped,
            "destinations": len(self._destinations),
            "unshipped": self.get_unshipped_count(),
        }

    def reset(self) -> None:
        self._buffer.clear()
        self._destinations.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_logged = 0
        self._total_shipped = 0
        self._total_dropped = 0
