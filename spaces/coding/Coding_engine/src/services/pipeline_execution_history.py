"""Pipeline execution history service.

Tracks pipeline execution history, recording each run with timing,
status, and results. Supports querying per-pipeline statistics,
success rates, average durations, and purging old entries.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class _ExecutionEntry:
    """A single pipeline execution entry."""
    exec_id: str = ""
    pipeline_name: str = ""
    status: str = "unknown"
    duration_ms: float = 0.0
    result: Any = None
    metadata: Dict = field(default_factory=dict)
    timestamp: float = 0.0
    seq: int = 0


class PipelineExecutionHistory:
    """Records and queries pipeline execution history."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._entries: Dict[str, _ExecutionEntry] = {}
        self._seq = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_recorded": 0,
            "total_purged": 0,
        }

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_execution(
        self,
        pipeline_name: str,
        status: str,
        duration_ms: float,
        result: Any = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Record a pipeline execution.

        Stores the execution with timing, status, and optional result
        and metadata. Returns the generated exec_id (prefixed "peh-").
        """
        with self._lock:
            if not pipeline_name:
                return ""

            if len(self._entries) >= self._max_entries:
                self._prune()

            self._seq += 1
            exec_id = "peh-" + hashlib.sha256(
                f"{pipeline_name}{time.time()}{self._seq}".encode()
            ).hexdigest()[:16]

            now = time.time()
            self._entries[exec_id] = _ExecutionEntry(
                exec_id=exec_id,
                pipeline_name=pipeline_name,
                status=status,
                duration_ms=float(duration_ms),
                result=result,
                metadata=metadata or {},
                timestamp=now,
                seq=self._seq,
            )
            self._stats["total_recorded"] += 1
            logger.debug(
                "execution_recorded exec_id=%s pipeline=%s status=%s",
                exec_id, pipeline_name, status,
            )
            self._fire("execution_recorded", {
                "exec_id": exec_id,
                "pipeline_name": pipeline_name,
                "status": status,
                "duration_ms": duration_ms,
            })
            return exec_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_execution(self, exec_id: str) -> Optional[Dict]:
        """Get a single execution by ID.

        Returns None if the exec_id is not found.
        """
        with self._lock:
            entry = self._entries.get(exec_id)
            if not entry:
                return None
            return self._to_dict(entry)

    def get_pipeline_history(
        self, pipeline_name: str, limit: int = 100
    ) -> List[Dict]:
        """Get execution history for a specific pipeline.

        Returns most recent first, up to *limit* entries.
        """
        with self._lock:
            results = []
            for entry in self._entries.values():
                if entry.pipeline_name != pipeline_name:
                    continue
                results.append(self._to_dict(entry))
            results.sort(key=lambda x: -x["seq"])
            return results[:limit]

    def get_latest_execution(self, pipeline_name: str) -> Optional[Dict]:
        """Get the most recent execution for a pipeline.

        Returns None if no executions exist for the pipeline.
        """
        with self._lock:
            latest: Optional[_ExecutionEntry] = None
            for entry in self._entries.values():
                if entry.pipeline_name != pipeline_name:
                    continue
                if latest is None or entry.seq > latest.seq:
                    latest = entry
            if latest is None:
                return None
            return self._to_dict(latest)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_success_rate(self, pipeline_name: str) -> float:
        """Get the success rate for a pipeline as 0.0-1.0.

        Returns 0.0 if no executions exist for the pipeline.
        A status of "success" or "succeeded" is counted as successful.
        """
        with self._lock:
            total = 0
            successes = 0
            for entry in self._entries.values():
                if entry.pipeline_name != pipeline_name:
                    continue
                total += 1
                if entry.status in ("success", "succeeded"):
                    successes += 1
            if total == 0:
                return 0.0
            return successes / total

    def get_average_duration(self, pipeline_name: str) -> float:
        """Get average duration_ms for a pipeline.

        Returns 0.0 if no executions exist for the pipeline.
        """
        with self._lock:
            total_duration = 0.0
            count = 0
            for entry in self._entries.values():
                if entry.pipeline_name != pipeline_name:
                    continue
                total_duration += entry.duration_ms
                count += 1
            if count == 0:
                return 0.0
            return total_duration / count

    def get_execution_count(self, pipeline_name: Optional[str] = None) -> int:
        """Count executions, optionally filtered by pipeline name.

        If *pipeline_name* is None, returns the total count across
        all pipelines.
        """
        with self._lock:
            if pipeline_name is None:
                return len(self._entries)
            count = 0
            for entry in self._entries.values():
                if entry.pipeline_name == pipeline_name:
                    count += 1
            return count

    def list_pipelines(self) -> List[str]:
        """List all pipeline names that have recorded history.

        Returns a sorted list of unique pipeline names seen across
        all stored execution entries.
        """
        with self._lock:
            names = set()
            for entry in self._entries.values():
                names.add(entry.pipeline_name)
            return sorted(names)

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Purge old entries.

        If *before_timestamp* is given, only entries recorded before
        that timestamp are removed. Otherwise all entries are purged.
        Returns the number of entries removed.
        """
        with self._lock:
            to_remove = []
            for eid, entry in self._entries.items():
                if before_timestamp is not None:
                    if entry.timestamp >= before_timestamp:
                        continue
                to_remove.append(eid)

            for eid in to_remove:
                del self._entries[eid]

            count = len(to_remove)
            if count > 0:
                self._stats["total_purged"] += count
                logger.debug("entries_purged count=%d", count)
                self._fire("entries_purged", {"count": count})
            return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, entry: _ExecutionEntry) -> Dict:
        """Convert an entry dataclass to a plain dict."""
        return {
            "exec_id": entry.exec_id,
            "pipeline_name": entry.pipeline_name,
            "status": entry.status,
            "duration_ms": entry.duration_ms,
            "result": entry.result,
            "metadata": dict(entry.metadata),
            "timestamp": entry.timestamp,
            "seq": entry.seq,
        }

    def _prune(self) -> None:
        """Remove oldest entries when at capacity.

        Called internally (under lock) when the entry count reaches
        max_entries. Removes approximately half the oldest entries.
        """
        prunable = sorted(
            self._entries.items(), key=lambda x: x[1].seq
        )
        to_remove = max(len(prunable) // 2, 1)
        removed = 0
        for eid, _ in prunable[:to_remove]:
            del self._entries[eid]
            removed += 1
        if removed > 0:
            self._stats["total_purged"] += removed

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.

        Returns True if the callback was registered, False if the
        name is already taken.
        """
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name.

        Returns True if the callback was found and removed, False
        if no callback with that name exists.
        """
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict) -> None:
        """Invoke all registered callbacks with the action and detail.

        Exceptions raised by individual callbacks are silently caught
        so that one failing callback does not affect others.
        """
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics.

        Includes total recorded count, total purged count, current
        entry count, and unique pipeline count.
        """
        with self._lock:
            return {
                **self._stats,
                "current_entries": len(self._entries),
                "unique_pipelines": len(set(
                    e.pipeline_name for e in self._entries.values()
                )),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all entries, counters, and callbacks.

        Restores the service to its initial empty state. The sequence
        counter is reset to zero, all callbacks are removed, and
        all stat counters are zeroed out.
        """
        with self._lock:
            self._entries.clear()
            self._seq = 0
            self._callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
            logger.debug("execution_history_reset")
