"""Pipeline failure handler.

Handles pipeline failures with configurable recovery strategies
including retry, skip, abort, and fallback actions.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _HandlerEntry:
    """Configuration for a pipeline failure handler."""
    handler_id: str = ""
    pipeline_id: str = ""
    strategy: str = "retry"  # retry, skip, abort, fallback
    max_retries: int = 3
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _FailureRecord:
    """A recorded pipeline failure."""
    failure_id: str = ""
    pipeline_id: str = ""
    step_name: str = ""
    error: str = ""
    created_at: float = 0.0
    seq: int = 0


class PipelineFailureHandler:
    """Handles pipeline failures with configurable recovery strategies."""

    STRATEGIES = ("retry", "skip", "abort", "fallback")

    def __init__(self, max_entries: int = 50000):
        self._max_entries = max_entries
        self._handlers: Dict[str, _HandlerEntry] = {}
        self._failures: Dict[str, List[_FailureRecord]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _make_id(self, *parts: str) -> str:
        seq = self._next_seq()
        raw = f"{'|'.join(parts)}|{time.time()}|{seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pfh-{digest}"

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def register_handler(self, pipeline_id: str, strategy: str = "retry",
                         max_retries: int = 3) -> str:
        """Register a failure handler for a pipeline.

        Strategies: retry, skip, abort, fallback.
        Returns the handler ID, or empty string on invalid input.
        """
        if not pipeline_id:
            return ""
        if strategy not in self.STRATEGIES:
            return ""
        if max_retries < 0:
            return ""

        hid = self._make_id(pipeline_id, strategy)
        self._handlers[pipeline_id] = _HandlerEntry(
            handler_id=hid,
            pipeline_id=pipeline_id,
            strategy=strategy,
            max_retries=max_retries,
            created_at=time.time(),
            seq=self._seq,
        )
        logger.info("handler_registered", pipeline_id=pipeline_id,
                     strategy=strategy, handler_id=hid)
        self._fire("handler_registered", {
            "handler_id": hid, "pipeline_id": pipeline_id,
            "strategy": strategy,
        })
        return hid

    # ------------------------------------------------------------------
    # Failure recording
    # ------------------------------------------------------------------

    def record_failure(self, pipeline_id: str, step_name: str,
                       error: str = "") -> str:
        """Record a failure for a pipeline step. Returns failure ID."""
        if not pipeline_id or not step_name:
            return ""

        # Enforce max entries across all pipelines
        total = sum(len(v) for v in self._failures.values())
        if total >= self._max_entries:
            self._prune_failures()

        fid = self._make_id(pipeline_id, step_name)
        record = _FailureRecord(
            failure_id=fid,
            pipeline_id=pipeline_id,
            step_name=step_name,
            error=error,
            created_at=time.time(),
            seq=self._seq,
        )

        if pipeline_id not in self._failures:
            self._failures[pipeline_id] = []
        self._failures[pipeline_id].append(record)

        logger.info("failure_recorded", pipeline_id=pipeline_id,
                     step_name=step_name, failure_id=fid)
        self._fire("failure_recorded", {
            "failure_id": fid, "pipeline_id": pipeline_id,
            "step_name": step_name, "error": error,
        })
        return fid

    # ------------------------------------------------------------------
    # Recovery logic
    # ------------------------------------------------------------------

    def get_recovery_action(self, pipeline_id: str) -> str:
        """Return recommended recovery action based on strategy and failure count.

        Returns one of: "retry", "skip", "abort", "fallback", or "abort"
        as a default when retries are exhausted.
        """
        handler = self._handlers.get(pipeline_id)
        if not handler:
            return "abort"

        strategy = handler.strategy
        if strategy == "abort":
            return "abort"
        if strategy == "skip":
            return "skip"
        if strategy == "fallback":
            count = self.get_failure_count(pipeline_id)
            if count >= handler.max_retries:
                return "fallback"
            return "retry"

        # strategy == "retry"
        count = self.get_failure_count(pipeline_id)
        if count >= handler.max_retries:
            return "abort"
        return "retry"

    # ------------------------------------------------------------------
    # Failure queries
    # ------------------------------------------------------------------

    def get_failure_count(self, pipeline_id: str) -> int:
        """Return number of recorded failures for a pipeline."""
        return len(self._failures.get(pipeline_id, []))

    def get_failures(self, pipeline_id: str) -> List[Dict]:
        """Return all failure records for a pipeline."""
        records = self._failures.get(pipeline_id, [])
        return [
            {
                "failure_id": r.failure_id,
                "pipeline_id": r.pipeline_id,
                "step_name": r.step_name,
                "error": r.error,
                "created_at": r.created_at,
                "seq": r.seq,
            }
            for r in records
        ]

    def reset_failures(self, pipeline_id: str) -> bool:
        """Clear all failure records for a pipeline. Returns True if any existed."""
        if pipeline_id not in self._failures or not self._failures[pipeline_id]:
            return False
        self._failures[pipeline_id].clear()
        logger.info("failures_reset", pipeline_id=pipeline_id)
        self._fire("failures_reset", {"pipeline_id": pipeline_id})
        return True

    # ------------------------------------------------------------------
    # Pipeline listing
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return list of pipeline IDs that have registered handlers."""
        return list(self._handlers.keys())

    def get_handler_count(self) -> int:
        """Return number of registered handlers."""
        return len(self._handlers)

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
        total_failures = sum(len(v) for v in self._failures.values())
        return {
            "total_handlers": len(self._handlers),
            "total_failures": total_failures,
            "pipelines_with_failures": sum(
                1 for v in self._failures.values() if v
            ),
            "pipelines_tracked": len(self._failures),
            "callbacks": len(self._callbacks),
            "seq": self._seq,
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        self._handlers.clear()
        self._failures.clear()
        self._callbacks.clear()
        self._seq = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_failures(self) -> None:
        """Remove oldest half of failure records across all pipelines."""
        all_records: List[tuple] = []
        for pid, records in self._failures.items():
            for r in records:
                all_records.append((pid, r))
        all_records.sort(key=lambda x: x[1].created_at)

        to_remove = len(all_records) // 2
        remove_set: Dict[str, set] = {}
        for pid, r in all_records[:to_remove]:
            if pid not in remove_set:
                remove_set[pid] = set()
            remove_set[pid].add(r.failure_id)

        for pid, ids in remove_set.items():
            self._failures[pid] = [
                r for r in self._failures[pid] if r.failure_id not in ids
            ]
