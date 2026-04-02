"""Service module for encrypting pipeline data entries with configurable algorithms."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataEncryptorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataEncryptor:
    """Encrypts pipeline data entries with support for multiple algorithms."""

    PREFIX = "pden-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataEncryptorState()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"{self.PREFIX}{digest}"

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) >= self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = max(1, len(self._state.entries) // 4)
            for key in sorted_keys[:quarter]:
                del self._state.entries[key]

    # -- Callbacks -----------------------------------------------------------

    def _fire(self, action: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def encrypt(
        self,
        pipeline_id: str,
        data_key: str,
        algorithm: str = "aes256",
        metadata: Optional[dict] = None,
    ) -> str:
        """Encrypt a pipeline data entry. Returns record_id or empty string on failure."""
        try:
            if not pipeline_id or not pipeline_id.strip():
                return ""
            if not data_key or not data_key.strip():
                return ""

            self._prune()

            record_id = self._generate_id()
            entry: Dict[str, Any] = {
                "record_id": record_id,
                "pipeline_id": pipeline_id,
                "data_key": data_key,
                "algorithm": algorithm,
                "metadata": copy.deepcopy(metadata) if metadata is not None else None,
                "created_at": time.time(),
                "_seq": self._state._seq,
            }
            self._state.entries[record_id] = entry
            self._fire("encrypted", {"record_id": record_id, "pipeline_id": pipeline_id})
            return record_id
        except Exception:
            logger.error("Failed to encrypt pipeline data")
            return ""

    def get_encryption(self, record_id: str) -> Optional[dict]:
        """Return a copy of the encryption entry or None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_encryptions(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return encryption entries, optionally filtered by pipeline_id, newest first."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_encryption_count(self, pipeline_id: str = "") -> int:
        """Return the number of encryption entries, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return statistics about encryption entries."""
        unique_pipelines = set(
            e.get("pipeline_id") for e in self._state.entries.values()
        )
        return {
            "total_encryptions": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataEncryptorState()
        self._on_change = None
