"""Service module for computing hashes of pipeline data for integrity verification and deduplication."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataHasherState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataHasher:
    """Compute hashes of pipeline data for integrity verification and deduplication."""

    PREFIX = "pdha-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataHasherState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        self._total_verifications = 0
        self._total_duplicates_found = 0

    # -- ID generation -------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{digest}"

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    # -- Callbacks -----------------------------------------------------------

    def _fire(self, event: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.error("on_change callback error for event %s", event)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.error("callback %s error for event %s", name, event)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def hash_data(self, data: str, algorithm: str = "sha256") -> str:
        """Hash a string using the specified algorithm. Returns hex digest."""
        if algorithm == "sha256":
            return hashlib.sha256(data.encode()).hexdigest()
        elif algorithm == "md5":
            return hashlib.md5(data.encode()).hexdigest()
        elif algorithm == "sha1":
            return hashlib.sha1(data.encode()).hexdigest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

    def register_hash(self, name: str, data: str, algorithm: str = "sha256") -> str:
        """Register and store a hash entry. Returns hash_id."""
        data_hash = self.hash_data(data, algorithm)
        hash_id = self._generate_id(data)
        self._state.entries[hash_id] = {
            "hash_id": hash_id,
            "name": name,
            "data_hash": data_hash,
            "algorithm": algorithm,
            "data_length": len(data),
            "created_at": time.time(),
        }
        self._prune()
        self._fire("register", {"hash_id": hash_id, "name": name})
        return hash_id

    def verify(self, hash_id: str, data: str) -> bool:
        """Verify data matches stored hash."""
        self._total_verifications += 1
        entry = self._state.entries.get(hash_id)
        if entry is None:
            return False
        computed = self.hash_data(data, entry["algorithm"])
        return computed == entry["data_hash"]

    def get_hash(self, hash_id: str) -> dict:
        """Return hash entry info."""
        entry = self._state.entries.get(hash_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_hashes(self) -> list:
        """List all stored hashes."""
        return [dict(e) for e in self._state.entries.values()]

    def find_duplicates(self, data: str, algorithm: str = "sha256") -> list:
        """Find entries with matching hash."""
        target_hash = self.hash_data(data, algorithm)
        results = []
        for entry in self._state.entries.values():
            if entry["algorithm"] == algorithm and entry["data_hash"] == target_hash:
                results.append(dict(entry))
        if results:
            self._total_duplicates_found += len(results)
        return results

    def get_hash_count(self) -> int:
        """Return number of stored hashes."""
        return len(self._state.entries)

    def remove_hash(self, hash_id: str) -> bool:
        """Remove a hash entry."""
        if hash_id in self._state.entries:
            del self._state.entries[hash_id]
            self._fire("remove", {"hash_id": hash_id})
            return True
        return False

    def get_stats(self) -> dict:
        """Return statistics."""
        return {
            "total_hashes": len(self._state.entries),
            "total_verifications": self._total_verifications,
            "total_duplicates_found": self._total_duplicates_found,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataHasherState()
        self._callbacks = {}
        self._on_change = None
        self._total_verifications = 0
        self._total_duplicates_found = 0
        self._fire("reset", {})
