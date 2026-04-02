"""Service module for redacting sensitive fields from pipeline data records."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataRedactorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataRedactor:
    """Redacts sensitive fields from pipeline data records by replacing values with masked versions."""

    PREFIX = "pdr2-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataRedactorState()
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

    def register_rule(self, name: str, field: str, replacement: str = "***") -> str:
        """Register a redaction rule for a specific field."""
        rule_id = self._generate_id(name)
        self._state.entries[rule_id] = {
            "id": rule_id,
            "name": name,
            "field": field,
            "replacement": replacement,
            "created_at": time.time(),
            "usage_count": 0,
        }
        self._prune()
        self._fire("rule_registered", {"id": rule_id, "name": name, "field": field})
        logger.info("Registered redaction rule %s for field '%s'", rule_id, field)
        return rule_id

    def redact(self, record: dict, rule_ids: Optional[List[str]] = None) -> dict:
        """Apply redaction rules to a record. Returns a new dict with sensitive fields masked."""
        result = dict(record)
        rules = self._state.entries
        if rule_ids is not None:
            rules = {rid: rules[rid] for rid in rule_ids if rid in rules}
        for rule_id, rule in rules.items():
            target_field = rule["field"]
            if target_field in result:
                result[target_field] = rule["replacement"]
                self._state.entries[rule_id]["usage_count"] += 1
        return result

    def redact_batch(self, records: list, rule_ids: Optional[List[str]] = None) -> list:
        """Redact a list of records."""
        return [self.redact(record, rule_ids) for record in records]

    def get_rule(self, rule_id: str) -> dict:
        """Get a single rule by ID."""
        return dict(self._state.entries.get(rule_id, {}))

    def get_rules(self) -> list:
        """Get all registered rules."""
        return [dict(v) for v in self._state.entries.values()]

    def get_rule_count(self) -> int:
        """Get the number of registered rules."""
        return len(self._state.entries)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        if rule_id in self._state.entries:
            del self._state.entries[rule_id]
            self._fire("rule_removed", {"id": rule_id})
            logger.info("Removed redaction rule %s", rule_id)
            return True
        return False

    def get_stats(self) -> dict:
        """Get redaction statistics."""
        rules = self._state.entries
        total_redactions = sum(r.get("usage_count", 0) for r in rules.values())
        return {
            "total_rules": len(rules),
            "total_redactions": total_redactions,
            "total_fields_redacted": total_redactions,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineDataRedactorState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
        logger.info("PipelineDataRedactor reset")
