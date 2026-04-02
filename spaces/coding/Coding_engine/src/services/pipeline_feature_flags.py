"""Pipeline feature flags - dynamic feature toggling with rollout strategies."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Flag:
    flag_id: str
    name: str
    description: str
    enabled: bool
    rollout_percentage: float  # 0.0 to 100.0
    targeting_rules: List[Dict]  # [{attribute, operator, value}]
    created_at: float
    updated_at: float
    tags: List[str]
    metadata: Dict = field(default_factory=dict)


class PipelineFeatureFlags:
    """Dynamic feature flag management with targeting rules and rollout strategies."""

    OPERATORS = ("eq", "neq", "in", "not_in", "gt", "lt", "gte", "lte", "contains")

    def __init__(self, max_flags: int = 5000):
        self._max_flags = max_flags
        self._flags: Dict[str, _Flag] = {}
        self._overrides: Dict[str, Dict[str, bool]] = {}  # flag_id -> {context_key: bool}
        self._check_log: List[Dict] = []
        self._max_log = 10000
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_created": 0,
            "total_checks": 0,
            "total_true": 0,
            "total_false": 0,
        }

    # ── Flag Management ──

    def create_flag(self, name: str, description: str = "",
                    enabled: bool = False, rollout_percentage: float = 100.0,
                    tags: Optional[List[str]] = None,
                    metadata: Optional[Dict] = None) -> str:
        """Create a feature flag."""
        if not name:
            return ""
        for f in self._flags.values():
            if f.name == name:
                return ""
        if len(self._flags) >= self._max_flags:
            return ""
        if not (0.0 <= rollout_percentage <= 100.0):
            return ""

        fid = f"flag-{uuid.uuid4().hex[:10]}"
        now = time.time()
        self._flags[fid] = _Flag(
            flag_id=fid,
            name=name,
            description=description,
            enabled=enabled,
            rollout_percentage=rollout_percentage,
            targeting_rules=[],
            created_at=now,
            updated_at=now,
            tags=tags or [],
            metadata=metadata or {},
        )
        self._stats["total_created"] += 1
        self._fire_callbacks("created", fid)
        return fid

    def remove_flag(self, flag_id: str) -> bool:
        if flag_id not in self._flags:
            return False
        del self._flags[flag_id]
        self._overrides.pop(flag_id, None)
        return True

    def get_flag(self, flag_id: str) -> Optional[Dict]:
        f = self._flags.get(flag_id)
        if not f:
            return None
        return {
            "flag_id": f.flag_id,
            "name": f.name,
            "description": f.description,
            "enabled": f.enabled,
            "rollout_percentage": f.rollout_percentage,
            "rule_count": len(f.targeting_rules),
            "tags": list(f.tags),
            "created_at": f.created_at,
            "updated_at": f.updated_at,
        }

    def get_flag_by_name(self, name: str) -> Optional[Dict]:
        for f in self._flags.values():
            if f.name == name:
                return self.get_flag(f.flag_id)
        return None

    def list_flags(self, tag: str = "", enabled_only: bool = False) -> List[Dict]:
        result = []
        for f in self._flags.values():
            if tag and tag not in f.tags:
                continue
            if enabled_only and not f.enabled:
                continue
            result.append({
                "flag_id": f.flag_id,
                "name": f.name,
                "enabled": f.enabled,
                "rollout_percentage": f.rollout_percentage,
            })
        return result

    # ── Toggle & Update ──

    def enable_flag(self, flag_id: str) -> bool:
        f = self._flags.get(flag_id)
        if not f:
            return False
        f.enabled = True
        f.updated_at = time.time()
        self._fire_callbacks("enabled", flag_id)
        return True

    def disable_flag(self, flag_id: str) -> bool:
        f = self._flags.get(flag_id)
        if not f:
            return False
        f.enabled = False
        f.updated_at = time.time()
        self._fire_callbacks("disabled", flag_id)
        return True

    def set_rollout(self, flag_id: str, percentage: float) -> bool:
        f = self._flags.get(flag_id)
        if not f:
            return False
        if not (0.0 <= percentage <= 100.0):
            return False
        f.rollout_percentage = percentage
        f.updated_at = time.time()
        return True

    def update_description(self, flag_id: str, description: str) -> bool:
        f = self._flags.get(flag_id)
        if not f:
            return False
        f.description = description
        f.updated_at = time.time()
        return True

    def add_tag(self, flag_id: str, tag: str) -> bool:
        f = self._flags.get(flag_id)
        if not f:
            return False
        if tag in f.tags:
            return False
        f.tags.append(tag)
        return True

    def remove_tag(self, flag_id: str, tag: str) -> bool:
        f = self._flags.get(flag_id)
        if not f or tag not in f.tags:
            return False
        f.tags.remove(tag)
        return True

    # ── Targeting Rules ──

    def add_rule(self, flag_id: str, attribute: str, operator: str,
                 value: Any) -> bool:
        """Add a targeting rule."""
        f = self._flags.get(flag_id)
        if not f:
            return False
        if operator not in self.OPERATORS:
            return False
        f.targeting_rules.append({
            "attribute": attribute,
            "operator": operator,
            "value": value,
        })
        f.updated_at = time.time()
        return True

    def clear_rules(self, flag_id: str) -> int:
        f = self._flags.get(flag_id)
        if not f:
            return 0
        count = len(f.targeting_rules)
        f.targeting_rules.clear()
        return count

    # ── Overrides ──

    def set_override(self, flag_id: str, context_key: str, value: bool) -> bool:
        """Set a per-context override."""
        if flag_id not in self._flags:
            return False
        if flag_id not in self._overrides:
            self._overrides[flag_id] = {}
        self._overrides[flag_id][context_key] = value
        return True

    def remove_override(self, flag_id: str, context_key: str) -> bool:
        if flag_id not in self._overrides:
            return False
        if context_key not in self._overrides[flag_id]:
            return False
        del self._overrides[flag_id][context_key]
        return True

    def list_overrides(self, flag_id: str) -> Dict[str, bool]:
        return dict(self._overrides.get(flag_id, {}))

    # ── Check (Flag Evaluation) ──

    def check(self, flag_id: str, context: Optional[Dict] = None) -> bool:
        """Check if a flag is active for a given context."""
        f = self._flags.get(flag_id)
        if not f:
            self._stats["total_checks"] += 1
            self._stats["total_false"] += 1
            return False

        self._stats["total_checks"] += 1
        context = context or {}
        context_key = context.get("key", "")

        # Check overrides first
        if flag_id in self._overrides and context_key in self._overrides[flag_id]:
            result = self._overrides[flag_id][context_key]
            self._record_check(flag_id, context_key, result, "override")
            return result

        # Flag disabled = false
        if not f.enabled:
            self._record_check(flag_id, context_key, False, "disabled")
            self._stats["total_false"] += 1
            return False

        # Check targeting rules (all must match)
        if f.targeting_rules:
            for rule in f.targeting_rules:
                if not self._check_rule(rule, context):
                    self._record_check(flag_id, context_key, False, "rule_mismatch")
                    self._stats["total_false"] += 1
                    return False

        # Check rollout percentage
        if f.rollout_percentage < 100.0:
            if context_key:
                hash_val = hash(context_key + flag_id) % 100
                if hash_val >= f.rollout_percentage:
                    self._record_check(flag_id, context_key, False, "rollout")
                    self._stats["total_false"] += 1
                    return False

        self._record_check(flag_id, context_key, True, "enabled")
        self._stats["total_true"] += 1
        return True

    def check_by_name(self, name: str, context: Optional[Dict] = None) -> bool:
        """Check by flag name."""
        for f in self._flags.values():
            if f.name == name:
                return self.check(f.flag_id, context)
        return False

    def check_all(self, context: Optional[Dict] = None) -> Dict[str, bool]:
        """Check all flags for a context."""
        result = {}
        for f in self._flags.values():
            result[f.name] = self.check(f.flag_id, context)
        return result

    def _check_rule(self, rule: Dict, context: Dict) -> bool:
        attr = rule["attribute"]
        op = rule["operator"]
        expected = rule["value"]
        actual = context.get(attr)

        if actual is None:
            return False

        if op == "eq":
            return actual == expected
        elif op == "neq":
            return actual != expected
        elif op == "in":
            return actual in expected
        elif op == "not_in":
            return actual not in expected
        elif op == "gt":
            return actual > expected
        elif op == "lt":
            return actual < expected
        elif op == "gte":
            return actual >= expected
        elif op == "lte":
            return actual <= expected
        elif op == "contains":
            return expected in actual
        return False

    def _record_check(self, flag_id: str, context_key: str,
                      result: bool, reason: str) -> None:
        if len(self._check_log) >= self._max_log:
            self._check_log = self._check_log[-(self._max_log // 2):]
        self._check_log.append({
            "flag_id": flag_id,
            "context_key": context_key,
            "result": result,
            "reason": reason,
            "timestamp": time.time(),
        })

    def get_check_log(self, flag_id: str = "", limit: int = 50) -> List[Dict]:
        result = []
        for e in reversed(self._check_log):
            if flag_id and e["flag_id"] != flag_id:
                continue
            result.append(e)
            if len(result) >= limit:
                break
        return result

    # ── Callbacks ──

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, action: str, flag_id: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, flag_id)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        enabled_count = sum(1 for f in self._flags.values() if f.enabled)
        return {
            **self._stats,
            "total_flags": len(self._flags),
            "enabled_flags": enabled_count,
            "disabled_flags": len(self._flags) - enabled_count,
            "total_overrides": sum(len(v) for v in self._overrides.values()),
            "total_rules": sum(len(f.targeting_rules) for f in self._flags.values()),
        }

    def reset(self) -> None:
        self._flags.clear()
        self._overrides.clear()
        self._check_log.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
