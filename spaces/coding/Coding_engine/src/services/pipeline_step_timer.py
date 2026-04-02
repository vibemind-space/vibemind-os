"""Pipeline Step Timer -- tracks timing for individual pipeline steps.

Measures start/stop durations per pipeline step, maintains history for
averaging, and fires callbacks on timing events.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _State:
    timers: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepTimer:
    """Track timing for individual steps within autonomous pipelines."""

    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = _State()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, pipeline_id: str, step_name: str) -> str:
        self._state._seq += 1
        raw = f"{pipeline_id}-{step_name}-{time.time()}-{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pst-{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        total = sum(len(steps) for steps in self._state.timers.values())
        if total >= self.MAX_ENTRIES:
            logger.warning("max_entries_reached", total=total)

    def _get_entry(self, pipeline_id: str, step_name: str) -> dict | None:
        pipeline = self._state.timers.get(pipeline_id)
        if not pipeline:
            return None
        return pipeline.get(step_name)

    # ------------------------------------------------------------------
    # Timer operations
    # ------------------------------------------------------------------

    def start_timer(self, pipeline_id: str, step_name: str) -> str:
        """Start timing a step. Returns timer_id (pst-...)."""
        if not pipeline_id or not step_name:
            return ""

        self._prune_if_needed()

        timer_id = self._generate_id(pipeline_id, step_name)
        now = time.time()

        if pipeline_id not in self._state.timers:
            self._state.timers[pipeline_id] = {}

        existing = self._state.timers[pipeline_id].get(step_name)
        history: List[float] = existing["history"] if existing else []

        self._state.timers[pipeline_id][step_name] = {
            "timer_id": timer_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "started_at": now,
            "stopped_at": None,
            "elapsed": 0.0,
            "history": history,
        }

        self._fire("start_timer", timer_id=timer_id, pipeline_id=pipeline_id, step_name=step_name)
        logger.debug("timer_started", timer_id=timer_id, pipeline_id=pipeline_id, step_name=step_name)
        return timer_id

    def stop_timer(self, pipeline_id: str, step_name: str) -> float:
        """Stop timing a step. Returns elapsed seconds, or 0.0 if not found."""
        entry = self._get_entry(pipeline_id, step_name)
        if not entry or entry["stopped_at"] is not None:
            return 0.0

        now = time.time()
        elapsed = now - entry["started_at"]
        entry["stopped_at"] = now
        entry["elapsed"] = elapsed
        entry["history"].append(elapsed)

        self._fire("stop_timer", timer_id=entry["timer_id"], pipeline_id=pipeline_id, step_name=step_name, elapsed=elapsed)
        logger.debug("timer_stopped", timer_id=entry["timer_id"], elapsed=elapsed)
        return elapsed

    def get_elapsed(self, pipeline_id: str, step_name: str) -> float:
        """Get elapsed time (running or completed). Returns 0.0 if not found."""
        entry = self._get_entry(pipeline_id, step_name)
        if not entry:
            return 0.0
        if entry["stopped_at"] is None:
            return time.time() - entry["started_at"]
        return entry["elapsed"]

    def get_average_time(self, pipeline_id: str, step_name: str) -> float:
        """Get average completion time across all runs of this step."""
        entry = self._get_entry(pipeline_id, step_name)
        if not entry or not entry["history"]:
            return 0.0
        return sum(entry["history"]) / len(entry["history"])

    def get_timers(self, pipeline_id: str) -> list:
        """Get all timers for a pipeline."""
        pipeline = self._state.timers.get(pipeline_id)
        if not pipeline:
            return []
        return list(pipeline.values())

    def get_timer_count(self, pipeline_id: str = "") -> int:
        """Count timers, optionally filtered by pipeline_id."""
        if pipeline_id:
            pipeline = self._state.timers.get(pipeline_id)
            if not pipeline:
                return 0
            return len(pipeline)
        return sum(len(steps) for steps in self._state.timers.values())

    def list_pipelines(self) -> list:
        """Return list of pipeline IDs."""
        return list(self._state.timers.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return stats."""
        total = self.get_timer_count()
        running = 0
        stopped = 0
        for steps in self._state.timers.values():
            for entry in steps.values():
                if entry["stopped_at"] is None:
                    running += 1
                else:
                    stopped += 1
        return {
            "total_timers": total,
            "running": running,
            "stopped": stopped,
            "pipelines": len(self._state.timers),
            "callbacks": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.timers.clear()
        self._state.callbacks.clear()
        self._state._seq = 0

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback. Returns True if removed, False if not found."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)
