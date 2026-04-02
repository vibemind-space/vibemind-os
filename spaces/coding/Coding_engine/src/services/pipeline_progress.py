"""
Pipeline Progress Tracker — Real-time progress monitoring with ETA estimation.

Tracks pipeline phase execution, individual agent tasks, and provides:
- Phase-level progress (planning → generation → testing → integration)
- Per-agent task tracking with completion percentages
- ETA estimation using exponential moving average of phase durations
- Event bus integration for real-time progress broadcasts
- Historical data for improving future estimates

Usage::

    tracker = PipelineProgressTracker(event_bus)
    tracker.start_pipeline("my-project", total_phases=5)

    tracker.start_phase("planning", estimated_tasks=3)
    tracker.complete_task("planning", "analyze_requirements")
    tracker.complete_task("planning", "generate_plan")
    tracker.complete_task("planning", "validate_plan")
    tracker.complete_phase("planning")

    progress = tracker.get_progress()
    # {'overall_pct': 20.0, 'eta_seconds': 240, 'current_phase': 'generation', ...}
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskProgress:
    """Progress of a single task within a phase."""
    task_id: str
    description: str = ""
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        return None


@dataclass
class PhaseProgress:
    """Progress of a pipeline phase."""
    phase_id: str
    label: str = ""
    status: PhaseStatus = PhaseStatus.PENDING
    estimated_tasks: int = 0
    tasks: Dict[str, TaskProgress] = field(default_factory=dict)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.tasks.values() if t.status == PhaseStatus.COMPLETED)

    @property
    def task_count(self) -> int:
        return max(self.estimated_tasks, len(self.tasks))

    @property
    def completion_pct(self) -> float:
        total = self.task_count
        if total == 0:
            return 100.0 if self.status == PhaseStatus.COMPLETED else 0.0
        return (self.completed_tasks / total) * 100.0

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        if self.started_at:
            return int((time.time() - self.started_at) * 1000)
        return None

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "label": self.label,
            "status": self.status.value,
            "completion_pct": round(self.completion_pct, 1),
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.task_count,
            "duration_ms": self.duration_ms,
            "tasks": {
                tid: {
                    "task_id": t.task_id,
                    "status": t.status.value,
                    "duration_ms": t.duration_ms,
                }
                for tid, t in self.tasks.items()
            },
        }


@dataclass
class ETAEstimator:
    """
    ETA estimator using exponential moving average of phase durations.

    Maintains historical phase durations and uses EMA to predict
    remaining time. Alpha controls how much weight recent observations get.
    """
    alpha: float = 0.3  # EMA smoothing factor (higher = more reactive)
    _history: Dict[str, List[float]] = field(default_factory=dict)
    _ema: Dict[str, float] = field(default_factory=dict)

    def record_phase_duration(self, phase_id: str, duration_seconds: float):
        """Record actual phase duration for future estimates."""
        if phase_id not in self._history:
            self._history[phase_id] = []
        self._history[phase_id].append(duration_seconds)

        # Update EMA
        if phase_id not in self._ema:
            self._ema[phase_id] = duration_seconds
        else:
            self._ema[phase_id] = (
                self.alpha * duration_seconds + (1 - self.alpha) * self._ema[phase_id]
            )

    def estimate_phase_duration(self, phase_id: str, default_seconds: float = 60.0) -> float:
        """Estimate duration for a phase based on history."""
        if phase_id in self._ema:
            return self._ema[phase_id]
        return default_seconds

    def estimate_remaining(
        self,
        remaining_phases: List[str],
        current_phase_id: Optional[str] = None,
        current_phase_pct: float = 0.0,
        default_seconds: float = 60.0,
    ) -> float:
        """Estimate total remaining seconds."""
        total = 0.0

        # Remaining time in current phase
        if current_phase_id:
            phase_est = self.estimate_phase_duration(current_phase_id, default_seconds)
            remaining_pct = max(0.0, 100.0 - current_phase_pct) / 100.0
            total += phase_est * remaining_pct

        # Full duration of upcoming phases
        for phase_id in remaining_phases:
            total += self.estimate_phase_duration(phase_id, default_seconds)

        return total

    def to_dict(self) -> dict:
        return {
            "ema_estimates": {k: round(v, 2) for k, v in self._ema.items()},
            "history_counts": {k: len(v) for k, v in self._history.items()},
        }


class PipelineProgressTracker:
    """
    Tracks overall pipeline progress with phase and task granularity.

    Integrates with EventBus to broadcast progress updates in real-time.
    """

    def __init__(self, event_bus=None, default_phase_seconds: float = 60.0):
        self.event_bus = event_bus
        self.default_phase_seconds = default_phase_seconds
        self.eta_estimator = ETAEstimator()

        # Pipeline state
        self.project_name: Optional[str] = None
        self.pipeline_started_at: Optional[float] = None
        self.pipeline_completed_at: Optional[float] = None
        self.phases: Dict[str, PhaseProgress] = {}
        self.phase_order: List[str] = []
        self._current_phase: Optional[str] = None

        self.logger = logger.bind(component="progress_tracker")

    def start_pipeline(self, project_name: str, phases: Optional[List[str]] = None):
        """Start tracking a new pipeline run."""
        self.project_name = project_name
        self.pipeline_started_at = time.time()
        self.pipeline_completed_at = None
        self.phases = {}
        self.phase_order = phases or []
        self._current_phase = None

        # Pre-create phase entries
        for phase_id in self.phase_order:
            self.phases[phase_id] = PhaseProgress(
                phase_id=phase_id,
                label=phase_id.replace("_", " ").title(),
            )

        self.logger.info("pipeline_started", project=project_name, phases=len(self.phase_order))
        self._broadcast_progress()

    def start_phase(self, phase_id: str, estimated_tasks: int = 0, label: str = ""):
        """Mark a phase as started."""
        if phase_id not in self.phases:
            self.phases[phase_id] = PhaseProgress(phase_id=phase_id)
            if phase_id not in self.phase_order:
                self.phase_order.append(phase_id)

        phase = self.phases[phase_id]
        phase.status = PhaseStatus.RUNNING
        phase.started_at = time.time()
        phase.estimated_tasks = estimated_tasks
        if label:
            phase.label = label

        self._current_phase = phase_id
        self.logger.info("phase_started", phase=phase_id, estimated_tasks=estimated_tasks)
        self._broadcast_progress()

    def start_task(self, phase_id: str, task_id: str, description: str = ""):
        """Mark a task as started within a phase."""
        phase = self.phases.get(phase_id)
        if not phase:
            return

        task = TaskProgress(
            task_id=task_id,
            description=description,
            status=PhaseStatus.RUNNING,
            started_at=time.time(),
        )
        phase.tasks[task_id] = task

    def complete_task(self, phase_id: str, task_id: str):
        """Mark a task as completed."""
        phase = self.phases.get(phase_id)
        if not phase:
            return

        if task_id not in phase.tasks:
            # Auto-create if task wasn't explicitly started
            phase.tasks[task_id] = TaskProgress(
                task_id=task_id,
                status=PhaseStatus.COMPLETED,
                completed_at=time.time(),
            )
        else:
            task = phase.tasks[task_id]
            task.status = PhaseStatus.COMPLETED
            task.completed_at = time.time()

        self._broadcast_progress()

    def fail_task(self, phase_id: str, task_id: str, error: str = ""):
        """Mark a task as failed."""
        phase = self.phases.get(phase_id)
        if not phase:
            return

        if task_id in phase.tasks:
            task = phase.tasks[task_id]
            task.status = PhaseStatus.FAILED
            task.completed_at = time.time()
            task.error = error

    def complete_phase(self, phase_id: str):
        """Mark a phase as completed."""
        phase = self.phases.get(phase_id)
        if not phase:
            return

        phase.status = PhaseStatus.COMPLETED
        phase.completed_at = time.time()

        # Record duration for ETA estimation
        if phase.started_at:
            duration = phase.completed_at - phase.started_at
            self.eta_estimator.record_phase_duration(phase_id, duration)

        self.logger.info(
            "phase_completed",
            phase=phase_id,
            duration_ms=phase.duration_ms,
            tasks=phase.completed_tasks,
        )
        self._broadcast_progress()

    def fail_phase(self, phase_id: str, error: str = ""):
        """Mark a phase as failed."""
        phase = self.phases.get(phase_id)
        if not phase:
            return

        phase.status = PhaseStatus.FAILED
        phase.completed_at = time.time()
        phase.error = error

        if phase.started_at:
            duration = phase.completed_at - phase.started_at
            self.eta_estimator.record_phase_duration(phase_id, duration)

        self._broadcast_progress()

    def skip_phase(self, phase_id: str):
        """Mark a phase as skipped."""
        phase = self.phases.get(phase_id)
        if not phase:
            return
        phase.status = PhaseStatus.SKIPPED
        self._broadcast_progress()

    def complete_pipeline(self):
        """Mark the entire pipeline as complete."""
        self.pipeline_completed_at = time.time()
        self._current_phase = None
        self.logger.info(
            "pipeline_completed",
            project=self.project_name,
            total_duration_ms=self.total_duration_ms,
        )
        self._broadcast_progress()

    # ------------------------------------------------------------------
    # Progress queries
    # ------------------------------------------------------------------

    @property
    def total_duration_ms(self) -> Optional[int]:
        if not self.pipeline_started_at:
            return None
        end = self.pipeline_completed_at or time.time()
        return int((end - self.pipeline_started_at) * 1000)

    @property
    def overall_pct(self) -> float:
        """Overall pipeline completion percentage."""
        if not self.phase_order:
            return 0.0

        total_phases = len(self.phase_order)
        completed_phases = sum(
            1 for pid in self.phase_order
            if self.phases.get(pid) and self.phases[pid].status in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED)
        )

        # Add partial credit for current running phase
        current_partial = 0.0
        if self._current_phase and self._current_phase in self.phases:
            current = self.phases[self._current_phase]
            if current.status == PhaseStatus.RUNNING:
                current_partial = current.completion_pct / 100.0

        return ((completed_phases + current_partial) / total_phases) * 100.0

    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimated seconds remaining."""
        if not self.phase_order or not self._current_phase:
            return None

        # Find remaining phases after current
        try:
            current_idx = self.phase_order.index(self._current_phase)
        except ValueError:
            return None

        remaining_phase_ids = [
            pid for pid in self.phase_order[current_idx + 1:]
            if self.phases.get(pid) and self.phases[pid].status == PhaseStatus.PENDING
        ]

        current_pct = 0.0
        if self._current_phase in self.phases:
            current_pct = self.phases[self._current_phase].completion_pct

        return self.eta_estimator.estimate_remaining(
            remaining_phases=remaining_phase_ids,
            current_phase_id=self._current_phase,
            current_phase_pct=current_pct,
            default_seconds=self.default_phase_seconds,
        )

    def get_progress(self) -> dict:
        """Get full progress snapshot."""
        return {
            "project_name": self.project_name,
            "overall_pct": round(self.overall_pct, 1),
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds is not None else None,
            "current_phase": self._current_phase,
            "total_duration_ms": self.total_duration_ms,
            "phases": {pid: self.phases[pid].to_dict() for pid in self.phase_order if pid in self.phases},
            "eta_estimator": self.eta_estimator.to_dict(),
        }

    def get_phase_progress(self, phase_id: str) -> Optional[dict]:
        """Get progress for a specific phase."""
        phase = self.phases.get(phase_id)
        if not phase:
            return None
        return phase.to_dict()

    # ------------------------------------------------------------------
    # Event broadcasting
    # ------------------------------------------------------------------

    def _broadcast_progress(self):
        """Broadcast progress update via event bus."""
        if not self.event_bus:
            return

        try:
            from src.mind.event_bus import Event, EventType
            event = Event(
                type=EventType.PIPELINE_STARTED,  # Reuse closest event type
                source="progress_tracker",
                data={
                    "action": "progress_update",
                    "progress": self.get_progress(),
                },
            )
            # EventBus.publish is async, use fire-and-forget
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.event_bus.publish(event))
            except RuntimeError:
                pass  # No event loop running
        except Exception:
            pass  # Don't let broadcast failures affect tracking
