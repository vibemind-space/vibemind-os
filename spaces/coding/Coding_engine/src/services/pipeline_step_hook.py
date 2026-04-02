"""Pipeline step hook management — register pre/post hooks for pipeline steps.

Allows registering callable hooks that run before or after specific pipeline
steps. Hooks are keyed by pipeline ID, step name, and hook type (pre/post).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepHookState:
    """Internal state for the PipelineStepHook service."""

    hooks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepHook:
    """Manages pre/post hooks for pipeline steps.

    Hooks are callable functions registered to run before (pre) or after (post)
    a specific step within a pipeline.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepHookState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psh-{self._state._seq}-{id(self)}"
        return "psh-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict the oldest entries when the store exceeds max_entries."""
        if len(self._state.hooks) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._state.hooks.keys(),
            key=lambda hid: self._state.hooks[hid].get("created_at", 0),
        )
        while len(self._state.hooks) > self._max_entries:
            old_id = sorted_ids.pop(0)
            del self._state.hooks[old_id]

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def register_hook(
        self,
        pipeline_id: str,
        step_name: str,
        hook_type: str,
        hook_fn: Callable = None,
        label: str = "",
    ) -> str:
        """Register a pre or post hook for a pipeline step.

        Args:
            pipeline_id: Pipeline identifier.
            step_name: Step within the pipeline.
            hook_type: ``"pre"`` or ``"post"``.
            hook_fn: Callable to invoke. May be ``None``.
            label: Optional human-readable label.

        Returns:
            The generated hook ID (``psh-...``).
        """
        hook_id = self._generate_id()
        self._state.hooks[hook_id] = {
            "hook_id": hook_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "hook_type": hook_type,
            "hook_fn": hook_fn,
            "label": label,
            "created_at": time.time(),
        }
        self._prune_if_needed()
        logger.info("hook_registered", hook_id=hook_id, pipeline_id=pipeline_id,
                     step_name=step_name, hook_type=hook_type)
        self._fire("register_hook", {"hook_id": hook_id, "pipeline_id": pipeline_id,
                                      "step_name": step_name, "hook_type": hook_type})
        return hook_id

    def remove_hook(self, hook_id: str) -> bool:
        """Remove a hook by its ID. Returns True if removed."""
        if hook_id in self._state.hooks:
            info = self._state.hooks.pop(hook_id)
            logger.info("hook_removed", hook_id=hook_id)
            self._fire("remove_hook", {"hook_id": hook_id, "pipeline_id": info["pipeline_id"]})
            return True
        return False

    def get_hooks(
        self, pipeline_id: str, step_name: str = "", hook_type: str = ""
    ) -> List[Dict[str, Any]]:
        """Return hooks for a pipeline, optionally filtered by step and/or type."""
        results: List[Dict[str, Any]] = []
        for hook in self._state.hooks.values():
            if hook["pipeline_id"] != pipeline_id:
                continue
            if step_name and hook["step_name"] != step_name:
                continue
            if hook_type and hook["hook_type"] != hook_type:
                continue
            results.append(hook)
        return results

    def execute_hooks(
        self,
        pipeline_id: str,
        step_name: str,
        hook_type: str,
        context: dict = None,
    ) -> int:
        """Execute all matching hooks. Returns count of hooks executed."""
        if context is None:
            context = {}
        matching = self.get_hooks(pipeline_id, step_name, hook_type)
        count = 0
        for hook in matching:
            fn = hook.get("hook_fn")
            if fn is None:
                continue
            try:
                fn(context)
                count += 1
            except Exception:
                logger.exception("hook_execution_error", hook_id=hook["hook_id"])
                count += 1
        self._fire("execute_hooks", {
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "hook_type": hook_type,
            "executed": count,
        })
        return count

    def get_hook_count(self, pipeline_id: str = "") -> int:
        """Count hooks, optionally scoped to a pipeline."""
        if not pipeline_id:
            return len(self._state.hooks)
        return sum(
            1 for h in self._state.hooks.values() if h["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of distinct pipeline IDs that have hooks."""
        pids = {h["pipeline_id"] for h in self._state.hooks.values()}
        return sorted(pids)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics."""
        return {
            "total_hooks": len(self._state.hooks),
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._state.callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all hooks and callbacks, reset sequence counter."""
        self._state.hooks.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
        logger.info("pipeline_step_hook_reset")
