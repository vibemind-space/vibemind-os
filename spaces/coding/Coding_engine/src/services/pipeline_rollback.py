"""
Pipeline Rollback — Snapshot and rollback mechanism for pipeline state.

Provides:
- Snapshot creation at pipeline phase boundaries
- Named snapshots for manual save points
- Rollback to any previous snapshot
- Diff between snapshots
- Automatic cleanup of old snapshots
- Snapshot metadata and tagging

Usage:
    rollback = PipelineRollbackManager(max_snapshots=50)

    # Create snapshot
    snap_id = rollback.create_snapshot(
        phase="generation",
        state={"files": [...], "config": {...}},
        description="After code generation"
    )

    # List snapshots
    snaps = rollback.list_snapshots()

    # Rollback
    state = rollback.rollback_to(snap_id)

    # Compare
    diff = rollback.diff_snapshots(snap_id_a, snap_id_b)
"""

import copy
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class SnapshotType(str, Enum):
    AUTO = "auto"       # Created automatically at phase boundaries
    MANUAL = "manual"   # Created by user/agent request
    PRE_ROLLBACK = "pre_rollback"  # Created before a rollback


@dataclass
class Snapshot:
    """A point-in-time snapshot of pipeline state."""
    snapshot_id: str
    phase: str
    state: Dict[str, Any]
    snapshot_type: SnapshotType = SnapshotType.AUTO
    description: str = ""
    tags: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: str = ""  # Previous snapshot in chain

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "phase": self.phase,
            "snapshot_type": self.snapshot_type.value,
            "description": self.description,
            "tags": sorted(self.tags),
            "age_seconds": round(self.age_seconds, 1),
            "parent_id": self.parent_id,
            "state_keys": sorted(self.state.keys()),
            "metadata": self.metadata,
        }


class PipelineRollbackManager:
    """Manages pipeline state snapshots and rollback operations."""

    def __init__(self, max_snapshots: int = 50, event_bus=None):
        self._max_snapshots = max_snapshots
        self._event_bus = event_bus

        # Snapshot storage: ordered list (oldest first)
        self._snapshots: List[Snapshot] = []
        self._snapshot_map: Dict[str, Snapshot] = {}

        # Current position in snapshot chain
        self._current_id: str = ""

        # Stats
        self._total_created = 0
        self._total_rollbacks = 0
        self._total_pruned = 0

    # ── Snapshot Creation ─────────────────────────────────────────────

    def create_snapshot(
        self,
        phase: str,
        state: Dict[str, Any],
        description: str = "",
        snapshot_type: SnapshotType = SnapshotType.AUTO,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new snapshot of the current pipeline state."""
        snapshot_id = f"snap-{uuid.uuid4().hex[:8]}"

        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            phase=phase,
            state=copy.deepcopy(state),  # Deep copy to prevent mutation
            snapshot_type=snapshot_type,
            description=description,
            tags=tags or set(),
            parent_id=self._current_id,
            metadata=metadata or {},
        )

        self._snapshots.append(snapshot)
        self._snapshot_map[snapshot_id] = snapshot
        self._current_id = snapshot_id
        self._total_created += 1

        # Prune if over limit
        self._prune()

        logger.info(
            "snapshot_created",
            component="pipeline_rollback",
            snapshot_id=snapshot_id,
            phase=phase,
            snapshot_type=snapshot_type.value,
            state_keys=sorted(state.keys()),
        )

        return snapshot_id

    def save_point(
        self,
        name: str,
        state: Dict[str, Any],
        phase: str = "manual",
    ) -> str:
        """Create a named manual save point."""
        return self.create_snapshot(
            phase=phase,
            state=state,
            description=f"Save point: {name}",
            snapshot_type=SnapshotType.MANUAL,
            tags={name, "save_point"},
        )

    # ── Rollback ──────────────────────────────────────────────────────

    def rollback_to(
        self,
        snapshot_id: str,
        save_current: bool = True,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Rollback to a previous snapshot. Returns the snapshot state."""
        target = self._snapshot_map.get(snapshot_id)
        if not target:
            logger.warning(
                "rollback_snapshot_not_found",
                component="pipeline_rollback",
                snapshot_id=snapshot_id,
            )
            return None

        # Optionally save current state before rollback
        if save_current and current_state:
            self.create_snapshot(
                phase="pre_rollback",
                state=current_state,
                description=f"Auto-saved before rollback to {snapshot_id}",
                snapshot_type=SnapshotType.PRE_ROLLBACK,
                tags={"pre_rollback"},
            )

        self._current_id = snapshot_id
        self._total_rollbacks += 1

        logger.info(
            "rollback_executed",
            component="pipeline_rollback",
            target_snapshot=snapshot_id,
            target_phase=target.phase,
            saved_current=save_current and current_state is not None,
        )

        return copy.deepcopy(target.state)

    def rollback_to_phase(
        self,
        phase: str,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Rollback to the most recent snapshot of a given phase."""
        for snap in reversed(self._snapshots):
            if snap.phase == phase:
                return self.rollback_to(
                    snap.snapshot_id,
                    current_state=current_state,
                )
        logger.warning(
            "rollback_phase_not_found",
            component="pipeline_rollback",
            phase=phase,
        )
        return None

    def rollback_to_tag(
        self,
        tag: str,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Rollback to the most recent snapshot with a given tag."""
        for snap in reversed(self._snapshots):
            if tag in snap.tags:
                return self.rollback_to(
                    snap.snapshot_id,
                    current_state=current_state,
                )
        return None

    def undo(self, current_state: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Rollback to the previous snapshot (one step back)."""
        current = self._snapshot_map.get(self._current_id)
        if not current or not current.parent_id:
            return None
        return self.rollback_to(
            current.parent_id,
            current_state=current_state,
        )

    # ── Snapshot Queries ──────────────────────────────────────────────

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Get snapshot metadata (without full state)."""
        snap = self._snapshot_map.get(snapshot_id)
        return snap.to_dict() if snap else None

    def get_snapshot_state(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Get the full state of a snapshot."""
        snap = self._snapshot_map.get(snapshot_id)
        if not snap:
            return None
        return copy.deepcopy(snap.state)

    def list_snapshots(
        self,
        phase: Optional[str] = None,
        tag: Optional[str] = None,
        snapshot_type: Optional[SnapshotType] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List snapshots with optional filters."""
        results = list(reversed(self._snapshots))  # Most recent first

        if phase:
            results = [s for s in results if s.phase == phase]
        if tag:
            results = [s for s in results if tag in s.tags]
        if snapshot_type:
            results = [s for s in results if s.snapshot_type == snapshot_type]

        return [s.to_dict() for s in results[:limit]]

    def get_current(self) -> Optional[Dict[str, Any]]:
        """Get the current (most recent) snapshot metadata."""
        if not self._current_id:
            return None
        return self.get_snapshot(self._current_id)

    def get_chain(self, snapshot_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get the chain of snapshots leading to the given snapshot."""
        snap_id = snapshot_id or self._current_id
        chain = []
        while snap_id:
            snap = self._snapshot_map.get(snap_id)
            if not snap:
                break
            chain.append(snap.to_dict())
            snap_id = snap.parent_id
        return chain

    # ── Diff ──────────────────────────────────────────────────────────

    def diff_snapshots(self, id_a: str, id_b: str) -> Dict[str, Any]:
        """Compare two snapshots and return the differences."""
        snap_a = self._snapshot_map.get(id_a)
        snap_b = self._snapshot_map.get(id_b)

        if not snap_a or not snap_b:
            return {"error": "Snapshot not found"}

        state_a = snap_a.state
        state_b = snap_b.state

        all_keys = set(state_a.keys()) | set(state_b.keys())

        added = {}
        removed = {}
        modified = {}
        unchanged = []

        for key in all_keys:
            if key not in state_a:
                added[key] = state_b[key]
            elif key not in state_b:
                removed[key] = state_a[key]
            elif state_a[key] != state_b[key]:
                modified[key] = {
                    "old": state_a[key],
                    "new": state_b[key],
                }
            else:
                unchanged.append(key)

        return {
            "snapshot_a": id_a,
            "snapshot_b": id_b,
            "phase_a": snap_a.phase,
            "phase_b": snap_b.phase,
            "added": added,
            "removed": removed,
            "modified": modified,
            "unchanged": unchanged,
            "total_changes": len(added) + len(removed) + len(modified),
        }

    # ── Tags ──────────────────────────────────────────────────────────

    def add_tag(self, snapshot_id: str, tag: str) -> bool:
        """Add a tag to a snapshot."""
        snap = self._snapshot_map.get(snapshot_id)
        if not snap:
            return False
        snap.tags.add(tag)
        return True

    def remove_tag(self, snapshot_id: str, tag: str) -> bool:
        """Remove a tag from a snapshot."""
        snap = self._snapshot_map.get(snapshot_id)
        if not snap or tag not in snap.tags:
            return False
        snap.tags.discard(tag)
        return True

    # ── Cleanup ───────────────────────────────────────────────────────

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a specific snapshot."""
        snap = self._snapshot_map.get(snapshot_id)
        if not snap:
            return False

        self._snapshots.remove(snap)
        del self._snapshot_map[snapshot_id]

        # Update parent references
        for s in self._snapshots:
            if s.parent_id == snapshot_id:
                s.parent_id = snap.parent_id

        if self._current_id == snapshot_id:
            self._current_id = snap.parent_id

        return True

    def clear_older_than(self, seconds: float) -> int:
        """Remove snapshots older than a given age."""
        threshold = time.time() - seconds
        to_remove = [s for s in self._snapshots if s.created_at < threshold]

        for snap in to_remove:
            self.delete_snapshot(snap.snapshot_id)

        return len(to_remove)

    def _prune(self):
        """Remove oldest snapshots when over limit."""
        while len(self._snapshots) > self._max_snapshots:
            oldest = self._snapshots.pop(0)
            self._snapshot_map.pop(oldest.snapshot_id, None)
            # Fix parent references
            for s in self._snapshots:
                if s.parent_id == oldest.snapshot_id:
                    s.parent_id = ""
            self._total_pruned += 1

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get rollback manager statistics."""
        type_counts = {}
        for snap in self._snapshots:
            t = snap.snapshot_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        phase_counts = {}
        for snap in self._snapshots:
            phase_counts[snap.phase] = phase_counts.get(snap.phase, 0) + 1

        return {
            "total_snapshots": len(self._snapshots),
            "total_created": self._total_created,
            "total_rollbacks": self._total_rollbacks,
            "total_pruned": self._total_pruned,
            "max_snapshots": self._max_snapshots,
            "current_snapshot": self._current_id,
            "type_counts": type_counts,
            "phase_counts": phase_counts,
        }

    def reset(self):
        """Clear all snapshots and reset state."""
        self._snapshots.clear()
        self._snapshot_map.clear()
        self._current_id = ""
        self._total_created = 0
        self._total_rollbacks = 0
        self._total_pruned = 0
