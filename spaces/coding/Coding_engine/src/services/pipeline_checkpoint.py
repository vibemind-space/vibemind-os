"""
Pipeline Checkpoint/Resume — Crash recovery for long-running pipeline runs.

Saves pipeline state to disk at key milestones so that if the process
crashes, it can be resumed from the last checkpoint instead of restarting
from scratch.

Checkpoints are saved as JSON files in:
    <project_dir>/.coding_engine/checkpoints/

Each checkpoint captures:
- Current pipeline phase
- Completed agents/tasks
- SharedState snapshot
- Convergence metrics
- Event history (last N events)
- Timestamp and trace ID

Usage::

    cp = PipelineCheckpointer(project_dir, shared_state, event_bus)

    # Save checkpoint at key milestones
    await cp.save("code_generation_complete", phase="generate")

    # On restart, check if a checkpoint exists
    last = cp.load_latest()
    if last:
        # Resume from checkpoint
        shared_state.restore(last.shared_state_snapshot)
        start_from_phase = last.phase
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState

logger = structlog.get_logger(__name__)


CHECKPOINT_DIR_NAME = ".coding_engine/checkpoints"
MAX_CHECKPOINTS = 20  # Keep last N checkpoints per project


@dataclass
class PipelineCheckpoint:
    """A serializable snapshot of pipeline state."""
    checkpoint_id: str
    timestamp: str
    trace_id: Optional[str]
    phase: str
    milestone: str
    completed_agents: List[str]
    shared_state_snapshot: Dict[str, Any]
    convergence_metrics: Dict[str, Any]
    recent_events: List[Dict]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineCheckpoint":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PipelineCheckpointer:
    """
    Manages pipeline checkpoints for crash recovery.

    Checkpoints are saved as numbered JSON files in the project's
    .coding_engine/checkpoints/ directory.
    """

    def __init__(
        self,
        project_dir: str,
        shared_state: SharedState,
        event_bus: EventBus,
    ):
        self.project_dir = Path(project_dir)
        self.shared_state = shared_state
        self.event_bus = event_bus
        self._checkpoint_dir = self.project_dir / CHECKPOINT_DIR_NAME
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_count = 0

        # Subscribe to pipeline events for auto-checkpointing
        self._subscribe()

    def _subscribe(self):
        """Subscribe to events that trigger automatic checkpoints."""
        auto_checkpoint_events = [
            EventType.PIPELINE_PHASE_CHANGED,
            EventType.TREEQUEST_VERIFICATION_COMPLETE,
            EventType.EVOLUTION_APPLIED,
            EventType.BUILD_SUCCEEDED,
        ]
        for et in auto_checkpoint_events:
            self.event_bus.subscribe(et, self._on_auto_checkpoint_event)

    async def _on_auto_checkpoint_event(self, event: Event):
        """Auto-save checkpoint on significant events."""
        phase = event.data.get("phase", event.type.value)
        milestone = f"auto:{event.type.value}"
        await self.save(milestone=milestone, phase=phase)

    async def save(
        self,
        milestone: str,
        phase: str = "unknown",
        metadata: Optional[Dict] = None,
    ) -> PipelineCheckpoint:
        """
        Save a checkpoint to disk.

        Args:
            milestone: Human-readable description of why this checkpoint was saved
            phase: Current pipeline phase name
            metadata: Additional metadata to store
        """
        self._checkpoint_count += 1
        checkpoint_id = f"cp-{self._checkpoint_count:04d}-{int(time.time())}"
        trace_id = self.shared_state.get("current_trace_id")

        # Snapshot shared state (only serializable keys)
        state_snapshot = {}
        custom = getattr(getattr(self.shared_state, '_metrics', None), '_custom', {})
        for key, val in custom.items():
            try:
                json.dumps(val)  # Test if serializable
                state_snapshot[key] = val
            except (TypeError, ValueError):
                state_snapshot[key] = str(val)

        # Get convergence metrics
        convergence = {}
        metrics = self.shared_state.get("convergence_metrics")
        if metrics and hasattr(metrics, "__dict__"):
            convergence = {k: v for k, v in metrics.__dict__.items()
                         if not k.startswith("_")}
        elif isinstance(metrics, dict):
            convergence = metrics

        # Get completed agents
        completed = self.shared_state.get("completed_agents", [])
        if not isinstance(completed, list):
            completed = list(completed) if completed else []

        # Get recent events from event bus history
        recent_events = []
        try:
            history = self.event_bus.get_history(limit=50)
            for evt in history:
                recent_events.append({
                    "type": evt.type.value,
                    "source": evt.source,
                    "timestamp": evt.timestamp.isoformat(),
                    "correlation_id": getattr(evt, "correlation_id", None),
                })
        except Exception:
            pass

        checkpoint = PipelineCheckpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now().isoformat(),
            trace_id=trace_id,
            phase=phase,
            milestone=milestone,
            completed_agents=completed,
            shared_state_snapshot=state_snapshot,
            convergence_metrics=convergence,
            recent_events=recent_events,
            metadata=metadata or {},
        )

        # Write to disk
        filepath = self._checkpoint_dir / f"{checkpoint_id}.json"
        filepath.write_text(
            json.dumps(checkpoint.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        logger.info(
            "checkpoint_saved",
            checkpoint_id=checkpoint_id,
            milestone=milestone,
            phase=phase,
            trace_id=trace_id,
        )

        # Cleanup old checkpoints
        self._cleanup_old_checkpoints()

        return checkpoint

    def load_latest(self) -> Optional[PipelineCheckpoint]:
        """Load the most recent checkpoint from disk."""
        checkpoints = sorted(
            self._checkpoint_dir.glob("cp-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not checkpoints:
            return None

        try:
            data = json.loads(checkpoints[0].read_text(encoding="utf-8"))
            checkpoint = PipelineCheckpoint.from_dict(data)
            logger.info(
                "checkpoint_loaded",
                checkpoint_id=checkpoint.checkpoint_id,
                milestone=checkpoint.milestone,
                phase=checkpoint.phase,
            )
            return checkpoint
        except Exception as e:
            logger.error("checkpoint_load_failed", error=str(e))
            return None

    def load_by_id(self, checkpoint_id: str) -> Optional[PipelineCheckpoint]:
        """Load a specific checkpoint by ID."""
        filepath = self._checkpoint_dir / f"{checkpoint_id}.json"
        if not filepath.exists():
            return None

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return PipelineCheckpoint.from_dict(data)
        except Exception as e:
            logger.error("checkpoint_load_failed", checkpoint_id=checkpoint_id, error=str(e))
            return None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all available checkpoints (newest first)."""
        result = []
        for path in sorted(
            self._checkpoint_dir.glob("cp-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                result.append({
                    "checkpoint_id": data.get("checkpoint_id", path.stem),
                    "timestamp": data.get("timestamp"),
                    "milestone": data.get("milestone"),
                    "phase": data.get("phase"),
                    "trace_id": data.get("trace_id"),
                })
            except Exception:
                continue
        return result

    async def restore_from_checkpoint(self, checkpoint: PipelineCheckpoint) -> None:
        """Restore SharedState from a checkpoint snapshot."""
        for key, value in checkpoint.shared_state_snapshot.items():
            await self.shared_state.set(key, value)

        logger.info(
            "checkpoint_restored",
            checkpoint_id=checkpoint.checkpoint_id,
            phase=checkpoint.phase,
            restored_keys=len(checkpoint.shared_state_snapshot),
        )

    def _cleanup_old_checkpoints(self):
        """Remove old checkpoints beyond MAX_CHECKPOINTS."""
        checkpoints = sorted(
            self._checkpoint_dir.glob("cp-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old in checkpoints[MAX_CHECKPOINTS:]:
            try:
                old.unlink()
                logger.debug("checkpoint_cleaned", path=str(old))
            except Exception:
                pass

    def clear_all(self):
        """Remove all checkpoints for this project."""
        for path in self._checkpoint_dir.glob("cp-*.json"):
            try:
                path.unlink()
            except Exception:
                pass
        logger.info("checkpoints_cleared", project_dir=str(self.project_dir))
