"""Service module for emergent autonomous pipeline data normalization system."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)

MAX_ENTRIES = 10000

VALID_OPERATIONS = ("lowercase", "uppercase", "trim", "round")


@dataclass
class _State:
    rules: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataNormalizer:
    """Autonomous pipeline data normalization service."""

    def __init__(self) -> None:
        self._state = _State()

    # ── ID generation ──────────────────────────────────────────────

    def _next_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pdn-{digest}"

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.rules) > MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.rules,
                key=lambda k: self._state.rules[k].get("created_at", 0),
            )
            to_remove = len(self._state.rules) - MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.rules[k]
            logger.info("pruned_rules", removed=to_remove)

    # ── Callbacks ──────────────────────────────────────────────────

    def on_change(self, name: str, cb: Callable) -> None:
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ── API ────────────────────────────────────────────────────────

    def add_rule(
        self,
        pipeline_id: str,
        field: str,
        operation: str = "lowercase",
    ) -> str:
        """Add a normalization rule and return its rule_id."""
        if operation not in VALID_OPERATIONS:
            raise ValueError(f"Invalid operation '{operation}', must be one of {VALID_OPERATIONS}")
        rule_id = self._next_id(pipeline_id)
        record = {
            "rule_id": rule_id,
            "pipeline_id": pipeline_id,
            "field": field,
            "operation": operation,
            "created_at": time.time(),
            "apply_count": 0,
        }
        self._state.rules[rule_id] = record
        self._prune()
        logger.info("rule_added", rule_id=rule_id, pipeline_id=pipeline_id)
        self._fire("add_rule", rule_id=rule_id, pipeline_id=pipeline_id)
        return rule_id

    def _apply_operation(self, value: Any, operation: str) -> Any:
        """Apply a single normalization operation to a value."""
        if operation == "lowercase":
            return value.lower() if isinstance(value, str) else value
        if operation == "uppercase":
            return value.upper() if isinstance(value, str) else value
        if operation == "trim":
            return value.strip() if isinstance(value, str) else value
        if operation == "round":
            return round(value) if isinstance(value, (int, float)) else value
        return value

    def normalize(self, pipeline_id: str, record: dict) -> dict:
        """Apply all rules for *pipeline_id* to *record*, returning a new dict."""
        pipeline_rules = [
            r for r in self._state.rules.values() if r["pipeline_id"] == pipeline_id
        ]
        result = dict(record)
        for rule in pipeline_rules:
            fld = rule["field"]
            if fld in result:
                result[fld] = self._apply_operation(result[fld], rule["operation"])
            rule["apply_count"] += 1
        logger.info("normalize_applied", pipeline_id=pipeline_id, rule_count=len(pipeline_rules))
        self._fire("normalize", pipeline_id=pipeline_id, rule_count=len(pipeline_rules))
        return result

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by its id. Returns True if found and removed."""
        if rule_id in self._state.rules:
            removed = self._state.rules.pop(rule_id)
            logger.info("rule_removed", rule_id=rule_id)
            self._fire("remove_rule", rule_id=rule_id, pipeline_id=removed["pipeline_id"])
            return True
        return False

    def get_rules(self, pipeline_id: str) -> List[dict]:
        """Return all rule records for the given pipeline."""
        return [
            dict(r) for r in self._state.rules.values() if r["pipeline_id"] == pipeline_id
        ]

    def get_rule_count(self, pipeline_id: str = "") -> int:
        """Return the number of rules, optionally scoped to a pipeline."""
        if not pipeline_id:
            return len(self._state.rules)
        return sum(1 for r in self._state.rules.values() if r["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of unique pipeline IDs that have rules."""
        return sorted({r["pipeline_id"] for r in self._state.rules.values()})

    def get_stats(self) -> dict:
        """Return summary statistics about current rule state."""
        pipelines = self.list_pipelines()
        total_applies = sum(r["apply_count"] for r in self._state.rules.values())
        return {
            "total_rules": len(self._state.rules),
            "total_pipelines": len(pipelines),
            "total_apply_count": total_applies,
            "callbacks_registered": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all rules, reset sequence counter, and remove callbacks."""
        self._state.rules.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("state_reset")
