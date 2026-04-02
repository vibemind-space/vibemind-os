"""Pipeline Version Store -- tracks pipeline version history with
versioning, diffing, and rollback points.

Features:
- Create and manage versioned pipeline configurations
- Auto-incrementing version numbers per pipeline
- Activate/deactivate versions for rollback support
- Diff two versions to see added, removed, and changed config keys
- Query version history ordered by version number
- Callback system for change notifications
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
class VersionEntry:
    """A single pipeline version record."""
    version_id: str = ""
    pipeline_name: str = ""
    version_number: int = 0
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: float = 0.0
    tags: List[str] = field(default_factory=list)
    is_active: bool = False


# ---------------------------------------------------------------------------
# Pipeline Version Store
# ---------------------------------------------------------------------------

class PipelineVersionStore:
    """Tracks pipeline version history with versioning, diffing,
    and rollback points."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._versions: Dict[str, VersionEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._version_counters: Dict[str, int] = {}
        self._total_created = 0
        self._total_removed = 0
        self._total_activations = 0
        self._total_diffs = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        """Generate a collision-free ID with prefix pvs-."""
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pvs-{digest}"

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
                logger.debug("callback_error", action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest inactive entries when exceeding max_entries."""
        while len(self._versions) > self._max_entries:
            # Prefer removing inactive, non-active versions first
            inactive = [
                (vid, v) for vid, v in self._versions.items()
                if not v.is_active
            ]
            if inactive:
                inactive.sort(key=lambda x: x[1].created_at)
                oldest_id = inactive[0][0]
            else:
                # All active -- remove oldest anyway
                oldest_id = min(
                    self._versions,
                    key=lambda k: self._versions[k].created_at,
                )
            del self._versions[oldest_id]
            logger.debug("version_pruned", version_id=oldest_id)

    # ------------------------------------------------------------------
    # create_version
    # ------------------------------------------------------------------

    def create_version(
        self,
        pipeline_name: str,
        config: Dict[str, Any],
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new version for a pipeline.

        Auto-increments version_number per pipeline. The first version
        for a pipeline is automatically activated.

        Returns:
            The version_id string (pvs-...), or "" on invalid input.
        """
        if not pipeline_name:
            logger.warning("create_version_empty_name")
            return ""
        if config is None:
            logger.warning("create_version_no_config", pipeline=pipeline_name)
            return ""

        # Auto-increment version number
        current = self._version_counters.get(pipeline_name, 0)
        next_number = current + 1
        self._version_counters[pipeline_name] = next_number

        version_id = self._generate_id(f"{pipeline_name}.v{next_number}")

        # First version for a pipeline is auto-activated
        is_first = not any(
            v.pipeline_name == pipeline_name for v in self._versions.values()
        )

        entry = VersionEntry(
            version_id=version_id,
            pipeline_name=pipeline_name,
            version_number=next_number,
            config=dict(config),
            description=description,
            created_at=time.time(),
            tags=list(tags) if tags else [],
            is_active=is_first,
        )
        self._versions[version_id] = entry
        self._total_created += 1
        self._prune()

        logger.info(
            "version_created",
            version_id=version_id,
            pipeline=pipeline_name,
            version_number=next_number,
            is_active=is_first,
        )
        self._fire("version_created", {
            "version_id": version_id,
            "pipeline_name": pipeline_name,
            "version_number": next_number,
        })
        return version_id

    # ------------------------------------------------------------------
    # get_version
    # ------------------------------------------------------------------

    def get_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        """Get a version entry by ID. Returns None if not found."""
        entry = self._versions.get(version_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # get_latest_version
    # ------------------------------------------------------------------

    def get_latest_version(self, pipeline_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest version (highest version_number) for a pipeline."""
        best: Optional[VersionEntry] = None
        for v in self._versions.values():
            if v.pipeline_name != pipeline_name:
                continue
            if best is None or v.version_number > best.version_number:
                best = v
        if best is None:
            return None
        return self._entry_to_dict(best)

    # ------------------------------------------------------------------
    # get_version_history
    # ------------------------------------------------------------------

    def get_version_history(self, pipeline_name: str) -> List[Dict[str, Any]]:
        """Get all versions for a pipeline, ordered by version_number ascending."""
        entries = [
            v for v in self._versions.values()
            if v.pipeline_name == pipeline_name
        ]
        entries.sort(key=lambda v: v.version_number)
        return [self._entry_to_dict(e) for e in entries]

    # ------------------------------------------------------------------
    # activate_version
    # ------------------------------------------------------------------

    def activate_version(self, pipeline_name: str, version_id: str) -> bool:
        """Activate a specific version for a pipeline, deactivating all others.

        Returns False if version_id not found or doesn't belong to pipeline.
        """
        target = self._versions.get(version_id)
        if target is None:
            logger.warning("activate_version_not_found", version_id=version_id)
            return False
        if target.pipeline_name != pipeline_name:
            logger.warning(
                "activate_version_pipeline_mismatch",
                version_id=version_id,
                expected=pipeline_name,
                actual=target.pipeline_name,
            )
            return False

        # Deactivate all versions for this pipeline
        for v in self._versions.values():
            if v.pipeline_name == pipeline_name:
                v.is_active = False

        # Activate the target
        target.is_active = True
        self._total_activations += 1

        logger.info(
            "version_activated",
            version_id=version_id,
            pipeline=pipeline_name,
            version_number=target.version_number,
        )
        self._fire("version_activated", {
            "version_id": version_id,
            "pipeline_name": pipeline_name,
            "version_number": target.version_number,
        })
        return True

    # ------------------------------------------------------------------
    # get_active_version
    # ------------------------------------------------------------------

    def get_active_version(self, pipeline_name: str) -> Optional[Dict[str, Any]]:
        """Get the currently active version for a pipeline."""
        for v in self._versions.values():
            if v.pipeline_name == pipeline_name and v.is_active:
                return self._entry_to_dict(v)
        return None

    # ------------------------------------------------------------------
    # diff_versions
    # ------------------------------------------------------------------

    def diff_versions(
        self, version_id_a: str, version_id_b: str
    ) -> Dict[str, Any]:
        """Compute the diff between two version configs.

        Returns a dict with:
            added   -- keys present in B but not in A
            removed -- keys present in A but not in B
            changed -- keys present in both but with different values

        Returns empty lists if either version is not found.
        """
        self._total_diffs += 1

        entry_a = self._versions.get(version_id_a)
        entry_b = self._versions.get(version_id_b)

        if entry_a is None or entry_b is None:
            missing = []
            if entry_a is None:
                missing.append(version_id_a)
            if entry_b is None:
                missing.append(version_id_b)
            logger.warning("diff_versions_not_found", missing=missing)
            return {"added": [], "removed": [], "changed": []}

        keys_a = set(entry_a.config.keys())
        keys_b = set(entry_b.config.keys())

        added = sorted(keys_b - keys_a)
        removed = sorted(keys_a - keys_b)

        changed: List[Dict[str, Any]] = []
        for key in sorted(keys_a & keys_b):
            val_a = entry_a.config[key]
            val_b = entry_b.config[key]
            if val_a != val_b:
                changed.append({
                    "key": key,
                    "old_value": val_a,
                    "new_value": val_b,
                })

        logger.info(
            "versions_diffed",
            version_a=version_id_a,
            version_b=version_id_b,
            added_count=len(added),
            removed_count=len(removed),
            changed_count=len(changed),
        )
        return {
            "added": added,
            "removed": removed,
            "changed": changed,
        }

    # ------------------------------------------------------------------
    # list_pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """List all pipeline names that have at least one version, sorted."""
        names = set(v.pipeline_name for v in self._versions.values())
        return sorted(names)

    # ------------------------------------------------------------------
    # remove_version
    # ------------------------------------------------------------------

    def remove_version(self, version_id: str) -> bool:
        """Remove a version entry by ID.

        If the removed version was active, the latest remaining version
        for that pipeline is auto-activated.

        Returns False if version_id not found.
        """
        entry = self._versions.get(version_id)
        if entry is None:
            logger.warning("remove_version_not_found", version_id=version_id)
            return False

        pipeline_name = entry.pipeline_name
        was_active = entry.is_active

        del self._versions[version_id]
        self._total_removed += 1

        # If removed version was active, activate the latest remaining
        if was_active:
            remaining = [
                v for v in self._versions.values()
                if v.pipeline_name == pipeline_name
            ]
            if remaining:
                latest = max(remaining, key=lambda v: v.version_number)
                latest.is_active = True
                logger.info(
                    "auto_activated_after_removal",
                    version_id=latest.version_id,
                    pipeline=pipeline_name,
                    version_number=latest.version_number,
                )

        logger.info(
            "version_removed",
            version_id=version_id,
            pipeline=pipeline_name,
            was_active=was_active,
        )
        self._fire("version_removed", {
            "version_id": version_id,
            "pipeline_name": pipeline_name,
        })
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        pipeline_names = set(v.pipeline_name for v in self._versions.values())
        active_count = sum(1 for v in self._versions.values() if v.is_active)

        return {
            "total_created": self._total_created,
            "total_removed": self._total_removed,
            "total_activations": self._total_activations,
            "total_diffs": self._total_diffs,
            "current_versions": len(self._versions),
            "current_pipelines": len(pipeline_names),
            "active_versions": active_count,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all versions, counters, and callbacks."""
        self._versions.clear()
        self._callbacks.clear()
        self._version_counters.clear()
        self._seq = 0
        self._total_created = 0
        self._total_removed = 0
        self._total_activations = 0
        self._total_diffs = 0
        logger.info("pipeline_version_store_reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry: VersionEntry) -> Dict[str, Any]:
        """Convert a VersionEntry dataclass to a plain dict."""
        return {
            "version_id": entry.version_id,
            "pipeline_name": entry.pipeline_name,
            "version_number": entry.version_number,
            "config": dict(entry.config),
            "description": entry.description,
            "created_at": entry.created_at,
            "tags": list(entry.tags),
            "is_active": entry.is_active,
        }
