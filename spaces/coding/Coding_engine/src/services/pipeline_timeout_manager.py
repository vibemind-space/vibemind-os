"""Pipeline timeout manager – manages execution timeouts for pipelines.

Tracks per-pipeline deadlines, checks expiry, extends or cancels timeouts,
and fires callbacks on state changes so callers can react to overruns.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _TimeoutEntry:
    """Internal record for a single pipeline timeout."""

    timeout_id: str = ""
    pipeline_id: str = ""
    timeout_seconds: float = 0.0
    deadline: float = 0.0
    label: str = ""
    seq: int = 0
    created_at: float = field(default_factory=time.time)


class PipelineTimeoutManager:
    """Manages execution timeouts for pipelines."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._timeouts: Dict[str, _TimeoutEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{uuid.uuid4().hex}{self._seq}"
        return "ptm2-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is exceeded."""
        if len(self._timeouts) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._timeouts,
            key=lambda tid: self._timeouts[tid].created_at,
        )
        remove_count = len(self._timeouts) - self._max_entries
        for tid in sorted_ids[:remove_count]:
            entry = self._timeouts.pop(tid)
            logger.debug("pipeline_timeout.pruned", pipeline_id=entry.pipeline_id)

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def set_timeout(
        self,
        pipeline_id: str,
        timeout_seconds: float,
        label: str = "",
    ) -> str:
        """Set a timeout for *pipeline_id*.  Returns the timeout ID."""
        if not pipeline_id or timeout_seconds <= 0.0:
            return ""
        now = time.time()
        tid = self._generate_id(pipeline_id)
        entry = _TimeoutEntry(
            timeout_id=tid,
            pipeline_id=pipeline_id,
            timeout_seconds=timeout_seconds,
            deadline=now + timeout_seconds,
            label=label,
            seq=self._seq,
            created_at=now,
        )
        self._timeouts[pipeline_id] = entry
        self._prune_if_needed()
        logger.info(
            "pipeline_timeout.set",
            pipeline_id=pipeline_id,
            timeout_seconds=timeout_seconds,
            timeout_id=tid,
        )
        self._fire("timeout_set", {"pipeline_id": pipeline_id, "timeout_id": tid, "timeout_seconds": timeout_seconds})
        return tid

    def check_timeout(self, pipeline_id: str) -> bool:
        """Return ``True`` if *pipeline_id* has timed out."""
        entry = self._timeouts.get(pipeline_id)
        if entry is None:
            return False
        expired = time.time() >= entry.deadline
        if expired:
            logger.warning("pipeline_timeout.expired", pipeline_id=pipeline_id)
            self._fire("timeout_expired", {"pipeline_id": pipeline_id, "timeout_id": entry.timeout_id})
        return expired

    def get_remaining(self, pipeline_id: str) -> float:
        """Return seconds remaining for *pipeline_id*, or ``0.0`` if expired / unknown."""
        entry = self._timeouts.get(pipeline_id)
        if entry is None:
            return 0.0
        remaining = entry.deadline - time.time()
        return max(0.0, remaining)

    def cancel_timeout(self, pipeline_id: str) -> bool:
        """Cancel the timeout for *pipeline_id*.  Returns ``True`` on success."""
        entry = self._timeouts.pop(pipeline_id, None)
        if entry is None:
            return False
        logger.info("pipeline_timeout.cancelled", pipeline_id=pipeline_id)
        self._fire("timeout_cancelled", {"pipeline_id": pipeline_id, "timeout_id": entry.timeout_id})
        return True

    def extend_timeout(self, pipeline_id: str, extra_seconds: float) -> bool:
        """Extend the deadline for *pipeline_id* by *extra_seconds*."""
        entry = self._timeouts.get(pipeline_id)
        if entry is None or extra_seconds <= 0.0:
            return False
        entry.deadline += extra_seconds
        entry.timeout_seconds += extra_seconds
        logger.info(
            "pipeline_timeout.extended",
            pipeline_id=pipeline_id,
            extra_seconds=extra_seconds,
            new_deadline=entry.deadline,
        )
        self._fire("timeout_extended", {"pipeline_id": pipeline_id, "extra_seconds": extra_seconds})
        return True

    def list_pipelines(self) -> List[str]:
        """Return a list of all pipeline IDs with active timeouts."""
        return list(self._timeouts.keys())

    def get_timeout_count(self) -> int:
        """Return the number of active timeouts."""
        return len(self._timeouts)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback under *name*."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if it existed."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("pipeline_timeout.callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics."""
        now = time.time()
        expired = sum(1 for e in self._timeouts.values() if now >= e.deadline)
        return {
            "active_timeouts": len(self._timeouts),
            "expired": expired,
            "callbacks": len(self._callbacks),
            "seq": self._seq,
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._timeouts.clear()
        self._callbacks.clear()
        self._seq = 0
        logger.info("pipeline_timeout.reset")
