"""Pipeline Branch Router – conditional branch routing for pipelines.

Evaluates pipeline execution context against configured branch conditions
and routes to the appropriate target step. Supports per-pipeline branch
definitions with first-match semantics and match counting.
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
    routes: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineBranchRouter:
    """Conditional branch routing for autonomous pipelines."""

    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = _State()

    # ------------------------------------------------------------------
    # Branch management
    # ------------------------------------------------------------------

    def add_branch(
        self,
        pipeline_id: str,
        condition_key: str,
        condition_value: str,
        target_step: str,
    ) -> str:
        """Add a conditional branch route. Returns branch_id (pbr-...)."""
        if not pipeline_id or not condition_key or not target_step:
            return ""

        # Prune if at capacity
        total = sum(len(v) for v in self._state.routes.values())
        if total >= self.MAX_ENTRIES:
            logger.warning("max_entries_reached", total=total)
            return ""

        self._state._seq += 1
        now = time.time()
        raw = f"{pipeline_id}-{condition_key}-{condition_value}-{now}-{self._state._seq}"
        branch_id = "pbr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = {
            "branch_id": branch_id,
            "pipeline_id": pipeline_id,
            "condition_key": condition_key,
            "condition_value": condition_value,
            "target_step": target_step,
            "created_at": now,
            "match_count": 0,
        }

        if pipeline_id not in self._state.routes:
            self._state.routes[pipeline_id] = []
        self._state.routes[pipeline_id].append(entry)

        logger.info("branch_added", branch_id=branch_id, pipeline_id=pipeline_id)
        self._fire("branch_added", branch_id=branch_id, pipeline_id=pipeline_id)
        return branch_id

    def route(self, pipeline_id: str, context: dict) -> str:
        """Evaluate context against branches; return first matching target_step or ''."""
        branches = self._state.routes.get(pipeline_id, [])
        for branch in branches:
            if context.get(branch["condition_key"]) == branch["condition_value"]:
                branch["match_count"] += 1
                logger.info(
                    "branch_matched",
                    branch_id=branch["branch_id"],
                    target_step=branch["target_step"],
                )
                self._fire(
                    "branch_matched",
                    branch_id=branch["branch_id"],
                    pipeline_id=pipeline_id,
                    target_step=branch["target_step"],
                )
                return branch["target_step"]
        return ""

    def get_branches(self, pipeline_id: str) -> list:
        """Get all branch definitions for a pipeline."""
        branches = self._state.routes.get(pipeline_id, [])
        return [dict(b) for b in branches]

    def remove_branch(self, branch_id: str) -> bool:
        """Remove a branch by ID."""
        for pipeline_id, branches in self._state.routes.items():
            for i, branch in enumerate(branches):
                if branch["branch_id"] == branch_id:
                    branches.pop(i)
                    if not branches:
                        del self._state.routes[pipeline_id]
                    logger.info("branch_removed", branch_id=branch_id)
                    self._fire("branch_removed", branch_id=branch_id, pipeline_id=pipeline_id)
                    return True
        return False

    def get_branch_count(self, pipeline_id: str = "") -> int:
        """Count branches, optionally filtered by pipeline_id."""
        if pipeline_id:
            return len(self._state.routes.get(pipeline_id, []))
        return sum(len(v) for v in self._state.routes.values())

    def list_pipelines(self) -> list:
        """Return list of pipeline IDs."""
        return list(self._state.routes.keys())

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return stats."""
        total_branches = sum(len(v) for v in self._state.routes.values())
        total_matches = sum(
            b["match_count"]
            for branches in self._state.routes.values()
            for b in branches
        )
        return {
            "total_branches": total_branches,
            "total_pipelines": len(self._state.routes),
            "total_matches": total_matches,
            "callbacks": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.routes.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("state_reset")
