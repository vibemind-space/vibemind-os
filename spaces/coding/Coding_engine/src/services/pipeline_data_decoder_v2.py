"""Pipeline data decoder v2 service."""

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataDecoderV2State:
    """State container for PipelineDataDecoderV2."""

    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataDecoderV2:
    """Decodes pipeline data with tracking and callback support."""

    PREFIX = "pddv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataDecoderV2State()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        """Generate a unique id using sequence and sha256."""
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        hash_val = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{hash_val[:12]}"

    def _prune(self) -> None:
        """Remove oldest quarter of entries if over MAX_ENTRIES."""
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: (
                    self._state.entries[k]["created_at"],
                    self._state.entries[k]["_seq"],
                ),
            )
            remove_count = self.MAX_ENTRIES // 4
            for key in sorted_keys[:remove_count]:
                del self._state.entries[key]

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback. Returns True if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        """Fire callbacks with the given action and details."""
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback failed for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("Callback failed for action=%s", action)

    def decode_v2(
        self,
        pipeline_id: str,
        data_key: str,
        encoding: str = "utf8",
        metadata: Optional[dict] = None,
    ) -> str:
        """Decode pipeline data and store a record. Returns record_id or empty string."""
        if not pipeline_id or not data_key:
            return ""

        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()

        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "encoding": encoding,
            "metadata": deepcopy(metadata) if metadata else None,
            "created_at": now,
            "_seq": self._state._seq,
        }

        self._state.entries[record_id] = entry
        self._prune()
        self._fire("decode_v2", pipeline_id=pipeline_id, record_id=record_id)
        return record_id

    def get_decoding(self, record_id: str) -> Optional[dict]:
        """Get a single decoding entry by record_id (deep copy)."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return deepcopy(entry)

    def get_decodings(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get decodings, optionally filtered by pipeline_id, sorted newest first."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [deepcopy(e) for e in entries[:limit]]

    def get_decoding_count(self, pipeline_id: str = "") -> int:
        """Count decodings, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_pipelines = {
            e["pipeline_id"] for e in self._state.entries.values()
        }
        return {
            "total_decodings": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineDataDecoderV2State()
        self._on_change = None
