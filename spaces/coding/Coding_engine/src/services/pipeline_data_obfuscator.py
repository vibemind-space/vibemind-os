"""Service module for obfuscating sensitive data fields in pipeline payloads."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataObfuscatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataObfuscator:
    """Obfuscates sensitive data fields in pipeline payloads with support for deobfuscation."""

    PREFIX = "pdo-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataObfuscatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
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

    def _fire(self, action: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._callbacks.items()):
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
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Obfuscation helpers -------------------------------------------------

    @staticmethod
    def _apply_strategy(value: Any, strategy: str) -> Any:
        """Apply the obfuscation strategy to a single value."""
        if strategy == "mask":
            return "***"
        elif strategy == "hash":
            return hashlib.sha256(str(value).encode()).hexdigest()
        elif strategy == "redact":
            return None  # sentinel for removal
        return "***"

    # -- Core methods --------------------------------------------------------

    def obfuscate(self, payload: dict, fields: List[str], strategy: str = "mask") -> str:
        """Create an obfuscation record. Applies the strategy to the specified fields.

        Strategies:
            - "mask": replace field values with "***"
            - "hash": replace field values with their SHA256 hex digest
            - "redact": remove the field entirely from the obfuscated payload

        Returns the record ID.
        """
        record_id = self._generate_id()
        original_payload = copy.deepcopy(payload)
        obfuscated_payload = copy.deepcopy(payload)
        fields_affected: List[str] = []

        for f in fields:
            if f in obfuscated_payload:
                result = self._apply_strategy(obfuscated_payload[f], strategy)
                if strategy == "redact":
                    del obfuscated_payload[f]
                else:
                    obfuscated_payload[f] = result
                fields_affected.append(f)

        self._state.entries[record_id] = {
            "id": record_id,
            "original_payload": original_payload,
            "obfuscated_payload": obfuscated_payload,
            "fields": fields_affected,
            "strategy": strategy,
            "pipeline_id": payload.get("pipeline_id", ""),
            "created_at": time.time(),
        }
        self._prune()
        self._fire("obfuscated", {"id": record_id, "strategy": strategy, "fields": fields_affected})
        logger.info("Obfuscated record %s (strategy=%s, fields=%s)", record_id, strategy, fields_affected)
        return record_id

    def get_record(self, record_id: str) -> Optional[dict]:
        """Get an obfuscation record by ID."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return {
            "id": entry["id"],
            "obfuscated_payload": copy.deepcopy(entry["obfuscated_payload"]),
            "fields": list(entry["fields"]),
            "strategy": entry["strategy"],
            "pipeline_id": entry["pipeline_id"],
            "created_at": entry["created_at"],
        }

    def get_records(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Query obfuscation records, newest first. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(key=lambda e: e.get("created_at", 0), reverse=True)
        entries = entries[:limit]
        results = []
        for entry in entries:
            results.append({
                "id": entry["id"],
                "obfuscated_payload": copy.deepcopy(entry["obfuscated_payload"]),
                "fields": list(entry["fields"]),
                "strategy": entry["strategy"],
                "pipeline_id": entry["pipeline_id"],
                "created_at": entry["created_at"],
            })
        return results

    def deobfuscate(self, record_id: str) -> Optional[dict]:
        """Return the original payload from a record."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry["original_payload"])

    def get_stats(self) -> dict:
        """Return statistics about obfuscation records."""
        entries = self._state.entries
        strategies_used: Dict[str, int] = {}
        fields_obfuscated: Dict[str, int] = {}
        for entry in entries.values():
            strategy = entry.get("strategy", "unknown")
            strategies_used[strategy] = strategies_used.get(strategy, 0) + 1
            for f in entry.get("fields", []):
                fields_obfuscated[f] = fields_obfuscated.get(f, 0) + 1
        return {
            "total_records": len(entries),
            "strategies_used": strategies_used,
            "fields_obfuscated": fields_obfuscated,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataObfuscatorState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
        logger.info("PipelineDataObfuscator reset")
