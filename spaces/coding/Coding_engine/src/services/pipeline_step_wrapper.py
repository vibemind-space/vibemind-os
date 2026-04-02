"""Pipeline step wrapper service for wrapping pipeline step execution with before/after logic."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepWrapperState:
    """State container for pipeline step wrapper."""
    entries: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0


class PipelineStepWrapper:
    """Wrap pipeline step execution with before/after logic (timing, logging, error handling)."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "psw-"

    def __init__(self):
        self._state = PipelineStepWrapperState()
        self._callbacks: Dict[str, Callable] = {}
        self._execution_history: List[Dict[str, Any]] = []

    def _generate_id(self, data: str) -> str:
        seq = self._state._seq
        self._state._seq += 1
        hash_val = hashlib.sha256(f"{data}{seq}".encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            entries = sorted(
                self._state.entries.items(),
                key=lambda x: x[1].get("created_at", 0)
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key, _ in entries[:to_remove]:
                del self._state.entries[key]

    def on_change(self, callback_id: str, callback: Callable) -> None:
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def _fire(self, event: str, data: Any = None) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def register_wrapper(self, pipeline_id: str, step_name: str, wrapper_type: str = "timing") -> str:
        wrapper_id = self._generate_id(f"{pipeline_id}:{step_name}:{wrapper_type}")
        entry = {
            "wrapper_id": wrapper_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "wrapper_type": wrapper_type,
            "created_at": time.time(),
        }
        self._state.entries[wrapper_id] = entry
        self._prune()
        self._fire("wrapper_registered", entry)
        return wrapper_id

    def wrap_execution(self, pipeline_id: str, step_name: str, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        wrappers = self.get_wrappers(pipeline_id, step_name)
        wrapper_type = wrappers[0]["wrapper_type"] if wrappers else "timing"

        result = None
        error = None
        start = time.time()

        if wrapper_type == "logging":
            logger.info(f"[psw] Executing {pipeline_id}/{step_name} args={args} kwargs={kwargs}")

        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            if wrapper_type == "error_handler":
                error = str(e)
                logger.error(f"[psw] Error in {pipeline_id}/{step_name}: {e}")
            else:
                error = str(e)
                raise
        finally:
            duration_ms = (time.time() - start) * 1000

        if wrapper_type == "logging":
            logger.info(f"[psw] Result {pipeline_id}/{step_name}: {result}")

        record = {
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "result": result,
            "duration_ms": duration_ms,
            "wrapper_type": wrapper_type,
            "error": error,
            "executed_at": time.time(),
        }
        self._execution_history.append(record)
        self._fire("execution_completed", record)
        return record

    def get_wrapper(self, wrapper_id: str) -> Optional[Dict[str, Any]]:
        return self._state.entries.get(wrapper_id)

    def get_wrappers(self, pipeline_id: str, step_name: str = "") -> List[Dict[str, Any]]:
        results = []
        for entry in self._state.entries.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            results.append(entry)
        return results

    def remove_wrapper(self, wrapper_id: str) -> bool:
        if wrapper_id in self._state.entries:
            del self._state.entries[wrapper_id]
            self._fire("wrapper_removed", {"wrapper_id": wrapper_id})
            return True
        return False

    def get_execution_history(self, pipeline_id: str, step_name: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        results = []
        for record in reversed(self._execution_history):
            if record["pipeline_id"] != pipeline_id:
                continue
            if step_name and record["step_name"] != step_name:
                continue
            results.append(record)
            if len(results) >= limit:
                break
        return results

    def get_wrapper_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> List[str]:
        pipelines = set()
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
        return sorted(pipelines)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_wrappers": len(self._state.entries),
            "total_executions": len(self._execution_history),
            "pipelines": len(self.list_pipelines()),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        self._state = PipelineStepWrapperState()
        self._execution_history.clear()
        self._callbacks.clear()
        self._fire("reset", None)
