"""Agent Preference Store -- manages agent behavior preferences.

Provides configurable preference storage that affects how agents behave,
with per-agent, per-category key-value preferences, import/export,
max-entries pruning, callbacks, and thread-safe access.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PreferenceRecord:
    pref_id: str
    agent_id: str
    category: str
    key: str
    value: Any
    metadata: Optional[Dict[str, Any]]
    created_at: float
    updated_at: float
    seq: int


class AgentPreferenceStore:
    """Manages agent behavior preferences (per-agent, per-category key-value store)."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, PreferenceRecord] = {}
        self._lookup: Dict[str, str] = {}  # "agent_id:category:key" -> pref_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_sets = 0
        self._total_gets = 0
        self._total_deletes = 0
        self._total_imports = 0
        self._total_exports = 0
        self._total_evictions = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"ape-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ape-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already registered."""
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name. Returns False if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        with self._lock:
            callbacks = list(self._callbacks.values())
        for cb in callbacks:
            try:
                cb(action, detail)
            except Exception:
                logger.debug("callback_error", exc_info=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_lookup_key(agent_id: str, category: str, key: str) -> str:
        return f"{agent_id}:{category}:{key}"

    def _prune_if_needed(self) -> None:
        """Prune oldest entries when max_entries is exceeded. Caller must hold lock."""
        if len(self._entries) < self._max_entries:
            return

        sorted_ids = sorted(
            self._entries.keys(),
            key=lambda eid: self._entries[eid].seq,
        )
        to_remove = len(self._entries) - self._max_entries + 1
        for eid in sorted_ids[:to_remove]:
            entry = self._entries[eid]
            lk = self._make_lookup_key(entry.agent_id, entry.category, entry.key)
            self._lookup.pop(lk, None)
            del self._entries[eid]
            self._total_evictions += 1
            logger.debug("preference_evicted pref_id=%s agent_id=%s", eid, entry.agent_id)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def set_preference(
        self,
        agent_id: str,
        category: str,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Set a preference. Returns pref_id. Updates existing if same agent+category+key."""
        if not agent_id or not category or not key:
            logger.warning(
                "set_preference_invalid_args agent_id=%s category=%s key=%s",
                agent_id, category, key,
            )
            return ""

        lk = self._make_lookup_key(agent_id, category, key)
        now = time.time()

        with self._lock:
            existing_eid = self._lookup.get(lk)
            if existing_eid and existing_eid in self._entries:
                entry = self._entries[existing_eid]
                old_value = entry.value
                entry.value = value
                entry.updated_at = now
                if metadata is not None:
                    entry.metadata = metadata
                self._seq += 1
                entry.seq = self._seq
                self._total_sets += 1
                pref_id = existing_eid

            else:
                self._prune_if_needed()
                pref_id = self._gen_id(f"{agent_id}-{category}-{key}")
                entry = PreferenceRecord(
                    pref_id=pref_id,
                    agent_id=agent_id,
                    category=category,
                    key=key,
                    value=value,
                    metadata=metadata,
                    created_at=now,
                    updated_at=now,
                    seq=self._seq,
                )
                self._entries[pref_id] = entry
                self._lookup[lk] = pref_id
                self._total_sets += 1
                old_value = None

        logger.debug(
            "preference_set agent_id=%s category=%s key=%s pref_id=%s",
            agent_id, category, key, pref_id,
        )
        self._fire("preference_set", {
            "pref_id": pref_id,
            "agent_id": agent_id,
            "category": category,
            "key": key,
            "value": value,
            "old_value": old_value,
            "metadata": metadata,
        })
        return pref_id

    def get_preference(
        self,
        agent_id: str,
        category: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """Get a preference value. Returns default if not found."""
        if not agent_id or not category or not key:
            return default

        lk = self._make_lookup_key(agent_id, category, key)
        with self._lock:
            self._total_gets += 1
            eid = self._lookup.get(lk)
            if eid and eid in self._entries:
                return self._entries[eid].value
        return default

    def get_agent_preferences(
        self,
        agent_id: str,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all preferences for an agent, optionally filtered by category."""
        if not agent_id:
            return []

        with self._lock:
            self._total_gets += 1
            results: List[Dict[str, Any]] = []
            for entry in self._entries.values():
                if entry.agent_id != agent_id:
                    continue
                if category is not None and entry.category != category:
                    continue
                results.append(asdict(entry))
        return results

    def delete_preference(self, agent_id: str, category: str, key: str) -> bool:
        """Delete a preference. Returns False if not found."""
        if not agent_id or not category or not key:
            return False

        lk = self._make_lookup_key(agent_id, category, key)
        with self._lock:
            eid = self._lookup.get(lk)
            if not eid or eid not in self._entries:
                return False

            entry = self._entries[eid]
            detail = asdict(entry)
            del self._entries[eid]
            del self._lookup[lk]
            self._total_deletes += 1

        logger.debug(
            "preference_deleted agent_id=%s category=%s key=%s",
            agent_id, category, key,
        )
        self._fire("preference_deleted", detail)
        return True

    def clear_agent_preferences(self, agent_id: str) -> int:
        """Clear all preferences for an agent. Returns count deleted."""
        if not agent_id:
            return 0

        with self._lock:
            to_delete: List[str] = []
            for eid, entry in self._entries.items():
                if entry.agent_id == agent_id:
                    to_delete.append(eid)

            for eid in to_delete:
                entry = self._entries[eid]
                lk = self._make_lookup_key(entry.agent_id, entry.category, entry.key)
                self._lookup.pop(lk, None)
                del self._entries[eid]
            self._total_deletes += len(to_delete)

        if to_delete:
            logger.debug(
                "agent_preferences_cleared agent_id=%s count=%d",
                agent_id, len(to_delete),
            )
            self._fire("agent_preferences_cleared", {
                "agent_id": agent_id,
                "count": len(to_delete),
            })
        return len(to_delete)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_all_categories(self, agent_id: Optional[str] = None) -> List[str]:
        """List all categories, optionally filtered to a specific agent."""
        with self._lock:
            categories: set[str] = set()
            for entry in self._entries.values():
                if agent_id is not None and entry.agent_id != agent_id:
                    continue
                categories.add(entry.category)
        return sorted(categories)

    def list_agents(self) -> List[str]:
        """List all agent IDs that have preferences."""
        with self._lock:
            agents: set[str] = set()
            for entry in self._entries.values():
                agents.add(entry.agent_id)
        return sorted(agents)

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def export_preferences(self, agent_id: str) -> Dict[str, Dict[str, Any]]:
        """Export all preferences for an agent as {category: {key: value}}."""
        if not agent_id:
            return {}

        with self._lock:
            self._total_exports += 1
            result: Dict[str, Dict[str, Any]] = {}
            for entry in self._entries.values():
                if entry.agent_id != agent_id:
                    continue
                if entry.category not in result:
                    result[entry.category] = {}
                result[entry.category][entry.key] = entry.value

        logger.debug(
            "preferences_exported agent_id=%s categories=%d",
            agent_id, len(result),
        )
        return result

    def import_preferences(self, agent_id: str, prefs_dict: Dict[str, Dict[str, Any]]) -> int:
        """Import preferences from {category: {key: value}}. Returns count imported."""
        if not agent_id or not isinstance(prefs_dict, dict):
            return 0

        count = 0
        for category, kv_pairs in prefs_dict.items():
            if not isinstance(category, str) or not category:
                continue
            if not isinstance(kv_pairs, dict):
                continue
            for key, value in kv_pairs.items():
                if not isinstance(key, str) or not key:
                    continue
                self.set_preference(agent_id, category, key, value)
                count += 1

        with self._lock:
            self._total_imports += 1

        logger.debug(
            "preferences_imported agent_id=%s count=%d", agent_id, count,
        )
        self._fire("preferences_imported", {
            "agent_id": agent_id,
            "count": count,
        })
        return count

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return store statistics."""
        with self._lock:
            unique_agents = len({e.agent_id for e in self._entries.values()})
            unique_categories = len({e.category for e in self._entries.values()})
            return {
                "current_entries": len(self._entries),
                "unique_agents": unique_agents,
                "unique_categories": unique_categories,
                "max_entries": self._max_entries,
                "total_sets": self._total_sets,
                "total_gets": self._total_gets,
                "total_deletes": self._total_deletes,
                "total_imports": self._total_imports,
                "total_exports": self._total_exports,
                "total_evictions": self._total_evictions,
                "callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all state and counters."""
        with self._lock:
            self._entries.clear()
            self._lookup.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_sets = 0
            self._total_gets = 0
            self._total_deletes = 0
            self._total_imports = 0
            self._total_exports = 0
            self._total_evictions = 0
        logger.debug("agent_preference_store_reset")
