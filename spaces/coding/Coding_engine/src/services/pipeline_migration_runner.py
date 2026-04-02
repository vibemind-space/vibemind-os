"""Pipeline Migration Runner – manages versioned data/schema migrations.

Registers migration steps with version numbers, runs them in order,
tracks which have been applied, and supports rollback.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Migration:
    migration_id: str
    version: int
    name: str
    up_fn: Optional[Callable]
    down_fn: Optional[Callable]
    status: str  # pending, applied, rolled_back, failed
    applied_at: float
    tags: List[str]
    created_at: float


@dataclass
class _MigrationEvent:
    event_id: str
    version: int
    name: str
    action: str  # applied, rolled_back, failed
    timestamp: float


class PipelineMigrationRunner:
    """Manages versioned data/schema migrations."""

    STATUSES = ("pending", "applied", "rolled_back", "failed")

    def __init__(self, max_migrations: int = 10000, max_history: int = 100000):
        self._migrations: Dict[str, _Migration] = {}
        self._version_index: Dict[int, str] = {}  # version -> migration_id
        self._name_index: Dict[str, str] = {}  # name -> migration_id
        self._history: List[_MigrationEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_migrations = max_migrations
        self._max_history = max_history
        self._seq = 0
        self._current_version = 0

        # stats
        self._total_registered = 0
        self._total_applied = 0
        self._total_rolled_back = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        version: int,
        name: str,
        up_fn: Optional[Callable] = None,
        down_fn: Optional[Callable] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if version <= 0 or not name:
            return ""
        if version in self._version_index:
            return ""
        if name in self._name_index:
            return ""
        if len(self._migrations) >= self._max_migrations:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{version}-{name}-{now}-{self._seq}"
        mid = "mig-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        migration = _Migration(
            migration_id=mid,
            version=version,
            name=name,
            up_fn=up_fn,
            down_fn=down_fn,
            status="pending",
            applied_at=0.0,
            tags=tags or [],
            created_at=now,
        )
        self._migrations[mid] = migration
        self._version_index[version] = mid
        self._name_index[name] = mid
        self._total_registered += 1
        self._fire("migration_registered", {"migration_id": mid, "version": version, "name": name})
        return mid

    def get_migration(self, migration_id: str) -> Optional[Dict[str, Any]]:
        m = self._migrations.get(migration_id)
        if not m:
            return None
        return {
            "migration_id": m.migration_id,
            "version": m.version,
            "name": m.name,
            "status": m.status,
            "has_up": m.up_fn is not None,
            "has_down": m.down_fn is not None,
            "applied_at": m.applied_at,
            "tags": list(m.tags),
            "created_at": m.created_at,
        }

    def get_by_version(self, version: int) -> Optional[Dict[str, Any]]:
        mid = self._version_index.get(version)
        if not mid:
            return None
        return self.get_migration(mid)

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        mid = self._name_index.get(name)
        if not mid:
            return None
        return self.get_migration(mid)

    def remove_migration(self, migration_id: str) -> bool:
        m = self._migrations.pop(migration_id, None)
        if not m:
            return False
        self._version_index.pop(m.version, None)
        self._name_index.pop(m.name, None)
        return True

    # ------------------------------------------------------------------
    # Run migrations
    # ------------------------------------------------------------------

    def migrate_up(self, target_version: int = 0) -> Dict[str, Any]:
        """Apply pending migrations up to target_version (0 = all)."""
        versions = sorted(v for v in self._version_index.keys() if v > self._current_version)
        if target_version > 0:
            versions = [v for v in versions if v <= target_version]

        applied = []
        failed = []
        for version in versions:
            mid = self._version_index[version]
            m = self._migrations[mid]
            if m.status == "applied":
                continue
            if m.up_fn:
                try:
                    m.up_fn()
                    m.status = "applied"
                    m.applied_at = time.time()
                    self._current_version = version
                    self._total_applied += 1
                    self._record_event(version, m.name, "applied")
                    self._fire("migration_applied", {"version": version, "name": m.name})
                    applied.append(version)
                except Exception as exc:
                    m.status = "failed"
                    self._total_failed += 1
                    self._record_event(version, m.name, "failed")
                    self._fire("migration_failed", {"version": version, "name": m.name, "error": str(exc)})
                    failed.append(version)
                    break  # stop on first failure
            else:
                # No up function, just mark as applied
                m.status = "applied"
                m.applied_at = time.time()
                self._current_version = version
                self._total_applied += 1
                self._record_event(version, m.name, "applied")
                applied.append(version)

        return {"applied": applied, "failed": failed, "current_version": self._current_version}

    def migrate_down(self, target_version: int = 0) -> Dict[str, Any]:
        """Roll back applied migrations down to target_version."""
        versions = sorted(
            (v for v in self._version_index.keys()
             if v <= self._current_version and v > target_version),
            reverse=True,
        )

        rolled_back = []
        failed = []
        for version in versions:
            mid = self._version_index[version]
            m = self._migrations[mid]
            if m.status != "applied":
                continue
            if m.down_fn:
                try:
                    m.down_fn()
                    m.status = "rolled_back"
                    self._current_version = version - 1
                    self._total_rolled_back += 1
                    self._record_event(version, m.name, "rolled_back")
                    self._fire("migration_rolled_back", {"version": version, "name": m.name})
                    rolled_back.append(version)
                except Exception:
                    failed.append(version)
                    break
            else:
                m.status = "rolled_back"
                self._current_version = version - 1
                self._total_rolled_back += 1
                self._record_event(version, m.name, "rolled_back")
                rolled_back.append(version)

        return {"rolled_back": rolled_back, "failed": failed, "current_version": self._current_version}

    def get_current_version(self) -> int:
        return self._current_version

    def get_pending(self) -> List[Dict[str, Any]]:
        """Get all pending migrations."""
        results = []
        for m in self._migrations.values():
            if m.status == "pending":
                results.append(self.get_migration(m.migration_id))
        return sorted(results, key=lambda x: x["version"])

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_migrations(self, status: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for m in self._migrations.values():
            if status and m.status != status:
                continue
            if tag and tag not in m.tags:
                continue
            results.append(self.get_migration(m.migration_id))
        return sorted(results, key=lambda x: x["version"])

    def get_history(self, action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "version": ev.version,
                "name": ev.name,
                "action": ev.action,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, version: int, name: str, action: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{version}-{action}-{now}-{self._seq}"
        evid = "mev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _MigrationEvent(
            event_id=evid, version=version, name=name,
            action=action, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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
            "current_version": self._current_version,
            "total_migrations": len(self._migrations),
            "total_registered": self._total_registered,
            "total_applied": self._total_applied,
            "total_rolled_back": self._total_rolled_back,
            "total_failed": self._total_failed,
            "pending_count": sum(1 for m in self._migrations.values() if m.status == "pending"),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._migrations.clear()
        self._version_index.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._current_version = 0
        self._total_registered = 0
        self._total_applied = 0
        self._total_rolled_back = 0
        self._total_failed = 0
