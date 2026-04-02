"""Pipeline Throttle Controller - manages rate limiting and throttling for pipelines.

Provides per-pipeline throttle control with configurable max rate and
sliding time windows.  Supports callbacks, pruning, and stats.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import hashlib
import time


@dataclass
class ThrottleEntry:
    """A single throttle configuration bound to a pipeline."""

    throttle_id: str
    pipeline_id: str
    max_rate: int
    window_seconds: float
    requests: List[float] = field(default_factory=list)
    created_at: float = 0.0


class PipelineThrottleController:
    """Per-pipeline request throttle with windowed rate limiting."""

    def __init__(self) -> None:
        self._throttles: Dict[str, ThrottleEntry] = {}      # throttle_id -> entry
        self._pipeline_map: Dict[str, str] = {}              # pipeline_id -> throttle_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"ptc-{self._seq}-{id(self)}"
        return "ptc-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when the store exceeds *_max_entries*."""
        if len(self._throttles) <= self._max_entries:
            return
        sorted_entries = sorted(
            self._throttles.values(), key=lambda e: e.created_at,
        )
        to_remove = len(self._throttles) - self._max_entries
        for entry in sorted_entries[:to_remove]:
            self._throttles.pop(entry.throttle_id, None)
            self._pipeline_map.pop(entry.pipeline_id, None)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def set_throttle(
        self,
        pipeline_id: str,
        max_rate: int,
        window_seconds: float = 60,
    ) -> str:
        """Set or update a throttle for *pipeline_id*.

        Returns the throttle_id (prefixed with ``ptc-``).  If a throttle
        already exists for this pipeline the rate/window are updated in
        place and the existing throttle_id is returned.
        """
        existing_tid = self._pipeline_map.get(pipeline_id)
        if existing_tid and existing_tid in self._throttles:
            entry = self._throttles[existing_tid]
            entry.max_rate = max_rate
            entry.window_seconds = window_seconds
            self._fire("throttle_updated", {
                "throttle_id": existing_tid,
                "pipeline_id": pipeline_id,
                "max_rate": max_rate,
                "window_seconds": window_seconds,
            })
            return existing_tid

        tid = self._generate_id()
        now = time.time()
        entry = ThrottleEntry(
            throttle_id=tid,
            pipeline_id=pipeline_id,
            max_rate=max_rate,
            window_seconds=window_seconds,
            requests=[],
            created_at=now,
        )
        self._throttles[tid] = entry
        self._pipeline_map[pipeline_id] = tid
        self._prune_if_needed()
        self._fire("throttle_set", {
            "throttle_id": tid,
            "pipeline_id": pipeline_id,
            "max_rate": max_rate,
            "window_seconds": window_seconds,
        })
        return tid

    def get_throttle(self, throttle_id: str) -> Optional[Dict[str, Any]]:
        """Return throttle info dict or ``None``."""
        entry = self._throttles.get(throttle_id)
        if entry is None:
            return None
        return {
            "throttle_id": entry.throttle_id,
            "pipeline_id": entry.pipeline_id,
            "max_rate": entry.max_rate,
            "window_seconds": entry.window_seconds,
            "requests": list(entry.requests),
            "created_at": entry.created_at,
        }

    def _clean_requests(self, entry: ThrottleEntry) -> None:
        """Remove request timestamps outside the current window."""
        cutoff = time.time() - entry.window_seconds
        entry.requests = [t for t in entry.requests if t > cutoff]

    def allow_request(self, pipeline_id: str) -> bool:
        """Check if a request is within the rate limit for *pipeline_id*.

        Records the request timestamp when allowed.  Returns ``False``
        when the pipeline has no throttle or the rate limit is reached.
        """
        tid = self._pipeline_map.get(pipeline_id)
        if tid is None:
            return False
        entry = self._throttles.get(tid)
        if entry is None:
            return False

        self._clean_requests(entry)

        if len(entry.requests) < entry.max_rate:
            entry.requests.append(time.time())
            return True

        self._fire("request_throttled", {"pipeline_id": pipeline_id})
        return False

    def get_current_rate(self, pipeline_id: str) -> int:
        """Return the number of requests in the current window."""
        tid = self._pipeline_map.get(pipeline_id)
        if tid is None:
            return 0
        entry = self._throttles.get(tid)
        if entry is None:
            return 0
        self._clean_requests(entry)
        return len(entry.requests)

    def get_remaining(self, pipeline_id: str) -> int:
        """Return remaining allowed requests in the current window."""
        tid = self._pipeline_map.get(pipeline_id)
        if tid is None:
            return 0
        entry = self._throttles.get(tid)
        if entry is None:
            return 0
        self._clean_requests(entry)
        return max(0, entry.max_rate - len(entry.requests))

    def is_throttled(self, pipeline_id: str) -> bool:
        """Return ``True`` if the pipeline has hit its rate limit."""
        tid = self._pipeline_map.get(pipeline_id)
        if tid is None:
            return False
        entry = self._throttles.get(tid)
        if entry is None:
            return False
        self._clean_requests(entry)
        return len(entry.requests) >= entry.max_rate

    def reset_throttle(self, pipeline_id: str) -> bool:
        """Clear request history for *pipeline_id*."""
        tid = self._pipeline_map.get(pipeline_id)
        if tid is None:
            return False
        entry = self._throttles.get(tid)
        if entry is None:
            return False
        entry.requests.clear()
        self._fire("throttle_reset", {"pipeline_id": pipeline_id})
        return True

    def remove_throttle(self, throttle_id: str) -> bool:
        """Remove a throttle by its *throttle_id*."""
        entry = self._throttles.pop(throttle_id, None)
        if entry is None:
            return False
        self._pipeline_map.pop(entry.pipeline_id, None)
        self._fire("throttle_removed", {
            "throttle_id": throttle_id,
            "pipeline_id": entry.pipeline_id,
        })
        return True

    def list_pipelines(self) -> List[str]:
        """Return all pipeline IDs that have a throttle."""
        return list(self._pipeline_map.keys())

    def get_throttle_count(self) -> int:
        """Return the number of active throttles."""
        return len(self._throttles)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
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
        """Return aggregate stats."""
        return {
            "throttle_count": len(self._throttles),
            "pipeline_count": len(self._pipeline_map),
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._throttles.clear()
        self._pipeline_map.clear()
        self._callbacks.clear()
        self._seq = 0
