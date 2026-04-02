"""Pipeline step fallback service.

Define fallback strategies for pipeline steps when primary execution fails.
Supports skip, default_value, retry, and custom fallback types.
"""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepFallbackState:
    entries: dict
    _seq: int = 0


class PipelineStepFallback:
    """Manages fallback strategies for pipeline steps when primary execution fails."""

    def __init__(self):
        self._state = PipelineStepFallbackState(entries={})
        self._callbacks = {}

    def on_change(self, name, cb):
        self._callbacks[name] = cb

    def remove_callback(self, name):
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action, detail_dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail_dict)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def _generate_id(self, data):
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "psf-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > 10000:
            sorted_entries = sorted(
                self._state.entries.items(), key=lambda x: x[1].get("timestamp", 0)
            )
            keep = sorted_entries[-5000:]
            self._state.entries = dict(keep)

    def register_fallback(self, pipeline_id, step_name, fallback_fn=None, fallback_type="skip", max_attempts=1):
        """Register a fallback for a pipeline step.

        Args:
            pipeline_id: The pipeline identifier.
            step_name: The step name within the pipeline.
            fallback_fn: Optional callable for 'custom' type fallbacks.
            fallback_type: One of 'skip', 'default_value', 'retry', 'custom'.
            max_attempts: Maximum retry attempts (for 'retry' type).

        Returns:
            The generated fallback ID.
        """
        fallback_id = self._generate_id(f"{pipeline_id}:{step_name}")
        entry = {
            "fallback_id": fallback_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "fallback_fn": fallback_fn,
            "fallback_type": fallback_type,
            "max_attempts": max_attempts,
            "default_value": None,
            "timestamp": time.time(),
        }
        self._state.entries[fallback_id] = entry
        self._prune()
        logger.info("Registered fallback %s for %s/%s", fallback_id, pipeline_id, step_name)
        self._fire("register_fallback", {"fallback_id": fallback_id, "pipeline_id": pipeline_id, "step_name": step_name})
        return fallback_id

    def execute_fallback(self, pipeline_id, step_name, error=None, context=None):
        """Execute the registered fallback for a failed step.

        Args:
            pipeline_id: The pipeline identifier.
            step_name: The step name within the pipeline.
            error: The error that caused the failure.
            context: Optional context dict for fallback execution.

        Returns:
            Dict with fallback_id, result, fallback_type, and attempts.
        """
        entry = None
        for e in self._state.entries.values():
            if e["pipeline_id"] == pipeline_id and e["step_name"] == step_name:
                entry = e
                break

        if entry is None:
            logger.warning("No fallback registered for %s/%s", pipeline_id, step_name)
            return {"fallback_id": None, "result": None, "fallback_type": None, "attempts": 0}

        fallback_type = entry["fallback_type"]
        fallback_id = entry["fallback_id"]
        result = None
        attempts = 0

        if fallback_type == "skip":
            result = None
            attempts = 1
        elif fallback_type == "default_value":
            result = entry.get("default_value")
            attempts = 1
        elif fallback_type == "retry":
            max_attempts = entry.get("max_attempts", 1)
            fallback_fn = entry.get("fallback_fn")
            for i in range(max_attempts):
                attempts += 1
                try:
                    if fallback_fn is not None:
                        result = fallback_fn(error, context)
                        break
                    else:
                        result = None
                        break
                except Exception as e:
                    logger.warning("Retry attempt %d failed: %s", attempts, e)
                    if attempts >= max_attempts:
                        result = None
        elif fallback_type == "custom":
            fallback_fn = entry.get("fallback_fn")
            attempts = 1
            if fallback_fn is not None:
                try:
                    result = fallback_fn(error, context)
                except Exception as e:
                    logger.error("Custom fallback failed: %s", e)
                    result = None
            else:
                result = None

        self._fire("execute_fallback", {"fallback_id": fallback_id, "pipeline_id": pipeline_id, "step_name": step_name, "fallback_type": fallback_type})
        return {"fallback_id": fallback_id, "result": result, "fallback_type": fallback_type, "attempts": attempts}

    def set_default_value(self, pipeline_id, step_name, value):
        """Set the default value for 'default_value' type fallbacks.

        Returns:
            True if a matching fallback was found and updated, False otherwise.
        """
        for entry in self._state.entries.values():
            if entry["pipeline_id"] == pipeline_id and entry["step_name"] == step_name:
                entry["default_value"] = value
                self._fire("set_default_value", {"pipeline_id": pipeline_id, "step_name": step_name, "value": value})
                return True
        return False

    def get_fallback(self, fallback_id):
        """Get a fallback entry by ID, or None if not found."""
        entry = self._state.entries.get(fallback_id)
        if entry is None:
            return None
        return {k: v for k, v in entry.items() if k != "fallback_fn"}

    def get_fallbacks(self, pipeline_id, step_name=""):
        """Get all fallbacks for a pipeline, optionally filtered by step name."""
        results = []
        for entry in self._state.entries.values():
            if entry["pipeline_id"] == pipeline_id:
                if step_name == "" or entry["step_name"] == step_name:
                    results.append({k: v for k, v in entry.items() if k != "fallback_fn"})
        return results

    def remove_fallback(self, fallback_id):
        """Remove a fallback by ID. Returns True if removed, False if not found."""
        if fallback_id in self._state.entries:
            del self._state.entries[fallback_id]
            self._fire("remove_fallback", {"fallback_id": fallback_id})
            return True
        return False

    def get_fallback_count(self, pipeline_id=""):
        """Get the count of fallbacks, optionally filtered by pipeline_id."""
        if pipeline_id == "":
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self):
        """List all unique pipeline IDs that have registered fallbacks."""
        return list(set(e["pipeline_id"] for e in self._state.entries.values()))

    def get_stats(self):
        """Return stats dict with counts."""
        pipelines = self.list_pipelines()
        type_counts = {}
        for entry in self._state.entries.values():
            ft = entry["fallback_type"]
            type_counts[ft] = type_counts.get(ft, 0) + 1
        return {
            "total_fallbacks": len(self._state.entries),
            "pipeline_count": len(pipelines),
            "type_counts": type_counts,
        }

    def reset(self):
        """Clear all state."""
        self._state = PipelineStepFallbackState(entries={})
        self._fire("reset", {})
