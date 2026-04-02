"""Service module for encoding and decoding pipeline data in various formats."""

from __future__ import annotations

import base64
import hashlib
import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataEncoderState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataEncoder:
    """Encode and decode pipeline data in various formats (base64, hex, url-encoding)."""

    PREFIX = "pden-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataEncoderState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

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

    def encode(self, data: str, encoding: str = "base64") -> str:
        """Encode a string using the specified encoding format."""
        if encoding == "base64":
            return base64.b64encode(data.encode()).decode()
        elif encoding == "hex":
            return data.encode().hex()
        elif encoding == "url":
            return urllib.parse.quote(data)
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")

    def decode(self, data: str, encoding: str = "base64") -> str:
        """Decode a string using the specified encoding format."""
        if encoding == "base64":
            return base64.b64decode(data.encode()).decode()
        elif encoding == "hex":
            return bytes.fromhex(data).decode()
        elif encoding == "url":
            return urllib.parse.unquote(data)
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")

    def register_encoding(self, name: str, encoding: str = "base64", metadata: Optional[dict] = None) -> str:
        """Register an encoding configuration. Returns config_id."""
        config_id = self._generate_id(name)
        self._state.entries[config_id] = {
            "config_id": config_id,
            "name": name,
            "encoding": encoding,
            "metadata": metadata,
            "created_at": time.time(),
            "usage_count": 0,
        }
        self._prune()
        self._fire("register", {"config_id": config_id, "name": name})
        return config_id

    def apply_encoding(self, config_id: str, data: str) -> dict:
        """Apply a registered encoding configuration to data."""
        entry = self._state.entries.get(config_id)
        if entry is None:
            return {}
        encoded = self.encode(data, entry["encoding"])
        entry["usage_count"] += 1
        return {
            "config_id": config_id,
            "encoded": encoded,
            "original_length": len(data),
            "encoded_length": len(encoded),
        }

    def get_encoding(self, config_id: str) -> dict:
        """Return encoding config info."""
        entry = self._state.entries.get(config_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_encodings(self) -> list:
        """List all registered encoding configs."""
        return [dict(e) for e in self._state.entries.values()]

    def get_encoding_count(self) -> int:
        """Return number of registered encoding configs."""
        return len(self._state.entries)

    def remove_encoding(self, config_id: str) -> bool:
        """Remove an encoding config."""
        if config_id in self._state.entries:
            del self._state.entries[config_id]
            self._fire("remove", {"config_id": config_id})
            return True
        return False

    def get_stats(self) -> dict:
        """Return statistics."""
        total_operations = sum(e.get("usage_count", 0) for e in self._state.entries.values())
        return {
            "total_encodings": len(self._state.entries),
            "total_operations": total_operations,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataEncoderState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
