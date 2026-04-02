"""Assess and track data quality metrics for pipeline records."""

import time
import hashlib
import dataclasses
import logging
import re

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataQualityState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataQuality:
    """Assess and track data quality metrics for pipeline records."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "pdq-"

    def __init__(self):
        self._state = PipelineDataQualityState()
        self._callbacks = {}
        self._rules = {}       # rule_id -> rule dict
        self._history = {}     # pipeline_id -> list of assessment results

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.ID_PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                removed = sorted_keys.pop(0)
                del self._state.entries[removed]

    def on_change(self, callback) -> str:
        cb_id = self._generate_id("callback")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self._callbacks:
            del self._callbacks[cb_id]
            return True
        return False

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def add_rule(self, pipeline_id: str, field: str, rule_type: str = "not_null", threshold: float = 1.0) -> str:
        """Add a data quality rule for a pipeline field."""
        if rule_type not in ("not_null", "unique", "in_range", "regex"):
            raise ValueError(f"Invalid rule_type: {rule_type}")
        rule_id = self._generate_id(f"rule-{pipeline_id}-{field}-{rule_type}")
        rule = {
            "rule_id": rule_id,
            "pipeline_id": pipeline_id,
            "field": field,
            "rule_type": rule_type,
            "threshold": threshold,
            "created_at": time.time(),
        }
        self._rules[rule_id] = rule
        self._state.entries[rule_id] = rule
        self._prune()
        self._fire("rule_added", rule)
        return rule_id

    def assess(self, pipeline_id: str, records: list) -> dict:
        """Assess records against rules for a pipeline, return quality report."""
        rules = self.get_rules(pipeline_id)
        total = len(records)
        if total == 0:
            result = {"score": 1.0, "total_records": 0, "passed": 0, "failed": 0, "details": []}
            self._store_history(pipeline_id, result)
            return result

        details = []
        all_pass_counts = []

        for rule in rules:
            field = rule["field"]
            rtype = rule["rule_type"]
            threshold = rule["threshold"]
            passed = 0

            for rec in records:
                val = rec.get(field)
                if rtype == "not_null":
                    if val is not None and val != "":
                        passed += 1
                elif rtype == "unique":
                    # Unique is checked across all records
                    passed = -1  # handled below
                    break
                elif rtype == "in_range":
                    if isinstance(val, (int, float)):
                        passed += 1
                elif rtype == "regex":
                    if isinstance(val, str) and re.search(threshold if isinstance(threshold, str) else ".*", val):
                        passed += 1

            if rtype == "unique":
                values = [rec.get(field) for rec in records if rec.get(field) is not None]
                unique_count = len(set(values))
                total_non_null = len(values)
                ratio = unique_count / total_non_null if total_non_null > 0 else 1.0
                passed = sum(1 for _ in records if True) if ratio >= threshold else 0
                detail = {
                    "rule_id": rule["rule_id"],
                    "field": field,
                    "rule_type": rtype,
                    "unique_ratio": ratio,
                    "passed": ratio >= threshold,
                }
            else:
                ratio = passed / total if total > 0 else 1.0
                detail = {
                    "rule_id": rule["rule_id"],
                    "field": field,
                    "rule_type": rtype,
                    "pass_rate": ratio,
                    "passed": ratio >= threshold,
                }

            details.append(detail)
            all_pass_counts.append(1 if detail["passed"] else 0)

        if not rules:
            score = 1.0
            total_passed = total
            total_failed = 0
        else:
            score = sum(all_pass_counts) / len(all_pass_counts) if all_pass_counts else 1.0
            total_passed = sum(1 for d in details if d["passed"])
            total_failed = len(details) - total_passed

        result = {
            "score": score,
            "total_records": total,
            "passed": total_passed,
            "failed": total_failed,
            "details": details,
        }
        self._store_history(pipeline_id, result)
        self._fire("assessment_completed", {"pipeline_id": pipeline_id, "result": result})
        return result

    def _store_history(self, pipeline_id: str, result: dict):
        if pipeline_id not in self._history:
            self._history[pipeline_id] = []
        entry = {**result, "pipeline_id": pipeline_id, "timestamp": time.time()}
        self._history[pipeline_id].append(entry)

    def get_rules(self, pipeline_id: str) -> list:
        """Get all rules for a pipeline."""
        return [r for r in self._rules.values() if r["pipeline_id"] == pipeline_id]

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        if rule_id in self._rules:
            rule = self._rules.pop(rule_id)
            self._state.entries.pop(rule_id, None)
            self._fire("rule_removed", rule)
            return True
        return False

    def get_history(self, pipeline_id: str, limit: int = 10) -> list:
        """Get past assessments for a pipeline."""
        entries = self._history.get(pipeline_id, [])
        return entries[-limit:]

    def get_rule(self, rule_id: str) -> dict:
        """Get a single rule by ID, or None."""
        return self._rules.get(rule_id, None)

    def get_rule_count(self, pipeline_id: str = "") -> int:
        """Count rules, optionally filtered by pipeline_id."""
        if pipeline_id:
            return len([r for r in self._rules.values() if r["pipeline_id"] == pipeline_id])
        return len(self._rules)

    def list_pipelines(self) -> list:
        """List distinct pipeline IDs that have rules."""
        return list(set(r["pipeline_id"] for r in self._rules.values()))

    def get_stats(self) -> dict:
        """Return stats about the quality tracker."""
        return {
            "total_rules": len(self._rules),
            "total_entries": len(self._state.entries),
            "total_pipelines": len(self.list_pipelines()),
            "total_assessments": sum(len(v) for v in self._history.values()),
            "seq": self._state._seq,
        }

    def reset(self):
        """Reset all state."""
        self._state = PipelineDataQualityState()
        self._rules.clear()
        self._history.clear()
        self._callbacks.clear()
        self._fire("reset", {})
