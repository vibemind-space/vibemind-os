"""Pipeline Step Profiler -- profiles individual pipeline steps.

Records start/end times per pipeline step, tracks elapsed durations and
run counts, and fires callbacks on profiling events.
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
    profiles: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepProfiler:
    """Profile individual steps within autonomous pipelines."""

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
        return f"psp-{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        total = sum(len(steps) for steps in self._state.profiles.values())
        if total >= self.MAX_ENTRIES:
            logger.warning("max_entries_reached", total=total)

    def _get_entry(self, pipeline_id: str, step_name: str) -> dict | None:
        pipeline = self._state.profiles.get(pipeline_id)
        if not pipeline:
            return None
        return pipeline.get(step_name)

    # ------------------------------------------------------------------
    # Profile operations
    # ------------------------------------------------------------------

    def start_profile(self, pipeline_id: str, step_name: str) -> str:
        """Start profiling a step. Returns profile_id (psp-...)."""
        if not pipeline_id or not step_name:
            return ""

        self._prune_if_needed()

        profile_id = self._generate_id(pipeline_id, step_name)
        now = time.time()

        if pipeline_id not in self._state.profiles:
            self._state.profiles[pipeline_id] = {}

        existing = self._state.profiles[pipeline_id].get(step_name)
        run_count = existing["run_count"] if existing else 0

        self._state.profiles[pipeline_id][step_name] = {
            "profile_id": profile_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "started_at": now,
            "ended_at": None,
            "elapsed": 0.0,
            "run_count": run_count,
        }

        self._fire("start_profile", {"profile_id": profile_id, "pipeline_id": pipeline_id, "step_name": step_name})
        logger.debug("profile_started", profile_id=profile_id, pipeline_id=pipeline_id, step_name=step_name)
        return profile_id

    def end_profile(self, pipeline_id: str, step_name: str) -> float:
        """End profiling a step. Returns elapsed seconds, or 0.0 if not found."""
        entry = self._get_entry(pipeline_id, step_name)
        if not entry or entry["ended_at"] is not None:
            return 0.0

        now = time.time()
        elapsed = now - entry["started_at"]
        entry["ended_at"] = now
        entry["elapsed"] = elapsed
        entry["run_count"] += 1

        self._fire("end_profile", {"profile_id": entry["profile_id"], "pipeline_id": pipeline_id, "step_name": step_name, "elapsed": elapsed})
        logger.debug("profile_ended", profile_id=entry["profile_id"], elapsed=elapsed)
        return elapsed

    def get_profile(self, pipeline_id: str, step_name: str) -> dict | None:
        """Get current/last profile for a step."""
        return self._get_entry(pipeline_id, step_name)

    def get_profiles(self, pipeline_id: str) -> list:
        """Get all profiles for a pipeline."""
        pipeline = self._state.profiles.get(pipeline_id)
        if not pipeline:
            return []
        return list(pipeline.values())

    def get_slowest_step(self, pipeline_id: str) -> dict | None:
        """Get step with longest elapsed time among completed profiles."""
        pipeline = self._state.profiles.get(pipeline_id)
        if not pipeline:
            return None

        slowest: dict | None = None
        max_elapsed = -1.0

        for entry in pipeline.values():
            if entry["ended_at"] is not None and entry["elapsed"] > max_elapsed:
                max_elapsed = entry["elapsed"]
                slowest = entry

        return slowest

    def get_profile_count(self, pipeline_id: str = "") -> int:
        """Count profiles, optionally filtered by pipeline_id."""
        if pipeline_id:
            pipeline = self._state.profiles.get(pipeline_id)
            if not pipeline:
                return 0
            return len(pipeline)
        return sum(len(steps) for steps in self._state.profiles.values())

    def list_pipelines(self) -> list:
        """Return list of pipeline IDs."""
        return list(self._state.profiles.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return stats."""
        total = self.get_profile_count()
        running = 0
        completed = 0
        for steps in self._state.profiles.values():
            for entry in steps.values():
                if entry["ended_at"] is None:
                    running += 1
                else:
                    completed += 1
        return {
            "total_profiles": total,
            "running": running,
            "completed": completed,
            "pipelines": len(self._state.profiles),
            "callbacks": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.profiles.clear()
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

    def _fire(self, action: str, detail: dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)
