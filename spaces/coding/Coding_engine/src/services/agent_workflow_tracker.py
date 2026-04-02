"""Agent Workflow Tracker -- tracks agent workflow progress and stages.

Provides stage-aware workflow tracking for agents.  Each workflow moves
through a sequence of named stages and can be advanced, completed, or
failed.  Supports per-agent queries, active-workflow filtering, and
observer callbacks on every mutation.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal dataclass
# ------------------------------------------------------------------

@dataclass
class WorkflowRecord:
    """Internal representation of a tracked workflow."""

    workflow_id: str = ""
    agent_id: str = ""
    workflow_name: str = ""
    stages: List[str] = field(default_factory=list)
    current_stage_index: int = 0
    status: str = "active"  # active | completed | failed
    failure_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowTracker:
    """Tracks agent workflow progress through named stages.

    Parameters
    ----------
    max_entries:
        Maximum number of workflow records to keep.  When the limit is
        reached the oldest quarter is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._workflows: Dict[str, WorkflowRecord] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative stats
        self._total_created: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_pruned: int = 0

        logger.debug("agent_workflow_tracker.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, workflow_name: str) -> str:
        self._seq += 1
        now = time.time()
        raw = f"{agent_id}-{workflow_name}-{now}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"awt-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._workflows) < self._max_entries:
            return
        # Remove oldest quarter by created_at
        sorted_ids = sorted(
            self._workflows,
            key=lambda wid: self._workflows[wid].created_at,
        )
        remove_count = max(1, len(sorted_ids) // 4)
        for wid in sorted_ids[:remove_count]:
            del self._workflows[wid]
            self._total_pruned += 1
        logger.debug("agent_workflow_tracker.pruned", removed=remove_count)

    # ------------------------------------------------------------------
    # Workflow CRUD
    # ------------------------------------------------------------------

    def create_workflow(
        self,
        agent_id: str,
        workflow_name: str,
        stages: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new workflow and return its ID (``awt-...``)."""
        self._prune_if_needed()

        effective_stages = list(stages) if stages else ["start", "end"]
        wid = self._generate_id(agent_id, workflow_name)

        record = WorkflowRecord(
            workflow_id=wid,
            agent_id=agent_id,
            workflow_name=workflow_name,
            stages=effective_stages,
            current_stage_index=0,
            status="active",
            failure_reason="",
            metadata=metadata or {},
            created_at=time.time(),
        )
        self._workflows[wid] = record
        self._total_created += 1

        logger.info(
            "agent_workflow_tracker.workflow_created",
            workflow_id=wid,
            agent_id=agent_id,
            workflow_name=workflow_name,
            stages=effective_stages,
        )
        self._fire("workflow_created", {"workflow_id": wid, "agent_id": agent_id})
        return wid

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Return workflow dict or ``None`` if not found."""
        rec = self._workflows.get(workflow_id)
        if rec is None:
            return None
        return {
            "workflow_id": rec.workflow_id,
            "agent_id": rec.agent_id,
            "workflow_name": rec.workflow_name,
            "stages": list(rec.stages),
            "current_stage": rec.stages[rec.current_stage_index] if rec.stages else None,
            "status": rec.status,
            "metadata": dict(rec.metadata),
            "created_at": rec.created_at,
        }

    # ------------------------------------------------------------------
    # Stage advancement
    # ------------------------------------------------------------------

    def advance_stage(self, workflow_id: str) -> bool:
        """Advance to the next stage.

        Returns ``True`` if the stage was advanced, ``False`` if the
        workflow is at the last stage, not found, or not active.
        """
        rec = self._workflows.get(workflow_id)
        if rec is None or rec.status != "active":
            return False
        if rec.current_stage_index >= len(rec.stages) - 1:
            return False

        rec.current_stage_index += 1
        new_stage = rec.stages[rec.current_stage_index]
        logger.info(
            "agent_workflow_tracker.stage_advanced",
            workflow_id=workflow_id,
            new_stage=new_stage,
        )
        self._fire("stage_advanced", {"workflow_id": workflow_id, "stage": new_stage})
        return True

    def get_current_stage(self, workflow_id: str) -> Optional[str]:
        """Return the current stage name, or ``None`` if not found."""
        rec = self._workflows.get(workflow_id)
        if rec is None:
            return None
        if not rec.stages:
            return None
        return rec.stages[rec.current_stage_index]

    # ------------------------------------------------------------------
    # Terminal states
    # ------------------------------------------------------------------

    def complete_workflow(self, workflow_id: str) -> bool:
        """Mark a workflow as completed.

        Returns ``False`` if the workflow is not found or already
        completed/failed.
        """
        rec = self._workflows.get(workflow_id)
        if rec is None or rec.status != "active":
            return False
        rec.status = "completed"
        self._total_completed += 1
        logger.info(
            "agent_workflow_tracker.workflow_completed",
            workflow_id=workflow_id,
        )
        self._fire("workflow_completed", {"workflow_id": workflow_id})
        return True

    def fail_workflow(self, workflow_id: str, reason: str = "") -> bool:
        """Mark a workflow as failed.

        Returns ``False`` if the workflow is not found.
        """
        rec = self._workflows.get(workflow_id)
        if rec is None:
            return False
        if rec.status != "active":
            return False
        rec.status = "failed"
        rec.failure_reason = reason
        self._total_failed += 1
        logger.info(
            "agent_workflow_tracker.workflow_failed",
            workflow_id=workflow_id,
            reason=reason,
        )
        self._fire("workflow_failed", {"workflow_id": workflow_id, "reason": reason})
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent_workflows(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all workflow dicts for *agent_id*."""
        return [
            self.get_workflow(rec.workflow_id)
            for rec in self._workflows.values()
            if rec.agent_id == agent_id
        ]

    def get_active_workflows(self) -> List[Dict[str, Any]]:
        """Return all workflow dicts with status ``'active'``."""
        return [
            self.get_workflow(rec.workflow_id)
            for rec in self._workflows.values()
            if rec.status == "active"
        ]

    def get_workflow_count(self, agent_id: Optional[str] = None) -> int:
        """Count workflows, optionally filtered by *agent_id*."""
        if agent_id is None:
            return len(self._workflows)
        return sum(1 for rec in self._workflows.values() if rec.agent_id == agent_id)

    def list_agents(self) -> List[str]:
        """Return a list of unique agent IDs that own workflows."""
        return list({rec.agent_id for rec in self._workflows.values()})

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register *callback* under *name*.  Overwrites if name exists."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove the callback registered under *name*."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("agent_workflow_tracker.callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        return {
            "current_workflows": len(self._workflows),
            "total_created": self._total_created,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_pruned": self._total_pruned,
            "active": sum(1 for r in self._workflows.values() if r.status == "active"),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all workflows, callbacks, and counters."""
        self._workflows.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_pruned = 0
        logger.debug("agent_workflow_tracker.reset")
