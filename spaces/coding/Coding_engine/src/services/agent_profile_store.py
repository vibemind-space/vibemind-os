"""Agent Profile Store – manages agent profiles with metadata and preferences.

Provides storage for agent profiles including display names, roles,
metadata, and per-agent preferences.  Supports search, filtering,
change callbacks, and automatic pruning.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Internal data model
# -------------------------------------------------------------------

@dataclass
class ProfileRecord:
    """Internal representation of a single agent profile."""

    profile_id: str
    agent_id: str
    display_name: str
    role: str
    metadata: Dict[str, Any]
    preferences: Dict[str, Any]
    created_at: float
    updated_at: float
    seq: int


# -------------------------------------------------------------------
# Store
# -------------------------------------------------------------------

class AgentProfileStore:
    """Thread-safe store for agent profiles, preferences, and metadata."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries

        # primary storage: profile_id -> ProfileRecord
        self._profiles: Dict[str, ProfileRecord] = {}

        # secondary index: agent_id -> profile_id  (one profile per agent)
        self._agent_index: Dict[str, str] = {}

        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._seq: int = 0

        # cumulative counters
        self._total_creates: int = 0
        self._total_updates: int = 0
        self._total_deletes: int = 0
        self._total_gets: int = 0
        self._total_searches: int = 0
        self._total_pref_sets: int = 0
        self._total_pref_gets: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        """Generate a unique profile ID with prefix ``apr-``."""
        self._seq += 1
        raw = f"apr-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"apr-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns *False* if *name* exists."""
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *detail*."""
        with self._lock:
            targets = list(self._callbacks.values())
        for cb in targets:
            try:
                cb(action, detail)
            except Exception:
                logger.debug("callback_error", exc_info=True)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict oldest profiles when *max_entries* is exceeded.

        Must be called while ``self._lock`` is held.
        """
        if len(self._profiles) < self._max_entries:
            return
        sorted_ids = sorted(
            self._profiles.keys(),
            key=lambda pid: self._profiles[pid].seq,
        )
        to_remove = len(self._profiles) - self._max_entries + 1
        for pid in sorted_ids[:to_remove]:
            record = self._profiles[pid]
            self._agent_index.pop(record.agent_id, None)
            del self._profiles[pid]
            logger.debug("pruned_profile agent_id=%s profile_id=%s", record.agent_id, pid)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _record_to_dict(record: ProfileRecord) -> Dict[str, Any]:
        """Convert a *ProfileRecord* to a plain dictionary."""
        return {
            "profile_id": record.profile_id,
            "agent_id": record.agent_id,
            "display_name": record.display_name,
            "role": record.role,
            "metadata": dict(record.metadata),
            "preferences": dict(record.preferences),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_profile(
        self,
        agent_id: str,
        display_name: str = "",
        role: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new agent profile.

        Returns the generated ``profile_id`` (prefixed ``apr-``), or an
        empty string if a profile for *agent_id* already exists.
        """
        if not agent_id:
            return ""

        with self._lock:
            if agent_id in self._agent_index:
                return ""

            self._prune_if_needed()

            now = time.time()
            pid = self._gen_id(agent_id)
            record = ProfileRecord(
                profile_id=pid,
                agent_id=agent_id,
                display_name=display_name,
                role=role,
                metadata=dict(metadata) if metadata else {},
                preferences={},
                created_at=now,
                updated_at=now,
                seq=self._seq,
            )
            self._profiles[pid] = record
            self._agent_index[agent_id] = pid
            self._total_creates += 1

        logger.debug("profile_created agent_id=%s profile_id=%s", agent_id, pid)
        self._fire("profile_created", {
            "profile_id": pid,
            "agent_id": agent_id,
            "display_name": display_name,
            "role": role,
        })
        return pid

    def get_profile(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the profile dict for *agent_id*, or ``None``."""
        if not agent_id:
            return None

        with self._lock:
            self._total_gets += 1
            pid = self._agent_index.get(agent_id)
            if pid is None or pid not in self._profiles:
                return None
            return self._record_to_dict(self._profiles[pid])

    def update_profile(self, agent_id: str, **kwargs: Any) -> bool:
        """Update mutable profile fields.

        Accepted keyword arguments: ``display_name``, ``role``, ``metadata``.
        Returns ``False`` if the profile is not found.
        """
        if not agent_id:
            return False

        allowed_keys = {"display_name", "role", "metadata"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_keys}
        if not updates:
            return False

        with self._lock:
            pid = self._agent_index.get(agent_id)
            if pid is None or pid not in self._profiles:
                return False

            record = self._profiles[pid]
            now = time.time()

            if "display_name" in updates:
                record.display_name = updates["display_name"]
            if "role" in updates:
                record.role = updates["role"]
            if "metadata" in updates:
                record.metadata = dict(updates["metadata"]) if updates["metadata"] else {}

            record.updated_at = now
            self._seq += 1
            record.seq = self._seq
            self._total_updates += 1

        logger.debug("profile_updated agent_id=%s fields=%s", agent_id, list(updates.keys()))
        self._fire("profile_updated", {
            "agent_id": agent_id,
            "updated_fields": list(updates.keys()),
        })
        return True

    def delete_profile(self, agent_id: str) -> bool:
        """Delete the profile for *agent_id*.  Returns ``False`` if not found."""
        if not agent_id:
            return False

        with self._lock:
            pid = self._agent_index.get(agent_id)
            if pid is None or pid not in self._profiles:
                return False

            record = self._profiles[pid]
            del self._profiles[pid]
            del self._agent_index[agent_id]
            self._total_deletes += 1

        logger.debug("profile_deleted agent_id=%s profile_id=%s", agent_id, pid)
        self._fire("profile_deleted", {
            "profile_id": pid,
            "agent_id": agent_id,
            "role": record.role,
        })
        return True

    # ------------------------------------------------------------------
    # Listing / Filtering
    # ------------------------------------------------------------------

    def list_profiles(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all profiles, optionally filtered by *role*."""
        with self._lock:
            results: List[Dict[str, Any]] = []
            for record in self._profiles.values():
                if role is not None and record.role != role:
                    continue
                results.append(self._record_to_dict(record))
        return results

    def get_profiles_by_role(self, role: str) -> List[Dict[str, Any]]:
        """Return all profiles that have the given *role*."""
        if not role:
            return []
        return self.list_profiles(role=role)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_profiles(self, query: str) -> List[Dict[str, Any]]:
        """Search profiles by substring in *display_name* or *agent_id*.

        The comparison is case-insensitive.  Returns a list of matching
        profile dicts.
        """
        if not query:
            return []

        needle = query.lower()
        with self._lock:
            self._total_searches += 1
            results: List[Dict[str, Any]] = []
            for record in self._profiles.values():
                if (
                    needle in record.agent_id.lower()
                    or needle in record.display_name.lower()
                ):
                    results.append(self._record_to_dict(record))
        return results

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def set_preference(self, agent_id: str, key: str, value: Any) -> bool:
        """Set a preference *key*/*value* on the agent's profile.

        Returns ``False`` if the profile does not exist.
        """
        if not agent_id or not key:
            return False

        with self._lock:
            pid = self._agent_index.get(agent_id)
            if pid is None or pid not in self._profiles:
                return False

            record = self._profiles[pid]
            old_value = record.preferences.get(key)
            record.preferences[key] = value
            record.updated_at = time.time()
            self._seq += 1
            record.seq = self._seq
            self._total_pref_sets += 1

        logger.debug(
            "preference_set agent_id=%s key=%s",
            agent_id, key,
        )
        self._fire("preference_set", {
            "agent_id": agent_id,
            "key": key,
            "old_value": old_value,
            "new_value": value,
        })
        return True

    def get_preference(self, agent_id: str, key: str, default: Any = None) -> Any:
        """Retrieve a single preference value.

        Returns *default* if the profile or preference key is not found.
        """
        if not agent_id or not key:
            return default

        with self._lock:
            self._total_pref_gets += 1
            pid = self._agent_index.get(agent_id)
            if pid is None or pid not in self._profiles:
                return default
            return self._profiles[pid].preferences.get(key, default)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of cumulative store statistics."""
        with self._lock:
            unique_roles: set[str] = set()
            for record in self._profiles.values():
                if record.role:
                    unique_roles.add(record.role)

            return {
                "current_profiles": len(self._profiles),
                "max_entries": self._max_entries,
                "unique_roles": len(unique_roles),
                "total_creates": self._total_creates,
                "total_updates": self._total_updates,
                "total_deletes": self._total_deletes,
                "total_gets": self._total_gets,
                "total_searches": self._total_searches,
                "total_pref_sets": self._total_pref_sets,
                "total_pref_gets": self._total_pref_gets,
                "callbacks": len(self._callbacks),
                "seq": self._seq,
            }

    def reset(self) -> None:
        """Clear all profiles, indexes, callbacks, and counters."""
        with self._lock:
            self._profiles.clear()
            self._agent_index.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_creates = 0
            self._total_updates = 0
            self._total_deletes = 0
            self._total_gets = 0
            self._total_searches = 0
            self._total_pref_sets = 0
            self._total_pref_gets = 0
        logger.debug("agent_profile_store_reset")
