"""Pipeline Step Registry -- registers and manages reusable pipeline step definitions.

Provides step registration with metadata, execution with stats tracking,
sequential composition of steps, and tag-based organization.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _StepEntry:
    """Internal representation of a registered pipeline step."""
    step_id: str
    name: str
    handler_fn: Callable
    description: str
    tags: List[str]
    input_schema: Optional[Dict[str, Any]]
    output_schema: Optional[Dict[str, Any]]
    created_at: float


@dataclass
class _ExecutionStats:
    """Tracks per-step execution statistics."""
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Step Registry
# ---------------------------------------------------------------------------

class PipelineStepRegistry:
    """Registers and manages reusable pipeline step definitions with metadata.

    Steps are callable units that accept a context dict and return a result.
    Steps can be composed into sequential pipelines and tracked with
    per-step execution statistics.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._steps: Dict[str, _StepEntry] = {}       # step_id -> entry
        self._by_name: Dict[str, str] = {}             # name -> step_id
        self._exec_stats: Dict[str, _ExecutionStats] = {}  # name -> stats
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # counters
        self._total_registered = 0
        self._total_executed = 0
        self._total_removed = 0
        self._total_composed = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        """Generate a collision-free ID with prefix psr2-."""
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"psr2-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding max_entries."""
        while len(self._steps) > self._max_entries:
            oldest_id = min(self._steps, key=lambda k: self._steps[k].created_at)
            entry = self._steps.pop(oldest_id)
            if entry.name in self._by_name and self._by_name[entry.name] == oldest_id:
                del self._by_name[entry.name]
            if entry.name in self._exec_stats:
                del self._exec_stats[entry.name]

    # ------------------------------------------------------------------
    # register_step
    # ------------------------------------------------------------------

    def register_step(
        self,
        name: str,
        handler_fn: Callable,
        description: str = "",
        tags: Optional[List[str]] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new pipeline step definition.

        Args:
            name: Unique step name.
            handler_fn: Callable that accepts a context dict and returns a result.
            description: Human-readable description of the step.
            tags: Optional list of tags for categorization.
            input_schema: Optional dict describing expected input fields.
            output_schema: Optional dict describing output fields.

        Returns:
            Step ID string (psr2-...), or "" if a step with this name
            already exists.
        """
        if name in self._by_name:
            logger.warning("step_duplicate_name", name=name)
            return ""

        step_id = self._generate_id(name)
        now = time.time()

        entry = _StepEntry(
            step_id=step_id,
            name=name,
            handler_fn=handler_fn,
            description=description,
            tags=list(tags) if tags else [],
            input_schema=dict(input_schema) if input_schema else None,
            output_schema=dict(output_schema) if output_schema else None,
            created_at=now,
        )

        self._steps[step_id] = entry
        self._by_name[name] = step_id
        self._exec_stats[name] = _ExecutionStats()
        self._total_registered += 1

        self._prune()

        logger.info("step_registered", step_id=step_id, name=name)
        self._fire("register", {"step_id": step_id, "name": name})

        return step_id

    # ------------------------------------------------------------------
    # get_step
    # ------------------------------------------------------------------

    def get_step(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a step definition by name.

        Args:
            name: Name of the step.

        Returns:
            Step dict or None if not found.
        """
        step_id = self._by_name.get(name)
        if step_id is None:
            return None
        entry = self._steps.get(step_id)
        if entry is None:
            return None
        return self._to_dict(entry)

    # ------------------------------------------------------------------
    # execute_step
    # ------------------------------------------------------------------

    def execute_step(
        self, name: str, context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a registered step with the given context.

        Args:
            name: Name of the step to execute.
            context: Input context dict passed to the handler.

        Returns:
            Dict with keys:
                success (bool): Whether execution succeeded.
                result: Return value from handler on success, None on failure.
                error (str): Error message on failure, empty on success.
        """
        if context is None:
            context = {}

        step_id = self._by_name.get(name)
        if step_id is None:
            return {"success": False, "result": None, "error": f"Step '{name}' not found"}

        entry = self._steps.get(step_id)
        if entry is None:
            return {"success": False, "result": None, "error": f"Step '{name}' not found"}

        stats = self._exec_stats.setdefault(name, _ExecutionStats())
        stats.call_count += 1
        self._total_executed += 1

        start = time.time()
        try:
            result = entry.handler_fn(context)
            duration = time.time() - start
            stats.success_count += 1
            stats.total_duration += duration

            logger.info("step_executed", name=name, duration=duration)
            self._fire("execute", {"name": name, "success": True, "duration": duration})

            return {"success": True, "result": result, "error": ""}
        except Exception as exc:
            duration = time.time() - start
            stats.failure_count += 1
            stats.total_duration += duration
            error_msg = str(exc)

            logger.error("step_execution_failed", name=name, error=error_msg)
            self._fire("execute", {"name": name, "success": False, "error": error_msg})

            return {"success": False, "result": None, "error": error_msg}

    # ------------------------------------------------------------------
    # list_steps
    # ------------------------------------------------------------------

    def list_steps(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all registered steps, optionally filtered by tag.

        Args:
            tag: If provided, only return steps containing this tag.

        Returns:
            List of step dicts sorted by creation time (newest first).
        """
        results: List[Dict[str, Any]] = []
        for entry in sorted(self._steps.values(), key=lambda e: e.created_at, reverse=True):
            if tag is not None and tag not in entry.tags:
                continue
            results.append(self._to_dict(entry))
        return results

    # ------------------------------------------------------------------
    # remove_step
    # ------------------------------------------------------------------

    def remove_step(self, name: str) -> bool:
        """Remove a step by name.

        Args:
            name: Name of the step to remove.

        Returns:
            True if removed, False if not found.
        """
        step_id = self._by_name.pop(name, None)
        if step_id is None:
            return False

        entry = self._steps.pop(step_id, None)
        if name in self._exec_stats:
            del self._exec_stats[name]

        self._total_removed += 1

        logger.info("step_removed", name=name, step_id=step_id)
        self._fire("remove", {"name": name, "step_id": step_id})

        return True

    # ------------------------------------------------------------------
    # get_execution_stats
    # ------------------------------------------------------------------

    def get_execution_stats(self, name: str) -> Dict[str, Any]:
        """Get execution statistics for a specific step.

        Args:
            name: Name of the step.

        Returns:
            Dict with call_count, success_count, failure_count, avg_duration.
            Returns zeroed stats if step not found.
        """
        stats = self._exec_stats.get(name)
        if stats is None:
            return {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "avg_duration": 0.0,
            }

        avg_duration = 0.0
        if stats.call_count > 0:
            avg_duration = stats.total_duration / stats.call_count

        return {
            "call_count": stats.call_count,
            "success_count": stats.success_count,
            "failure_count": stats.failure_count,
            "avg_duration": avg_duration,
        }

    # ------------------------------------------------------------------
    # compose
    # ------------------------------------------------------------------

    def compose(self, step_names: List[str], composed_name: str) -> str:
        """Create a new step that runs multiple steps in sequence.

        Each step receives the context dict. The context is updated with
        each step's result under the key ``_results`` (a list) so that
        later steps can access earlier outputs.

        Args:
            step_names: Ordered list of existing step names to compose.
            composed_name: Name for the new composed step.

        Returns:
            Step ID of the composed step, or "" if composed_name already
            exists or any referenced step is not found.
        """
        if composed_name in self._by_name:
            logger.warning("compose_duplicate_name", name=composed_name)
            return ""

        # Validate all referenced steps exist
        for sn in step_names:
            if sn not in self._by_name:
                logger.warning("compose_missing_step", missing=sn, composed=composed_name)
                return ""

        # Capture the names for the closure
        captured_names = list(step_names)

        def _composed_handler(context: Dict[str, Any]) -> Dict[str, Any]:
            results: List[Any] = []
            ctx = dict(context)
            ctx["_results"] = results

            for sn in captured_names:
                outcome = self.execute_step(sn, ctx)
                if not outcome["success"]:
                    return {
                        "success": False,
                        "failed_step": sn,
                        "error": outcome["error"],
                        "partial_results": results,
                    }
                results.append(outcome["result"])

            return {
                "success": True,
                "results": results,
            }

        step_id = self.register_step(
            name=composed_name,
            handler_fn=_composed_handler,
            description=f"Composed step: {' -> '.join(captured_names)}",
            tags=["composed"],
        )

        if step_id:
            self._total_composed += 1
            logger.info("step_composed", step_id=step_id, steps=captured_names)
            self._fire("compose", {"step_id": step_id, "steps": captured_names})

        return step_id

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics.

        Returns:
            Dict with counters for registrations, executions, removals,
            compositions, current step count, callbacks, etc.
        """
        return {
            "total_registered": self._total_registered,
            "total_executed": self._total_executed,
            "total_removed": self._total_removed,
            "total_composed": self._total_composed,
            "current_steps": len(self._steps),
            "unique_names": len(self._by_name),
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all steps, execution stats, callbacks, and counters."""
        self._steps.clear()
        self._by_name.clear()
        self._exec_stats.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_executed = 0
        self._total_removed = 0
        self._total_composed = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(entry: _StepEntry) -> Dict[str, Any]:
        """Convert a step entry to a plain dict for external consumption."""
        return {
            "step_id": entry.step_id,
            "name": entry.name,
            "description": entry.description,
            "tags": list(entry.tags),
            "input_schema": dict(entry.input_schema) if entry.input_schema else None,
            "output_schema": dict(entry.output_schema) if entry.output_schema else None,
            "created_at": entry.created_at,
        }
