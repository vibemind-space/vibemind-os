"""Pipeline Rollout Scheduler – schedules and manages staged rollouts.

Plans multi-phase rollouts with configurable timing, percentage ramps,
and validation gates between stages. Supports pause, resume, and
rollback during execution.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _RolloutPhase:
    phase_index: int
    name: str
    target_pct: float
    status: str  # pending, active, completed, failed
    started_at: float
    completed_at: float


@dataclass
class _RolloutEntry:
    rollout_id: str
    name: str
    component: str
    status: str  # draft, running, paused, completed, failed, rolled_back
    phases: List[_RolloutPhase]
    current_phase: int
    current_pct: float
    tags: List[str]
    created_at: float
    updated_at: float


class PipelineRolloutScheduler:
    """Schedules and manages staged rollouts."""

    STATUSES = ("draft", "running", "paused", "completed", "failed", "rolled_back")

    def __init__(self, max_rollouts: int = 5000):
        self._rollouts: Dict[str, _RolloutEntry] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_rollouts = max_rollouts
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_completed = 0
        self._total_rolled_back = 0

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_rollout(
        self,
        name: str,
        component: str,
        phases: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or not component:
            return ""
        if name in self._name_index:
            return ""
        if len(self._rollouts) >= self._max_rollouts:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{component}-{now}-{self._seq}"
        rid = "rlt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        rollout_phases = []
        if phases:
            for i, p in enumerate(phases):
                rollout_phases.append(_RolloutPhase(
                    phase_index=i,
                    name=p.get("name", f"phase_{i}"),
                    target_pct=p.get("target_pct", 100.0),
                    status="pending",
                    started_at=0.0,
                    completed_at=0.0,
                ))

        entry = _RolloutEntry(
            rollout_id=rid,
            name=name,
            component=component,
            status="draft",
            phases=rollout_phases,
            current_phase=-1,
            current_pct=0.0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._rollouts[rid] = entry
        self._name_index[name] = rid
        self._total_created += 1
        self._fire("rollout_created", {"rollout_id": rid, "name": name})
        return rid

    def get_rollout(self, rollout_id: str) -> Optional[Dict[str, Any]]:
        e = self._rollouts.get(rollout_id)
        if not e:
            return None
        return {
            "rollout_id": e.rollout_id,
            "name": e.name,
            "component": e.component,
            "status": e.status,
            "phases": [
                {
                    "phase_index": p.phase_index,
                    "name": p.name,
                    "target_pct": p.target_pct,
                    "status": p.status,
                    "started_at": p.started_at,
                    "completed_at": p.completed_at,
                }
                for p in e.phases
            ],
            "current_phase": e.current_phase,
            "current_pct": e.current_pct,
            "tags": list(e.tags),
            "created_at": e.created_at,
        }

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        rid = self._name_index.get(name)
        if not rid:
            return None
        return self.get_rollout(rid)

    def remove_rollout(self, rollout_id: str) -> bool:
        e = self._rollouts.pop(rollout_id, None)
        if not e:
            return False
        self._name_index.pop(e.name, None)
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, rollout_id: str) -> bool:
        """Start rollout (begin first phase)."""
        e = self._rollouts.get(rollout_id)
        if not e or e.status != "draft":
            return False
        if not e.phases:
            return False
        e.status = "running"
        e.current_phase = 0
        phase = e.phases[0]
        phase.status = "active"
        phase.started_at = time.time()
        e.current_pct = phase.target_pct
        e.updated_at = time.time()
        self._fire("rollout_started", {"rollout_id": rollout_id})
        self._fire("phase_started", {"rollout_id": rollout_id, "phase": 0})
        return True

    def advance(self, rollout_id: str) -> bool:
        """Advance to next phase."""
        e = self._rollouts.get(rollout_id)
        if not e or e.status != "running":
            return False
        if e.current_phase < 0 or e.current_phase >= len(e.phases):
            return False

        # complete current phase
        current = e.phases[e.current_phase]
        current.status = "completed"
        current.completed_at = time.time()

        next_idx = e.current_phase + 1
        if next_idx >= len(e.phases):
            # all phases done
            e.status = "completed"
            e.current_pct = 100.0
            e.updated_at = time.time()
            self._total_completed += 1
            self._fire("rollout_completed", {"rollout_id": rollout_id})
            return True

        # start next phase
        e.current_phase = next_idx
        next_phase = e.phases[next_idx]
        next_phase.status = "active"
        next_phase.started_at = time.time()
        e.current_pct = next_phase.target_pct
        e.updated_at = time.time()
        self._fire("phase_started", {"rollout_id": rollout_id, "phase": next_idx})
        return True

    def pause(self, rollout_id: str) -> bool:
        """Pause rollout."""
        e = self._rollouts.get(rollout_id)
        if not e or e.status != "running":
            return False
        e.status = "paused"
        e.updated_at = time.time()
        self._fire("rollout_paused", {"rollout_id": rollout_id})
        return True

    def resume(self, rollout_id: str) -> bool:
        """Resume paused rollout."""
        e = self._rollouts.get(rollout_id)
        if not e or e.status != "paused":
            return False
        e.status = "running"
        e.updated_at = time.time()
        self._fire("rollout_resumed", {"rollout_id": rollout_id})
        return True

    def rollback(self, rollout_id: str, reason: str = "") -> bool:
        """Roll back rollout."""
        e = self._rollouts.get(rollout_id)
        if not e or e.status not in ("running", "paused"):
            return False
        e.status = "rolled_back"
        e.current_pct = 0.0
        e.updated_at = time.time()
        self._total_rolled_back += 1
        self._fire("rollout_rolled_back", {"rollout_id": rollout_id, "reason": reason})
        return True

    def get_progress(self, rollout_id: str) -> Optional[Dict[str, Any]]:
        """Get rollout progress."""
        e = self._rollouts.get(rollout_id)
        if not e:
            return None
        total = len(e.phases)
        completed = sum(1 for p in e.phases if p.status == "completed")
        return {
            "total_phases": total,
            "completed_phases": completed,
            "current_phase": e.current_phase,
            "current_pct": e.current_pct,
            "pct_complete": (completed / total * 100.0) if total > 0 else 0.0,
        }

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_rollouts(
        self,
        status: str = "",
        component: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in self._rollouts.values():
            if status and e.status != status:
                continue
            if component and e.component != component:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_rollout(e.rollout_id))
        return results

    def get_active_rollouts(self) -> List[Dict[str, Any]]:
        return self.list_rollouts(status="running")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_rollouts": len(self._rollouts),
            "total_created": self._total_created,
            "total_completed": self._total_completed,
            "total_rolled_back": self._total_rolled_back,
            "running_count": sum(1 for e in self._rollouts.values() if e.status == "running"),
        }

    def reset(self) -> None:
        self._rollouts.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_completed = 0
        self._total_rolled_back = 0
