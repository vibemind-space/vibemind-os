"""Pipeline State Store – persistent key-value state management for pipelines.

Provides namespaced key-value storage with versioning, TTL-based expiry,
atomic compare-and-set operations, and state history tracking.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _StateEntry:
    key: str
    namespace: str
    value: Any
    version: int
    ttl_ms: float  # 0 = no expiry
    created_at: float
    updated_at: float
    expires_at: float  # 0 = never
    seq: int


@dataclass
class _HistoryEntry:
    history_id: str
    key: str
    namespace: str
    old_value: Any
    new_value: Any
    version: int
    timestamp: float
    seq: int


class PipelineStateStore:
    """Namespaced key-value state store with versioning."""

    def __init__(self, max_entries: int = 100000,
                 max_history: int = 500000) -> None:
        self._max_entries = max_entries
        self._max_history = max_history
        self._entries: Dict[str, _StateEntry] = {}  # composite key -> entry
        self._history: Dict[str, _HistoryEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_sets": 0,
            "total_gets": 0,
            "total_deletes": 0,
            "total_cas_attempts": 0,
            "total_cas_successes": 0,
        }

    def _make_key(self, key: str, namespace: str) -> str:
        return f"{namespace}::{key}"

    def _is_expired(self, entry: _StateEntry) -> bool:
        if entry.expires_at <= 0:
            return False
        return time.time() > entry.expires_at

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any, namespace: str = "default",
            ttl_ms: float = 0.0) -> bool:
        if not key:
            return False
        ck = self._make_key(key, namespace)
        existing = self._entries.get(ck)
        if existing and not self._is_expired(existing):
            # Update existing
            old_value = existing.value
            existing.version += 1
            existing.value = value
            existing.updated_at = time.time()
            if ttl_ms > 0:
                existing.ttl_ms = ttl_ms
                existing.expires_at = time.time() + ttl_ms / 1000.0
            self._record_history(key, namespace, old_value, value, existing.version)
        else:
            # New entry
            if existing:
                del self._entries[ck]  # expired
            if len(self._entries) >= self._max_entries:
                return False
            self._seq += 1
            now = time.time()
            entry = _StateEntry(
                key=key, namespace=namespace, value=value, version=1,
                ttl_ms=ttl_ms, created_at=now, updated_at=now,
                expires_at=now + ttl_ms / 1000.0 if ttl_ms > 0 else 0.0,
                seq=self._seq,
            )
            self._entries[ck] = entry
            self._record_history(key, namespace, None, value, 1)
        self._stats["total_sets"] += 1
        self._fire("state_set", {"key": key, "namespace": namespace})
        return True

    def get(self, key: str, namespace: str = "default",
            default: Any = None) -> Any:
        ck = self._make_key(key, namespace)
        entry = self._entries.get(ck)
        if entry is None:
            return default
        if self._is_expired(entry):
            del self._entries[ck]
            return default
        self._stats["total_gets"] += 1
        return entry.value

    def delete(self, key: str, namespace: str = "default") -> bool:
        ck = self._make_key(key, namespace)
        if ck not in self._entries:
            return False
        del self._entries[ck]
        self._stats["total_deletes"] += 1
        self._fire("state_deleted", {"key": key, "namespace": namespace})
        return True

    def exists(self, key: str, namespace: str = "default") -> bool:
        ck = self._make_key(key, namespace)
        entry = self._entries.get(ck)
        if entry is None:
            return False
        if self._is_expired(entry):
            del self._entries[ck]
            return False
        return True

    def get_version(self, key: str, namespace: str = "default") -> int:
        ck = self._make_key(key, namespace)
        entry = self._entries.get(ck)
        if entry is None or self._is_expired(entry):
            return 0
        return entry.version

    # ------------------------------------------------------------------
    # Compare-and-set
    # ------------------------------------------------------------------

    def compare_and_set(self, key: str, expected_value: Any, new_value: Any,
                        namespace: str = "default") -> bool:
        self._stats["total_cas_attempts"] += 1
        ck = self._make_key(key, namespace)
        entry = self._entries.get(ck)
        if entry is None or self._is_expired(entry):
            return False
        if entry.value != expected_value:
            return False
        old_value = entry.value
        entry.value = new_value
        entry.version += 1
        entry.updated_at = time.time()
        self._record_history(key, namespace, old_value, new_value, entry.version)
        self._stats["total_cas_successes"] += 1
        self._fire("state_cas", {"key": key, "namespace": namespace})
        return True

    # ------------------------------------------------------------------
    # Namespace operations
    # ------------------------------------------------------------------

    def get_namespace_keys(self, namespace: str = "default") -> List[str]:
        keys = []
        expired = []
        for ck, entry in self._entries.items():
            if entry.namespace != namespace:
                continue
            if self._is_expired(entry):
                expired.append(ck)
                continue
            keys.append(entry.key)
        for ck in expired:
            del self._entries[ck]
        return sorted(keys)

    def clear_namespace(self, namespace: str) -> int:
        to_remove = [ck for ck, e in self._entries.items() if e.namespace == namespace]
        for ck in to_remove:
            del self._entries[ck]
        return len(to_remove)

    def get_namespaces(self) -> List[str]:
        ns = set()
        for entry in self._entries.values():
            ns.add(entry.namespace)
        return sorted(ns)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, key: str, namespace: str,
                        old_value: Any, new_value: Any, version: int) -> None:
        if len(self._history) >= self._max_history:
            return
        self._seq += 1
        raw = f"hist-{key}-{namespace}-{self._seq}-{len(self._history)}"
        hid = "hist-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        h = _HistoryEntry(
            history_id=hid, key=key, namespace=namespace,
            old_value=old_value, new_value=new_value, version=version,
            timestamp=time.time(), seq=self._seq,
        )
        self._history[hid] = h

    def get_history(self, key: str, namespace: str = "default",
                    limit: int = 50) -> List[Dict]:
        results = []
        for h in self._history.values():
            if h.key != key or h.namespace != namespace:
                continue
            results.append({
                "history_id": h.history_id,
                "key": h.key,
                "namespace": h.namespace,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "version": h.version,
                "timestamp": h.timestamp,
            })
        results.sort(key=lambda x: x["version"])
        if limit > 0:
            results = results[-limit:]
        return results

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def get_all(self, namespace: str = "default") -> Dict[str, Any]:
        result = {}
        expired = []
        for ck, entry in self._entries.items():
            if entry.namespace != namespace:
                continue
            if self._is_expired(entry):
                expired.append(ck)
                continue
            result[entry.key] = entry.value
        for ck in expired:
            del self._entries[ck]
        return result

    def set_many(self, items: Dict[str, Any],
                 namespace: str = "default") -> int:
        count = 0
        for key, value in items.items():
            if self.set(key, value, namespace):
                count += 1
        return count

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "current_history": len(self._history),
            "namespaces": len(self.get_namespaces()),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._history.clear()
        self._seq = 0
        self._stats = {
            "total_sets": 0,
            "total_gets": 0,
            "total_deletes": 0,
            "total_cas_attempts": 0,
            "total_cas_successes": 0,
        }
