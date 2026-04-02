"""Service module for sanitizing pipeline data by applying cleaning rules."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataSanitizerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataSanitizer:
    """Sanitizes pipeline data by applying cleaning rules such as stripping whitespace,
    lowercasing, removing nulls, and trimming strings."""

    PREFIX = "pdsa-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataSanitizerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self, data: str = "") -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}{data}"
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

    # -- Sanitization helpers ------------------------------------------------

    def _apply_strip_whitespace(self, data: dict) -> dict:
        """Strip leading/trailing whitespace from all string values."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = v.strip()
            elif isinstance(v, dict):
                result[k] = self._apply_strip_whitespace(v)
            else:
                result[k] = v
        return result

    def _apply_lowercase(self, data: dict) -> dict:
        """Lowercase all string values."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = v.lower()
            elif isinstance(v, dict):
                result[k] = self._apply_lowercase(v)
            else:
                result[k] = v
        return result

    def _apply_remove_nulls(self, data: dict) -> dict:
        """Remove keys with None values."""
        result = {}
        for k, v in data.items():
            if v is None:
                continue
            if isinstance(v, dict):
                result[k] = self._apply_remove_nulls(v)
            else:
                result[k] = v
        return result

    def _apply_trim_strings(self, data: dict, max_length: int = 1000) -> dict:
        """Trim string values to max_length characters."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = v[:max_length]
            elif isinstance(v, dict):
                result[k] = self._apply_trim_strings(v, max_length)
            else:
                result[k] = v
        return result

    # -- Core methods --------------------------------------------------------

    def sanitize(self, data: dict, rules: List[str] = None) -> str:
        """Apply sanitization rules to data. Returns sanitization record ID.

        Supported built-in rules: strip_whitespace, lowercase, remove_nulls, trim_strings.
        """
        if rules is None:
            rules = ["strip_whitespace", "remove_nulls"]

        original = copy.deepcopy(data)
        sanitized = copy.deepcopy(data)

        rules_applied = []
        for rule in rules:
            if rule == "strip_whitespace":
                sanitized = self._apply_strip_whitespace(sanitized)
                rules_applied.append(rule)
            elif rule == "lowercase":
                sanitized = self._apply_lowercase(sanitized)
                rules_applied.append(rule)
            elif rule == "remove_nulls":
                sanitized = self._apply_remove_nulls(sanitized)
                rules_applied.append(rule)
            elif rule == "trim_strings":
                sanitized = self._apply_trim_strings(sanitized)
                rules_applied.append(rule)
            else:
                # Check custom rules
                for entry in self._state.entries.values():
                    if entry.get("type") == "rule" and entry.get("rule_name") == rule:
                        rules_applied.append(rule)
                        break

        record_id = self._generate_id("sanitize")
        self._state.entries[record_id] = {
            "id": record_id,
            "type": "record",
            "original": original,
            "sanitized": sanitized,
            "rules_applied": rules_applied,
            "created_at": time.time(),
        }
        self._prune()
        self._fire("sanitized", {"id": record_id, "rules_applied": rules_applied})
        logger.info("Sanitized data with rules %s -> %s", rules_applied, record_id)
        return record_id

    def get_record(self, record_id: str) -> Optional[dict]:
        """Get a sanitization record by ID."""
        entry = self._state.entries.get(record_id)
        if entry is None or entry.get("type") != "record":
            return None
        return copy.deepcopy(entry)

    def get_records(self, limit: int = 50) -> List[dict]:
        """Get sanitization records, newest first."""
        records = [
            copy.deepcopy(v)
            for v in self._state.entries.values()
            if v.get("type") == "record"
        ]
        records.sort(key=lambda r: r.get("created_at", 0), reverse=True)
        return records[:limit]

    def add_rule(self, rule_name: str, description: str = "") -> str:
        """Register a custom sanitization rule. Returns rule ID."""
        rule_id = self._generate_id(rule_name)
        self._state.entries[rule_id] = {
            "id": rule_id,
            "type": "rule",
            "rule_name": rule_name,
            "description": description,
            "created_at": time.time(),
        }
        self._prune()
        self._fire("rule_added", {"id": rule_id, "rule_name": rule_name})
        logger.info("Added custom rule '%s' -> %s", rule_name, rule_id)
        return rule_id

    def get_rules(self) -> List[dict]:
        """Get all registered custom rules."""
        return [
            copy.deepcopy(v)
            for v in self._state.entries.values()
            if v.get("type") == "rule"
        ]

    def get_stats(self) -> dict:
        """Get sanitization statistics."""
        records = [v for v in self._state.entries.values() if v.get("type") == "record"]
        rules_count: Dict[str, int] = {}
        for rec in records:
            for rule in rec.get("rules_applied", []):
                rules_count[rule] = rules_count.get(rule, 0) + 1
        return {
            "total_sanitizations": len(records),
            "rules_applied": rules_count,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineDataSanitizerState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
        logger.info("PipelineDataSanitizer reset")
