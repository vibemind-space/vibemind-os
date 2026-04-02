"""Service module for encrypting pipeline data entries with configurable algorithms."""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataEncryptorV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataEncryptorV2:
    """Encrypts pipeline data entries with support for multiple algorithms."""

    PREFIX = "pdec-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataEncryptorV2State()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", ""),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = max(1, len(self._state.entries) // 4)
            for key in sorted_keys[:quarter]:
                del self._state.entries[key]

    # -- Callbacks -----------------------------------------------------------

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

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # -- Core methods --------------------------------------------------------

    def encrypt_v2(
        self,
        pipeline_id: str,
        data_key: str,
        algorithm: str = "aes256",
        metadata: Optional[dict] = None,
    ) -> str:
        """Encrypt a pipeline data entry. Returns record_id or empty string on failure."""
        if not pipeline_id or not data_key:
            return ""

        self._prune()

        record_id = self._generate_id()
        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "algorithm": algorithm,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._fire("encrypt_v2", pipeline_id=pipeline_id, record_id=record_id)
        return record_id

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
            key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)),
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
        self._state = PipelineDataEncryptorV2State()
        self._on_change = None
