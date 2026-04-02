"""Pipeline backpressure handler.

Manages backpressure for pipelines by tracking queue depth and applying
throttling when depth exceeds configurable thresholds.  Each registered
pipeline is monitored independently so that slow consumers do not starve
fast producers across unrelated flows.
"""

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PipelineEntry:
    """Tracked state for a single pipeline's backpressure."""
    entry_id: str = ""
    pipeline_id: str = ""
    max_queue_depth: int = 100
    throttle_threshold: float = 0.8
    current_depth: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Backpressure Handler
# ---------------------------------------------------------------------------

class PipelineBackpressureHandler:
    """Track queue depth per pipeline and apply throttling."""

    def __init__(self, max_entries: int = 10000):
        self._pipelines: Dict[str, PipelineEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries
        self._stats = {
            "total_registered": 0,
            "total_depth_records": 0,
            "total_throttle_events": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, key: str) -> str:
        """Generate a collision-free ID with prefix 'pbh-'."""
        self._seq += 1
        raw = f"{key}:{uuid.uuid4().hex}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pbh-{digest}"

    # ------------------------------------------------------------------
    # Pipeline registration
    # ------------------------------------------------------------------

    def register_pipeline(
        self,
        pipeline_id: str,
        max_queue_depth: int = 100,
        throttle_threshold: float = 0.8,
    ) -> str:
        """Register a pipeline for backpressure tracking.

        Returns the generated entry ID, or an empty string on failure.
        """
        if not pipeline_id:
            return ""
        if max_queue_depth < 1:
            return ""
        if not (0.0 <= throttle_threshold <= 1.0):
            return ""
        if len(self._pipelines) >= self._max_entries:
            logger.warning("max_entries_reached", max_entries=self._max_entries)
            return ""

        entry_id = self._next_id(pipeline_id)
        self._pipelines[entry_id] = PipelineEntry(
            entry_id=entry_id,
            pipeline_id=pipeline_id,
            max_queue_depth=max_queue_depth,
            throttle_threshold=throttle_threshold,
            seq=self._seq,
        )
        self._stats["total_registered"] += 1
        logger.info("pipeline_registered", entry_id=entry_id, pipeline_id=pipeline_id)
        self._fire("pipeline_registered", {
            "entry_id": entry_id,
            "pipeline_id": pipeline_id,
        })
        return entry_id

    # ------------------------------------------------------------------
    # Depth tracking
    # ------------------------------------------------------------------

    def record_depth(self, pipeline_id: str, current_depth: int) -> None:
        """Record the current queue depth for a pipeline."""
        for entry in self._pipelines.values():
            if entry.pipeline_id == pipeline_id:
                entry.current_depth = max(0, current_depth)
                entry.updated_at = time.time()
                self._stats["total_depth_records"] += 1

                pressure = entry.current_depth / entry.max_queue_depth if entry.max_queue_depth > 0 else 0.0
                if pressure >= entry.throttle_threshold:
                    self._stats["total_throttle_events"] += 1
                    logger.warning(
                        "throttle_triggered",
                        pipeline_id=pipeline_id,
                        pressure=round(pressure, 4),
                    )
                    self._fire("throttle_triggered", {
                        "pipeline_id": pipeline_id,
                        "current_depth": entry.current_depth,
                        "pressure": round(pressure, 4),
                    })
                return

        logger.debug("pipeline_not_found", pipeline_id=pipeline_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_throttled(self, pipeline_id: str) -> bool:
        """Return True if the pipeline's depth exceeds its throttle threshold."""
        for entry in self._pipelines.values():
            if entry.pipeline_id == pipeline_id:
                if entry.max_queue_depth <= 0:
                    return False
                return (entry.current_depth / entry.max_queue_depth) >= entry.throttle_threshold
        return False

    def get_pressure(self, pipeline_id: str) -> float:
        """Return the ratio of current depth to max queue depth (0.0-1.0)."""
        for entry in self._pipelines.values():
            if entry.pipeline_id == pipeline_id:
                if entry.max_queue_depth <= 0:
                    return 0.0
                return min(1.0, entry.current_depth / entry.max_queue_depth)
        return 0.0

    def get_current_depth(self, pipeline_id: str) -> int:
        """Return the current queue depth for a pipeline."""
        for entry in self._pipelines.values():
            if entry.pipeline_id == pipeline_id:
                return entry.current_depth
        return 0

    def list_pipelines(self) -> List[str]:
        """Return a list of all registered pipeline IDs."""
        seen: List[str] = []
        for entry in self._pipelines.values():
            if entry.pipeline_id not in seen:
                seen.append(entry.pipeline_id)
        return seen

    def get_pipeline_count(self) -> int:
        """Return the number of registered pipeline entries."""
        return len(self._pipelines)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback that fires on state changes."""
        if not name:
            return
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return aggregate statistics."""
        throttled = sum(
            1 for e in self._pipelines.values()
            if e.max_queue_depth > 0
            and (e.current_depth / e.max_queue_depth) >= e.throttle_threshold
        )
        return {
            **self._stats,
            "current_pipelines": len(self._pipelines),
            "throttled_pipelines": throttled,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all pipelines, callbacks, and statistics."""
        self._pipelines.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {
            "total_registered": 0,
            "total_depth_records": 0,
            "total_throttle_events": 0,
        }
        logger.info("handler_reset")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)
