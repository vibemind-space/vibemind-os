"""Pipeline version control - manages versioned pipeline definitions."""

import time
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class VersionEntry:
    """A versioned pipeline definition entry."""
    version_id: str = ""
    pipeline_id: str = ""
    definition: dict = field(default_factory=dict)
    version_tag: str = ""
    active: bool = True
    created_at: float = 0.0
    seq: int = 0


class PipelineVersionControl:
    """Manages versioned pipeline definitions with rollback support."""

    def __init__(self, max_entries: int = 10000):
        self._versions: Dict[str, VersionEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max(1, max_entries)

    # --- ID Generation ---

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"pvc-{self._seq}-{id(self)}"
        return "pvc-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # --- Core API ---

    def create_version(
        self,
        pipeline_id: str,
        definition: dict,
        version_tag: str = "",
    ) -> str:
        """Create a new version for a pipeline. Returns version_id (str 'pvc-...')."""
        if not pipeline_id or not isinstance(definition, dict):
            return ""
        if len(self._versions) >= self._max_entries:
            self._prune()
            if len(self._versions) >= self._max_entries:
                return ""

        # Deactivate all previous versions for this pipeline
        for entry in self._versions.values():
            if entry.pipeline_id == pipeline_id and entry.active:
                entry.active = False

        version_id = self._generate_id()
        now = time.time()

        entry = VersionEntry(
            version_id=version_id,
            pipeline_id=pipeline_id,
            definition=dict(definition),
            version_tag=version_tag,
            active=True,
            created_at=now,
            seq=self._seq,
        )

        self._versions[version_id] = entry
        self._fire("version_created", {
            "version_id": version_id,
            "pipeline_id": pipeline_id,
        })
        return version_id

    def get_version(self, version_id: str) -> Optional[Dict]:
        """Get a version by ID. Returns dict or None."""
        entry = self._versions.get(version_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    def get_latest_version(self, pipeline_id: str) -> Optional[Dict]:
        """Get the latest version for a pipeline (by seq). Returns dict or None."""
        latest: Optional[VersionEntry] = None
        for entry in self._versions.values():
            if entry.pipeline_id == pipeline_id:
                if latest is None or entry.seq > latest.seq:
                    latest = entry
        if latest is None:
            return None
        return self._entry_to_dict(latest)

    def get_version_history(self, pipeline_id: str) -> List[Dict]:
        """Get version history for a pipeline (newest first)."""
        entries = [
            e for e in self._versions.values()
            if e.pipeline_id == pipeline_id
        ]
        entries.sort(key=lambda e: e.seq, reverse=True)
        return [self._entry_to_dict(e) for e in entries]

    def rollback(self, pipeline_id: str, version_id: str) -> bool:
        """Rollback a pipeline to a specific version. Marks that version as active, others inactive."""
        target = self._versions.get(version_id)
        if not target or target.pipeline_id != pipeline_id:
            return False

        for entry in self._versions.values():
            if entry.pipeline_id == pipeline_id:
                entry.active = (entry.version_id == version_id)

        self._fire("version_rollback", {
            "version_id": version_id,
            "pipeline_id": pipeline_id,
        })
        return True

    def get_active_version(self, pipeline_id: str) -> Optional[Dict]:
        """Get the currently active version for a pipeline. Returns dict or None."""
        active: Optional[VersionEntry] = None
        for entry in self._versions.values():
            if entry.pipeline_id == pipeline_id and entry.active:
                if active is None or entry.seq > active.seq:
                    active = entry
        if active is None:
            return None
        return self._entry_to_dict(active)

    def delete_version(self, version_id: str) -> bool:
        """Delete a version by ID. Returns True if deleted."""
        if version_id not in self._versions:
            return False
        entry = self._versions.pop(version_id)
        self._fire("version_deleted", {
            "version_id": version_id,
            "pipeline_id": entry.pipeline_id,
        })
        return True

    def list_pipelines(self) -> List[str]:
        """List all unique pipeline IDs."""
        pipelines = set()
        for entry in self._versions.values():
            pipelines.add(entry.pipeline_id)
        result = sorted(pipelines)
        return result

    def get_version_count(self) -> int:
        """Get total number of version entries."""
        return len(self._versions)

    # --- Callbacks ---

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already exists."""
        if not name or name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns False if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # --- Stats & Reset ---

    def get_stats(self) -> Dict:
        """Get statistics about the version store."""
        pipelines = set()
        active_count = 0
        for entry in self._versions.values():
            pipelines.add(entry.pipeline_id)
            if entry.active:
                active_count += 1
        return {
            "total_versions": len(self._versions),
            "total_pipelines": len(pipelines),
            "active_versions": active_count,
            "max_entries": self._max_entries,
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._versions.clear()
        self._callbacks.clear()
        self._seq = 0

    # --- Internal ---

    def _entry_to_dict(self, entry: VersionEntry) -> Dict:
        """Convert a VersionEntry to a dict."""
        return {
            "version_id": entry.version_id,
            "pipeline_id": entry.pipeline_id,
            "definition": dict(entry.definition),
            "version_tag": entry.version_tag,
            "active": entry.active,
            "created_at": entry.created_at,
            "seq": entry.seq,
        }

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def _prune(self) -> None:
        """Remove oldest inactive versions to make room."""
        inactive = [
            e for e in self._versions.values()
            if not e.active
        ]
        if not inactive:
            return
        inactive.sort(key=lambda e: e.seq)
        to_remove = len(self._versions) - self._max_entries + 1
        for entry in inactive[:max(1, to_remove)]:
            self._versions.pop(entry.version_id, None)
