"""Pipeline step retry service.

Manages retry policies and attempt tracking for individual pipeline steps —
supporting configurable max retries, backoff seconds, attempt recording,
and should-retry checks per pipeline/step combination.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class _State:
    """Internal state for the step retry service."""

    retries: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline Step Retry Service
# ---------------------------------------------------------------------------


class PipelineStepRetry:
    """Manages retry policies and attempt tracking for pipeline steps."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._state = _State()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a unique ID with prefix 'psr2-'."""
        self._state._seq += 1
        raw = f"{seed}:{time.time()}:{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"psr2-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when total retry configs exceed max_entries."""
        total = sum(
            len(steps) for steps in self._state.retries.values()
        )
        if total < self._max_entries:
            return
        # Flatten, sort by created_at, remove oldest
        all_entries = []
        for pid, steps in self._state.retries.items():
            for sname, entry in steps.items():
                all_entries.append((pid, sname, entry.get("created_at", 0)))
        all_entries.sort(key=lambda x: x[2])
        remove_count = total - self._max_entries + 1
        for i in range(remove_count):
            pid, sname, _ = all_entries[i]
            del self._state.retries[pid][sname]
            if not self._state.retries[pid]:
                del self._state.retries[pid]
        logger.debug("retries_pruned", removed=remove_count)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        """Register a change callback."""
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        """Fire all registered callbacks."""
        detail_dict = dict(detail)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail_dict)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def configure_retry(
        self,
        pipeline_id: str,
        step_name: str,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> str:
        """Configure retry policy for a pipeline step.

        Returns retry_id (prefix 'psr2-').
        """
        self._prune_if_needed()

        retry_id = self._next_id(f"{pipeline_id}:{step_name}")
        now = time.time()

        if pipeline_id not in self._state.retries:
            self._state.retries[pipeline_id] = {}

        self._state.retries[pipeline_id][step_name] = {
            "retry_id": retry_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "max_retries": max_retries,
            "backoff_seconds": backoff_seconds,
            "attempts": 0,
            "succeeded": False,
            "created_at": now,
        }

        logger.info(
            "retry_configured",
            pipeline_id=pipeline_id,
            step_name=step_name,
            retry_id=retry_id,
        )
        self._fire(
            "retry_configured",
            pipeline_id=pipeline_id,
            step_name=step_name,
            retry_id=retry_id,
        )
        return retry_id

    def record_attempt(
        self,
        pipeline_id: str,
        step_name: str,
        success: bool,
    ) -> dict:
        """Record a retry attempt for a pipeline step.

        Returns dict with retry_id, attempt count, should_retry, and exhausted.
        """
        steps = self._state.retries.get(pipeline_id, {})
        entry = steps.get(step_name)
        if entry is None:
            return {
                "retry_id": "",
                "attempt": 0,
                "should_retry": False,
                "exhausted": False,
            }

        entry["attempts"] += 1
        attempt = entry["attempts"]
        should_retry = False
        exhausted = False

        if success:
            entry["succeeded"] = True
            should_retry = False
            exhausted = False
        else:
            if attempt < entry["max_retries"]:
                should_retry = True
            else:
                exhausted = True

        result = {
            "retry_id": entry["retry_id"],
            "attempt": attempt,
            "should_retry": should_retry,
            "exhausted": exhausted,
        }

        logger.info(
            "attempt_recorded",
            pipeline_id=pipeline_id,
            step_name=step_name,
            attempt=attempt,
            success=success,
        )
        self._fire(
            "attempt_recorded",
            pipeline_id=pipeline_id,
            step_name=step_name,
            **result,
        )
        return result

    def get_attempt_count(self, pipeline_id: str, step_name: str) -> int:
        """Get current attempt count for a pipeline step."""
        steps = self._state.retries.get(pipeline_id, {})
        entry = steps.get(step_name)
        if entry is None:
            return 0
        return entry["attempts"]

    def should_retry(self, pipeline_id: str, step_name: str) -> bool:
        """Check if more retries are available for a pipeline step."""
        steps = self._state.retries.get(pipeline_id, {})
        entry = steps.get(step_name)
        if entry is None:
            return False
        if entry["succeeded"]:
            return False
        return entry["attempts"] < entry["max_retries"]

    def reset_retries(self, pipeline_id: str, step_name: str) -> bool:
        """Reset attempt counter for a pipeline step. Returns True if found."""
        steps = self._state.retries.get(pipeline_id, {})
        entry = steps.get(step_name)
        if entry is None:
            return False
        entry["attempts"] = 0
        entry["succeeded"] = False
        logger.info(
            "retries_reset",
            pipeline_id=pipeline_id,
            step_name=step_name,
        )
        self._fire(
            "retries_reset",
            pipeline_id=pipeline_id,
            step_name=step_name,
        )
        return True

    def get_retry_count(self, pipeline_id: str = "") -> int:
        """Count retry configs, optionally filtered by pipeline_id."""
        if pipeline_id:
            return len(self._state.retries.get(pipeline_id, {}))
        return sum(
            len(steps) for steps in self._state.retries.values()
        )

    def list_pipelines(self) -> list:
        """List all pipeline IDs with retry configs."""
        return sorted(self._state.retries.keys())

    def get_stats(self) -> dict:
        """Return service statistics."""
        total_configs = sum(
            len(steps) for steps in self._state.retries.values()
        )
        total_attempts = sum(
            entry["attempts"]
            for steps in self._state.retries.values()
            for entry in steps.values()
        )
        total_succeeded = sum(
            1
            for steps in self._state.retries.values()
            for entry in steps.values()
            if entry["succeeded"]
        )
        return {
            "total_configs": total_configs,
            "total_attempts": total_attempts,
            "total_succeeded": total_succeeded,
            "pipelines": len(self._state.retries),
            "max_entries": self._max_entries,
            "callbacks_registered": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.retries.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("service_reset")
