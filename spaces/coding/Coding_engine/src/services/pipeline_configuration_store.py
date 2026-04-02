"""
Pipeline Configuration Store — hierarchical, typed configuration with validation and change tracking.

Features:
- Hierarchical namespace-based configuration
- Type validation (str, int, float, bool, list, dict)
- Default values and descriptions
- Change history with rollback
- Configuration profiles (dev, staging, prod)
- Schema definitions for validation
- Change notification callbacks
"""

from __future__ import annotations

import copy
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

VALID_TYPES = {"str", "int", "float", "bool", "list", "dict", "any"}

TYPE_MAP = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


@dataclass
class ConfigEntry:
    """A single configuration entry."""
    key: str
    namespace: str
    value: Any
    value_type: str
    default: Any
    description: str
    readonly: bool
    created_at: float
    updated_at: float


@dataclass
class ConfigChange:
    """A recorded configuration change."""
    change_id: str
    key: str
    namespace: str
    old_value: Any
    new_value: Any
    changed_by: str
    timestamp: float


# ---------------------------------------------------------------------------
# Pipeline Configuration Store
# ---------------------------------------------------------------------------

class PipelineConfigurationStore:
    """Hierarchical configuration store with validation and change tracking."""

    def __init__(
        self,
        max_entries: int = 10000,
        max_history: int = 5000,
    ):
        self._max_entries = max_entries
        self._max_history = max_history
        self._entries: Dict[str, ConfigEntry] = {}  # "namespace:key"
        self._history: List[ConfigChange] = []
        self._profiles: Dict[str, Dict[str, Any]] = {}  # profile_name -> {full_key: value}
        self._callbacks: Dict[str, Callable] = {}

        self._stats = {
            "total_sets": 0,
            "total_gets": 0,
            "total_deletes": 0,
            "total_rollbacks": 0,
        }

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def _full_key(self, key: str, namespace: str = "default") -> str:
        return f"{namespace}:{key}"

    # ------------------------------------------------------------------
    # Set / Get / Delete
    # ------------------------------------------------------------------

    def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        value_type: str = "any",
        description: str = "",
        readonly: bool = False,
        changed_by: str = "system",
    ) -> bool:
        """Set a configuration value. Returns False on validation failure."""
        if value_type != "any" and value_type not in VALID_TYPES:
            return False

        # Type validation
        if value_type != "any" and value_type in TYPE_MAP:
            if not isinstance(value, TYPE_MAP[value_type]):
                return False

        fk = self._full_key(key, namespace)
        existing = self._entries.get(fk)

        if existing:
            if existing.readonly:
                return False
            # Type must match if previously set with a type
            if existing.value_type != "any" and value_type == "any":
                value_type = existing.value_type
            if existing.value_type != "any" and existing.value_type in TYPE_MAP:
                if not isinstance(value, TYPE_MAP[existing.value_type]):
                    return False

            old_value = copy.deepcopy(existing.value)
            existing.value = copy.deepcopy(value)
            existing.updated_at = time.time()
            if description:
                existing.description = description

            self._record_change(key, namespace, old_value, value, changed_by)
        else:
            now = time.time()
            self._entries[fk] = ConfigEntry(
                key=key,
                namespace=namespace,
                value=copy.deepcopy(value),
                value_type=value_type,
                default=copy.deepcopy(value),
                description=description,
                readonly=readonly,
                created_at=now,
                updated_at=now,
            )

        self._stats["total_sets"] += 1

        if len(self._entries) > self._max_entries:
            self._prune()

        return True

    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        """Get a configuration value."""
        self._stats["total_gets"] += 1
        fk = self._full_key(key, namespace)
        entry = self._entries.get(fk)
        if not entry:
            return default
        return copy.deepcopy(entry.value)

    def get_entry(self, key: str, namespace: str = "default") -> Optional[Dict]:
        """Get full entry info."""
        fk = self._full_key(key, namespace)
        entry = self._entries.get(fk)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete a configuration entry."""
        fk = self._full_key(key, namespace)
        entry = self._entries.get(fk)
        if not entry:
            return False
        if entry.readonly:
            return False
        del self._entries[fk]
        self._stats["total_deletes"] += 1
        return True

    def exists(self, key: str, namespace: str = "default") -> bool:
        """Check if a key exists."""
        return self._full_key(key, namespace) in self._entries

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def set_many(self, entries: Dict[str, Any], namespace: str = "default", changed_by: str = "system") -> int:
        """Set multiple values. Returns count of successful sets."""
        count = 0
        for key, value in entries.items():
            if self.set(key, value, namespace=namespace, changed_by=changed_by):
                count += 1
        return count

    def get_many(self, keys: List[str], namespace: str = "default") -> Dict[str, Any]:
        """Get multiple values."""
        result = {}
        for key in keys:
            val = self.get(key, namespace)
            if val is not None:
                result[key] = val
        return result

    def get_namespace(self, namespace: str) -> Dict[str, Any]:
        """Get all entries in a namespace."""
        result = {}
        for entry in self._entries.values():
            if entry.namespace == namespace:
                result[entry.key] = copy.deepcopy(entry.value)
        return result

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self, change_id: str) -> bool:
        """Rollback a specific change."""
        change = None
        for c in self._history:
            if c.change_id == change_id:
                change = c
                break
        if not change:
            return False

        fk = self._full_key(change.key, change.namespace)
        entry = self._entries.get(fk)
        if not entry or entry.readonly:
            return False

        entry.value = copy.deepcopy(change.old_value)
        entry.updated_at = time.time()
        self._stats["total_rollbacks"] += 1
        return True

    def reset_to_defaults(self, namespace: str = "default") -> int:
        """Reset all entries in a namespace to their defaults."""
        count = 0
        for entry in self._entries.values():
            if entry.namespace == namespace and not entry.readonly:
                if entry.value != entry.default:
                    entry.value = copy.deepcopy(entry.default)
                    entry.updated_at = time.time()
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def save_profile(self, profile_name: str, namespace: str = "default") -> bool:
        """Save current namespace config as a named profile."""
        data = {}
        for fk, entry in self._entries.items():
            if entry.namespace == namespace:
                data[fk] = copy.deepcopy(entry.value)
        if not data:
            return False
        self._profiles[profile_name] = data
        return True

    def load_profile(self, profile_name: str, changed_by: str = "system") -> bool:
        """Load a saved profile, applying its values."""
        profile = self._profiles.get(profile_name)
        if not profile:
            return False

        for fk, value in profile.items():
            entry = self._entries.get(fk)
            if entry and not entry.readonly:
                old_value = copy.deepcopy(entry.value)
                entry.value = copy.deepcopy(value)
                entry.updated_at = time.time()
                self._record_change(entry.key, entry.namespace, old_value, value, changed_by)

        return True

    def delete_profile(self, profile_name: str) -> bool:
        """Delete a saved profile."""
        if profile_name not in self._profiles:
            return False
        del self._profiles[profile_name]
        return True

    def list_profiles(self) -> List[str]:
        """List saved profile names."""
        return list(self._profiles.keys())

    # ------------------------------------------------------------------
    # Change history
    # ------------------------------------------------------------------

    def get_history(
        self,
        key: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get change history."""
        results = self._history
        if key:
            results = [c for c in results if c.key == key]
        if namespace:
            results = [c for c in results if c.namespace == namespace]
        results = results[-limit:]
        return [
            {
                "change_id": c.change_id,
                "key": c.key,
                "namespace": c.namespace,
                "old_value": c.old_value,
                "new_value": c.new_value,
                "changed_by": c.changed_by,
                "timestamp": c.timestamp,
            }
            for c in results
        ]

    # ------------------------------------------------------------------
    # Listing & search
    # ------------------------------------------------------------------

    def list_keys(self, namespace: str = "default") -> List[str]:
        """List all keys in a namespace."""
        return [e.key for e in self._entries.values() if e.namespace == namespace]

    def list_namespaces(self) -> Dict[str, int]:
        """List namespaces with entry counts."""
        counts: Dict[str, int] = defaultdict(int)
        for entry in self._entries.values():
            counts[entry.namespace] += 1
        return dict(sorted(counts.items()))

    def search(self, query: str, namespace: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Search entries by key or description."""
        q = query.lower()
        results = []
        for entry in self._entries.values():
            if namespace and entry.namespace != namespace:
                continue
            if q in entry.key.lower() or q in entry.description.lower():
                results.append(self._entry_to_dict(entry))
                if len(results) >= limit:
                    break
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record_change(self, key: str, namespace: str, old_value: Any, new_value: Any, changed_by: str) -> None:
        change = ConfigChange(
            change_id=f"cc-{uuid.uuid4().hex[:8]}",
            key=key,
            namespace=namespace,
            old_value=copy.deepcopy(old_value),
            new_value=copy.deepcopy(new_value),
            changed_by=changed_by,
            timestamp=time.time(),
        )
        self._history.append(change)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        for cb in self._callbacks.values():
            try:
                cb(key, namespace, old_value, new_value)
            except Exception:
                pass

    def _prune(self) -> None:
        """Remove oldest non-readonly entries."""
        entries = [(fk, e) for fk, e in self._entries.items() if not e.readonly]
        entries.sort(key=lambda x: x[1].updated_at)
        to_remove = len(self._entries) - self._max_entries
        for fk, _ in entries[:to_remove]:
            del self._entries[fk]

    def _entry_to_dict(self, entry: ConfigEntry) -> Dict:
        return {
            "key": entry.key,
            "namespace": entry.namespace,
            "value": copy.deepcopy(entry.value),
            "value_type": entry.value_type,
            "default": copy.deepcopy(entry.default),
            "description": entry.description,
            "readonly": entry.readonly,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_entries": len(self._entries),
            "total_namespaces": len(set(e.namespace for e in self._entries.values())),
            "total_profiles": len(self._profiles),
            "total_history": len(self._history),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._history.clear()
        self._profiles.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
