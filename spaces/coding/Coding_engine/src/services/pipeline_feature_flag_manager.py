"""Pipeline feature flag manager.

Manages feature flags for pipeline behaviour toggling, A/B testing,
gradual rollouts, and experiment tracking.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Flag:
    """A feature flag."""
    flag_id: str = ""
    name: str = ""
    description: str = ""
    enabled: bool = False
    rollout_percentage: float = 100.0  # 0-100
    targeting_rules: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    status: str = "active"  # active, archived
    evaluation_count: int = 0
    true_count: int = 0
    created_at: float = 0.0
    seq: int = 0


class PipelineFeatureFlagManager:
    """Manages feature flags for pipeline control."""

    STATUSES = ("active", "archived")

    def __init__(self, max_flags: int = 10000):
        self._max_flags = max_flags
        self._flags: Dict[str, _Flag] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_flags_created": 0,
            "total_evaluations": 0,
        }

    # ------------------------------------------------------------------
    # Flags
    # ------------------------------------------------------------------

    def create_flag(self, name: str, description: str = "",
                    enabled: bool = False,
                    rollout_percentage: float = 100.0,
                    targeting_rules: Optional[Dict] = None,
                    tags: Optional[List[str]] = None,
                    metadata: Optional[Dict] = None) -> str:
        if not name or not name.strip():
            return ""
        # Duplicate name check
        for f in self._flags.values():
            if f.name == name and f.status == "active":
                return ""
        if len(self._flags) >= self._max_flags:
            return ""

        rollout_percentage = max(0.0, min(100.0, rollout_percentage))
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}-{len(self._flags)}"
        fid = "ff-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._flags[fid] = _Flag(
            flag_id=fid,
            name=name,
            description=description,
            enabled=enabled,
            rollout_percentage=rollout_percentage,
            targeting_rules=dict(targeting_rules or {}),
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            status="active",
            created_at=now,
            seq=self._seq,
        )
        self._stats["total_flags_created"] += 1
        self._fire("flag_created", {"flag_id": fid, "name": name})
        return fid

    def get_flag(self, flag_id: str) -> Optional[Dict]:
        f = self._flags.get(flag_id)
        if not f:
            return None
        return {
            "flag_id": f.flag_id, "name": f.name,
            "description": f.description, "enabled": f.enabled,
            "rollout_percentage": f.rollout_percentage,
            "targeting_rules": dict(f.targeting_rules),
            "tags": list(f.tags), "metadata": dict(f.metadata),
            "status": f.status,
            "evaluation_count": f.evaluation_count,
            "true_count": f.true_count,
            "created_at": f.created_at,
        }

    def remove_flag(self, flag_id: str) -> bool:
        if flag_id not in self._flags:
            return False
        del self._flags[flag_id]
        return True

    def enable_flag(self, flag_id: str) -> bool:
        f = self._flags.get(flag_id)
        if not f or f.enabled:
            return False
        f.enabled = True
        self._fire("flag_enabled", {"flag_id": flag_id})
        return True

    def disable_flag(self, flag_id: str) -> bool:
        f = self._flags.get(flag_id)
        if not f or not f.enabled:
            return False
        f.enabled = False
        self._fire("flag_disabled", {"flag_id": flag_id})
        return True

    def archive_flag(self, flag_id: str) -> bool:
        f = self._flags.get(flag_id)
        if not f or f.status == "archived":
            return False
        f.status = "archived"
        return True

    def update_flag(self, flag_id: str,
                    description: str = None,
                    rollout_percentage: float = None,
                    targeting_rules: Dict = None,
                    tags: List[str] = None) -> bool:
        f = self._flags.get(flag_id)
        if not f or f.status != "active":
            return False
        if description is not None:
            f.description = description
        if rollout_percentage is not None:
            f.rollout_percentage = max(0.0, min(100.0, rollout_percentage))
        if targeting_rules is not None:
            f.targeting_rules = dict(targeting_rules)
        if tags is not None:
            f.tags = list(tags)
        return True

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, flag_id: str, context: Optional[Dict] = None) -> bool:
        """Evaluate whether a flag is active for the given context."""
        f = self._flags.get(flag_id)
        if not f or f.status != "active":
            return False

        f.evaluation_count += 1
        self._stats["total_evaluations"] += 1

        if not f.enabled:
            return False

        # Simple rollout check using hash of context
        if f.rollout_percentage < 100.0:
            ctx_str = str(context or {})
            h = int(hashlib.md5(ctx_str.encode()).hexdigest()[:8], 16)
            bucket = (h % 10000) / 100.0
            if bucket >= f.rollout_percentage:
                return False

        f.true_count += 1
        return True

    def evaluate_by_name(self, name: str,
                          context: Optional[Dict] = None) -> bool:
        """Evaluate flag by name."""
        for f in self._flags.values():
            if f.name == name and f.status == "active":
                return self.evaluate(f.flag_id, context)
        return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search(self, status: str = "", enabled: bool = None,
               tag: str = "", limit: int = 100) -> List[Dict]:
        results = []
        for f in self._flags.values():
            if status and f.status != status:
                continue
            if enabled is not None and f.enabled != enabled:
                continue
            if tag and tag not in f.tags:
                continue
            results.append(self.get_flag(f.flag_id))
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    def get_flag_by_name(self, name: str) -> Optional[Dict]:
        for f in self._flags.values():
            if f.name == name and f.status == "active":
                return self.get_flag(f.flag_id)
        return None

    def get_evaluation_stats(self, flag_id: str = "") -> Dict:
        """Get evaluation statistics."""
        if flag_id:
            f = self._flags.get(flag_id)
            if not f:
                return {"total_evaluations": 0, "true_count": 0, "true_rate": 0.0}
            rate = (f.true_count / f.evaluation_count * 100.0
                    if f.evaluation_count > 0 else 0.0)
            return {
                "total_evaluations": f.evaluation_count,
                "true_count": f.true_count,
                "true_rate": round(rate, 1),
            }
        total_eval = sum(f.evaluation_count for f in self._flags.values())
        total_true = sum(f.true_count for f in self._flags.values())
        rate = (total_true / total_eval * 100.0
                if total_eval > 0 else 0.0)
        return {
            "total_evaluations": total_eval,
            "true_count": total_true,
            "true_rate": round(rate, 1),
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        active = sum(1 for f in self._flags.values()
                     if f.status == "active")
        enabled = sum(1 for f in self._flags.values()
                      if f.enabled and f.status == "active")
        return {
            **self._stats,
            "current_flags": len(self._flags),
            "active_flags": active,
            "enabled_flags": enabled,
        }

    def reset(self) -> None:
        self._flags.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
