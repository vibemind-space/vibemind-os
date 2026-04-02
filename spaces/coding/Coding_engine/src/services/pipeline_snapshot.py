"""
Pipeline Snapshot — captures and manages pipeline state snapshots.

Features:
- Full pipeline state capture (serializable dicts)
- Snapshot comparison (diff between snapshots)
- Snapshot tagging and labeling
- Snapshot retention policies
- Snapshot restore data
- Snapshot search and listing
"""

from __future__ import annotations

import copy
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    """A captured pipeline state snapshot."""
    snapshot_id: str
    name: str
    description: str
    created_at: float
    created_by: str
    data: Dict[str, Any]  # The actual state data
    tags: Set[str]
    metadata: Dict[str, Any]
    size_estimate: int  # Rough byte size estimate


# ---------------------------------------------------------------------------
# Pipeline Snapshot Manager
# ---------------------------------------------------------------------------

class PipelineSnapshot:
    """Captures and manages pipeline state snapshots."""

    def __init__(
        self,
        max_snapshots: int = 200,
        retention_seconds: float = 0.0,  # 0 = no expiry
    ):
        self._max_snapshots = max_snapshots
        self._retention_seconds = retention_seconds
        self._snapshots: Dict[str, Snapshot] = {}

        self._stats = {
            "total_created": 0,
            "total_deleted": 0,
            "total_restored": 0,
            "total_compared": 0,
        }

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture(
        self,
        name: str,
        data: Dict[str, Any],
        description: str = "",
        created_by: str = "system",
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Capture a new snapshot. Returns snapshot_id."""
        sid = f"snap-{uuid.uuid4().hex[:8]}"
        snapshot_data = copy.deepcopy(data)
        size = self._estimate_size(snapshot_data)

        self._snapshots[sid] = Snapshot(
            snapshot_id=sid,
            name=name,
            description=description,
            created_at=time.time(),
            created_by=created_by,
            data=snapshot_data,
            tags=tags or set(),
            metadata=metadata or {},
            size_estimate=size,
        )
        self._stats["total_created"] += 1
        self._enforce_limits()
        return sid

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get(self, snapshot_id: str) -> Optional[Dict]:
        """Get snapshot metadata (without full data)."""
        s = self._snapshots.get(snapshot_id)
        if not s:
            return None
        return self._snap_to_dict(s, include_data=False)

    def get_data(self, snapshot_id: str) -> Optional[Dict]:
        """Get the full snapshot data."""
        s = self._snapshots.get(snapshot_id)
        if not s:
            return None
        return copy.deepcopy(s.data)

    def get_by_name(self, name: str) -> List[Dict]:
        """Get all snapshots with a given name (sorted by time desc)."""
        results = [
            self._snap_to_dict(s, include_data=False)
            for s in self._snapshots.values()
            if s.name == name
        ]
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results

    def get_latest(self, name: Optional[str] = None) -> Optional[Dict]:
        """Get the most recent snapshot, optionally filtered by name."""
        candidates = list(self._snapshots.values())
        if name:
            candidates = [s for s in candidates if s.name == name]
        if not candidates:
            return None
        latest = max(candidates, key=lambda s: s.created_at)
        return self._snap_to_dict(latest, include_data=False)

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def compare(self, snap_id_a: str, snap_id_b: str) -> Optional[Dict]:
        """Compare two snapshots. Returns diff summary."""
        a = self._snapshots.get(snap_id_a)
        b = self._snapshots.get(snap_id_b)
        if not a or not b:
            return None

        self._stats["total_compared"] += 1

        added = []
        removed = []
        changed = []

        all_keys = set(a.data.keys()) | set(b.data.keys())
        for key in sorted(all_keys):
            in_a = key in a.data
            in_b = key in b.data
            if in_a and not in_b:
                removed.append(key)
            elif not in_a and in_b:
                added.append(key)
            elif a.data[key] != b.data[key]:
                changed.append(key)

        return {
            "snapshot_a": snap_id_a,
            "snapshot_b": snap_id_b,
            "added": added,
            "removed": removed,
            "changed": changed,
            "total_diffs": len(added) + len(removed) + len(changed),
            "identical": len(added) + len(removed) + len(changed) == 0,
        }

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore(self, snapshot_id: str) -> Optional[Dict]:
        """Get snapshot data for restoration. Returns deep copy."""
        s = self._snapshots.get(snapshot_id)
        if not s:
            return None
        self._stats["total_restored"] += 1
        return copy.deepcopy(s.data)

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def update(
        self,
        snapshot_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Update snapshot metadata."""
        s = self._snapshots.get(snapshot_id)
        if not s:
            return False
        if name is not None:
            s.name = name
        if description is not None:
            s.description = description
        if tags is not None:
            s.tags = tags
        if metadata is not None:
            s.metadata = metadata
        return True

    def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        if snapshot_id not in self._snapshots:
            return False
        del self._snapshots[snapshot_id]
        self._stats["total_deleted"] += 1
        return True

    def tag(self, snapshot_id: str, tag: str) -> bool:
        """Add a tag to a snapshot."""
        s = self._snapshots.get(snapshot_id)
        if not s:
            return False
        s.tags.add(tag)
        return True

    def untag(self, snapshot_id: str, tag: str) -> bool:
        """Remove a tag from a snapshot."""
        s = self._snapshots.get(snapshot_id)
        if not s or tag not in s.tags:
            return False
        s.tags.discard(tag)
        return True

    # ------------------------------------------------------------------
    # Listing & Search
    # ------------------------------------------------------------------

    def list_snapshots(
        self,
        name: Optional[str] = None,
        created_by: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List snapshots with filters."""
        results = []
        for s in sorted(self._snapshots.values(),
                        key=lambda x: x.created_at, reverse=True):
            if name and s.name != name:
                continue
            if created_by and s.created_by != created_by:
                continue
            if tag and tag not in s.tags:
                continue
            results.append(self._snap_to_dict(s, include_data=False))
            if len(results) >= limit:
                break
        return results

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Search snapshots by name or description."""
        q = query.lower()
        results = []
        for s in self._snapshots.values():
            if q in s.name.lower() or q in s.description.lower():
                results.append(self._snap_to_dict(s, include_data=False))
                if len(results) >= limit:
                    break
        return results

    def list_names(self) -> List[str]:
        """List unique snapshot names."""
        return sorted(set(s.name for s in self._snapshots.values()))

    def list_tags(self) -> Dict[str, int]:
        """List all tags with counts."""
        counts: Dict[str, int] = defaultdict(int)
        for s in self._snapshots.values():
            for t in s.tags:
                counts[t] += 1
        return dict(sorted(counts.items()))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _snap_to_dict(self, s: Snapshot, include_data: bool = False) -> Dict:
        result = {
            "snapshot_id": s.snapshot_id,
            "name": s.name,
            "description": s.description,
            "created_at": s.created_at,
            "created_by": s.created_by,
            "tags": sorted(s.tags),
            "metadata": s.metadata,
            "size_estimate": s.size_estimate,
            "data_keys": sorted(s.data.keys()),
        }
        if include_data:
            result["data"] = copy.deepcopy(s.data)
        return result

    def _estimate_size(self, data: Any) -> int:
        """Rough size estimate in bytes."""
        return len(str(data))

    def _enforce_limits(self) -> None:
        """Enforce max snapshots and retention."""
        # Retention
        if self._retention_seconds > 0:
            cutoff = time.time() - self._retention_seconds
            expired = [sid for sid, s in self._snapshots.items()
                       if s.created_at < cutoff]
            for sid in expired:
                del self._snapshots[sid]
                self._stats["total_deleted"] += 1

        # Max count
        if len(self._snapshots) > self._max_snapshots:
            by_time = sorted(self._snapshots.values(), key=lambda s: s.created_at)
            to_remove = len(self._snapshots) - self._max_snapshots
            for s in by_time[:to_remove]:
                del self._snapshots[s.snapshot_id]
                self._stats["total_deleted"] += 1

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        total_size = sum(s.size_estimate for s in self._snapshots.values())
        return {
            **self._stats,
            "total_snapshots": len(self._snapshots),
            "total_size_estimate": total_size,
        }

    def reset(self) -> None:
        self._snapshots.clear()
        self._stats = {k: 0 for k in self._stats}
