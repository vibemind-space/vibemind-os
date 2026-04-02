"""Pipeline step monitor: track step health with success/failure tracking and alerting thresholds."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepMonitorState:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineStepMonitor:
    """Monitor pipeline step health with success/failure tracking and alerting thresholds."""

    PREFIX = "psmo-"

    def __init__(self):
        self._state = PipelineStepMonitorState()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _fire(self, event: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.warning("Callback error: %s", exc)

    def on_change(self, callback_id: str, callback) -> None:
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        return self._callbacks.pop(callback_id, None) is not None

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= 10000:
            return
        sorted_keys = sorted(entries, key=lambda k: entries[k].get("updated_at", 0))
        to_remove = len(entries) - 10000
        for k in sorted_keys[:to_remove]:
            del entries[k]

    def _step_key(self, pipeline_id: str, step_name: str) -> str:
        return f"{pipeline_id}::{step_name}"

    def configure_monitor(self, pipeline_id: str, step_name: str,
                          failure_threshold: int = 3, window_seconds: float = 300.0) -> str:
        monitor_id = self._generate_id(f"{pipeline_id}:{step_name}")
        now = time.time()
        key = self._step_key(pipeline_id, step_name)
        entry = {
            "monitor_id": monitor_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "failure_threshold": failure_threshold,
            "window_seconds": window_seconds,
            "success_count": 0,
            "failure_count": 0,
            "consecutive_failures": 0,
            "last_error": "",
            "healthy": True,
            "created_at": now,
            "updated_at": now,
            "failures_in_window": [],
        }
        self._state.entries[monitor_id] = entry
        # Also index by key for quick lookup
        self._state.entries[f"_key_{key}"] = monitor_id
        self._prune()
        self._fire("monitor_configured", {"monitor_id": monitor_id, "pipeline_id": pipeline_id, "step_name": step_name})
        return monitor_id

    def _find_monitor(self, pipeline_id: str, step_name: str) -> dict | None:
        key = self._step_key(pipeline_id, step_name)
        monitor_id = self._state.entries.get(f"_key_{key}")
        if monitor_id and monitor_id in self._state.entries:
            return self._state.entries[monitor_id]
        return None

    def record_success(self, pipeline_id: str, step_name: str) -> bool:
        entry = self._find_monitor(pipeline_id, step_name)
        if entry is None:
            return False
        now = time.time()
        entry["success_count"] += 1
        entry["consecutive_failures"] = 0
        entry["healthy"] = True
        entry["updated_at"] = now
        self._fire("success_recorded", {"monitor_id": entry["monitor_id"], "pipeline_id": pipeline_id, "step_name": step_name})
        return True

    def record_failure(self, pipeline_id: str, step_name: str, error: str = "") -> dict:
        entry = self._find_monitor(pipeline_id, step_name)
        if entry is None:
            return {}
        now = time.time()
        entry["failure_count"] += 1
        entry["consecutive_failures"] += 1
        entry["last_error"] = error
        entry["updated_at"] = now

        # Track failures within the window
        window = entry["window_seconds"]
        entry["failures_in_window"].append(now)
        entry["failures_in_window"] = [t for t in entry["failures_in_window"] if now - t <= window]

        alert = entry["consecutive_failures"] >= entry["failure_threshold"]
        if alert:
            entry["healthy"] = False

        result = {
            "monitor_id": entry["monitor_id"],
            "consecutive_failures": entry["consecutive_failures"],
            "alert": alert,
        }
        self._fire("failure_recorded", result)
        return result

    def get_status(self, pipeline_id: str, step_name: str) -> dict:
        entry = self._find_monitor(pipeline_id, step_name)
        if entry is None:
            return {}
        total = entry["success_count"] + entry["failure_count"]
        success_rate = entry["success_count"] / total if total > 0 else 0.0
        return {
            "healthy": entry["healthy"],
            "success_count": entry["success_count"],
            "failure_count": entry["failure_count"],
            "success_rate": success_rate,
        }

    def get_monitor(self, monitor_id: str) -> dict | None:
        entry = self._state.entries.get(monitor_id)
        if entry is None or not isinstance(entry, dict) or "monitor_id" not in entry:
            return None
        return dict(entry)

    def get_monitors(self, pipeline_id: str) -> list:
        results = []
        for key, val in self._state.entries.items():
            if isinstance(val, dict) and val.get("pipeline_id") == pipeline_id and "monitor_id" in val:
                results.append(dict(val))
        return results

    def get_monitor_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return sum(1 for v in self._state.entries.values() if isinstance(v, dict) and "monitor_id" in v)
        return sum(1 for v in self._state.entries.values() if isinstance(v, dict) and v.get("pipeline_id") == pipeline_id and "monitor_id" in v)

    def list_pipelines(self) -> list:
        pipelines = set()
        for val in self._state.entries.values():
            if isinstance(val, dict) and "pipeline_id" in val and "monitor_id" in val:
                pipelines.add(val["pipeline_id"])
        return sorted(pipelines)

    def get_stats(self) -> dict:
        total = self.get_monitor_count()
        healthy = sum(
            1 for v in self._state.entries.values()
            if isinstance(v, dict) and "monitor_id" in v and v.get("healthy", False)
        )
        return {
            "total_monitors": total,
            "healthy_monitors": healthy,
            "unhealthy_monitors": total - healthy,
            "pipelines": len(self.list_pipelines()),
        }

    def reset(self) -> None:
        self._state = PipelineStepMonitorState()
        self._callbacks.clear()
        self._fire("reset", {})
