"""Configure and track timeouts for pipeline steps."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepTimeoutState:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineStepTimeout:
    PREFIX = "pst-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepTimeoutState()
        self._callbacks: Dict[str, Callable] = {}
        self._timers: Dict[str, float] = {}

    # ── ID generation ──────────────────────────────────────────────
    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Callbacks ──────────────────────────────────────────────────
    def on_change(self, name: str, cb: Callable) -> None:
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Any = None) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("Callback error for action=%s", action)

    # ── Pruning ────────────────────────────────────────────────────
    def _prune(self) -> None:
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]

    # ── Core API ───────────────────────────────────────────────────
    def set_timeout(self, pipeline_id: str, step_name: str, timeout_seconds: float) -> str:
        tid = self._generate_id(f"{pipeline_id}:{step_name}")
        entry = {
            "timeout_id": tid,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "timeout_seconds": timeout_seconds,
            "created_at": time.time(),
        }
        self._state.entries[tid] = entry
        self._prune()
        self._fire("set_timeout", entry)
        return tid

    def start_timer(self, pipeline_id: str, step_name: str) -> bool:
        key = f"{pipeline_id}:{step_name}"
        self._timers[key] = time.time()
        self._fire("start_timer", {"pipeline_id": pipeline_id, "step_name": step_name})
        return True

    def check_timeout(self, pipeline_id: str, step_name: str) -> dict:
        key = f"{pipeline_id}:{step_name}"
        start = self._timers.get(key)
        if start is None:
            return {"timed_out": False, "elapsed": 0.0, "remaining": 0.0}

        elapsed = time.time() - start
        timeout_seconds = self._find_timeout_seconds(pipeline_id, step_name)
        if timeout_seconds is None:
            return {"timed_out": False, "elapsed": elapsed, "remaining": 0.0}

        remaining = max(0.0, timeout_seconds - elapsed)
        timed_out = elapsed >= timeout_seconds
        return {"timed_out": timed_out, "elapsed": elapsed, "remaining": remaining}

    def stop_timer(self, pipeline_id: str, step_name: str) -> dict:
        key = f"{pipeline_id}:{step_name}"
        start = self._timers.pop(key, None)
        if start is None:
            return {"elapsed": 0.0, "timed_out": False}

        elapsed = time.time() - start
        timeout_seconds = self._find_timeout_seconds(pipeline_id, step_name)
        timed_out = elapsed >= timeout_seconds if timeout_seconds is not None else False
        result = {"elapsed": elapsed, "timed_out": timed_out}
        self._fire("stop_timer", {"pipeline_id": pipeline_id, "step_name": step_name, **result})
        return result

    def get_timeout(self, timeout_id: str) -> Optional[dict]:
        return self._state.entries.get(timeout_id)

    def get_timeouts(self, pipeline_id: str) -> list:
        return [e for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id]

    def get_timeout_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> list:
        return list({e["pipeline_id"] for e in self._state.entries.values()})

    # ── Helpers ────────────────────────────────────────────────────
    def _find_timeout_seconds(self, pipeline_id: str, step_name: str) -> Optional[float]:
        for e in reversed(list(self._state.entries.values())):
            if e["pipeline_id"] == pipeline_id and e["step_name"] == step_name:
                return e["timeout_seconds"]
        return None

    def get_stats(self) -> dict:
        return {
            "total_entries": len(self._state.entries),
            "active_timers": len(self._timers),
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._state = PipelineStepTimeoutState()
        self._timers.clear()
        self._fire("reset", None)
