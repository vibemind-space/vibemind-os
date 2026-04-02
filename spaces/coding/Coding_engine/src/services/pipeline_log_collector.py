"""Pipeline Log Collector – collects and stores pipeline execution logs.

Captures structured log entries per pipeline with level filtering,
step-based querying, and configurable pruning.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

VALID_LEVELS = {"debug", "info", "warning", "error"}


@dataclass
class _LogRecord:
    log_id: str
    pipeline_id: str
    level: str
    message: str
    step_name: str
    metadata: Dict[str, Any]
    created_at: float
    seq: int


class PipelineLogCollector:
    """Collects and stores pipeline execution logs."""

    def __init__(self, max_entries: int = 10000):
        self._records: List[_LogRecord] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._total_logged = 0
        self._level_counts: Dict[str, int] = {k: 0 for k in VALID_LEVELS}

    def log(
        self,
        pipeline_id: str,
        level: str,
        message: str,
        step_name: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not pipeline_id or not message:
            return ""
        if level not in VALID_LEVELS:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{pipeline_id}-{level}-{now}-{self._seq}"
        log_id = "plc-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        record = _LogRecord(
            log_id=log_id,
            pipeline_id=pipeline_id,
            level=level,
            message=message,
            step_name=step_name,
            metadata=metadata or {},
            created_at=now,
            seq=self._seq,
        )
        if len(self._records) >= self._max_entries:
            self._records.pop(0)
        self._records.append(record)
        self._total_logged += 1
        self._level_counts[level] = self._level_counts.get(level, 0) + 1
        logger.debug("log_collected", log_id=log_id, pipeline_id=pipeline_id, level=level)
        self._fire("log_added", {"log_id": log_id, "pipeline_id": pipeline_id, "level": level, "message": message})
        return log_id

    def get_logs(
        self,
        pipeline_id: str,
        level: str = "",
        step_name: str = "",
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for rec in self._records:
            if rec.pipeline_id != pipeline_id:
                continue
            if level and rec.level != level:
                continue
            if step_name and rec.step_name != step_name:
                continue
            results.append(self._record_to_dict(rec))
        return results

    def get_latest_log(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        best: Optional[_LogRecord] = None
        for rec in self._records:
            if rec.pipeline_id != pipeline_id:
                continue
            if best is None or (rec.created_at, rec.seq) > (best.created_at, best.seq):
                best = rec
        if best is None:
            return None
        return self._record_to_dict(best)

    def get_log_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._records)
        return sum(1 for r in self._records if r.pipeline_id == pipeline_id)

    def clear_logs(self, pipeline_id: str) -> int:
        before = len(self._records)
        self._records = [r for r in self._records if r.pipeline_id != pipeline_id]
        cleared = before - len(self._records)
        if cleared:
            logger.info("logs_cleared", pipeline_id=pipeline_id, count=cleared)
            self._fire("logs_cleared", {"pipeline_id": pipeline_id, "count": cleared})
        return cleared

    def list_pipelines(self) -> List[str]:
        return sorted(set(r.pipeline_id for r in self._records))

    def get_total_logs(self) -> int:
        return self._total_logged

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

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_entries": len(self._records),
            "total_logged": self._total_logged,
            "level_counts": dict(self._level_counts),
            "max_entries": self._max_entries,
            "pipeline_count": len(set(r.pipeline_id for r in self._records)),
        }

    def reset(self) -> None:
        self._records.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_logged = 0
        self._level_counts = {k: 0 for k in VALID_LEVELS}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_to_dict(self, r: _LogRecord) -> Dict[str, Any]:
        return {
            "log_id": r.log_id,
            "pipeline_id": r.pipeline_id,
            "level": r.level,
            "message": r.message,
            "step_name": r.step_name,
            "metadata": dict(r.metadata),
            "created_at": r.created_at,
            "seq": r.seq,
        }
