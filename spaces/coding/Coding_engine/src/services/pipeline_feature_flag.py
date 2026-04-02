"""Pipeline Feature Flag – manages feature flags for pipeline components.

Provides a centralised feature flag registry with support for boolean and
percentage-based rollouts, environment targeting, and change tracking.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _FeatureFlag:
    flag_id: str
    name: str
    enabled: bool
    rollout_pct: float  # 0.0 to 100.0
    environments: List[str]  # empty = all environments
    description: str
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _FlagEvent:
    event_id: str
    flag_name: str
    action: str  # created, enabled, disabled, updated, evaluated
    timestamp: float


class PipelineFeatureFlag:
    """Manages feature flags for pipeline components."""

    def __init__(self, max_flags: int = 10000, max_history: int = 100000):
        self._flags: Dict[str, _FeatureFlag] = {}
        self._name_index: Dict[str, str] = {}  # name -> flag_id
        self._history: List[_FlagEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_flags = max_flags
        self._max_history = max_history
        self._seq = 0
        self._current_env = "production"

        # stats
        self._total_created = 0
        self._total_evaluations = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def create_flag(
        self,
        name: str,
        enabled: bool = False,
        rollout_pct: float = 100.0,
        environments: Optional[List[str]] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._flags) >= self._max_flags:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        fid = "flg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        flag = _FeatureFlag(
            flag_id=fid,
            name=name,
            enabled=enabled,
            rollout_pct=max(0.0, min(100.0, rollout_pct)),
            environments=environments or [],
            description=description,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._flags[fid] = flag
        self._name_index[name] = fid
        self._total_created += 1
        self._record_event(name, "created")
        self._fire("flag_created", {"flag_id": fid, "name": name, "enabled": enabled})
        return fid

    def get_flag(self, name: str) -> Optional[Dict[str, Any]]:
        fid = self._name_index.get(name)
        if not fid:
            return None
        f = self._flags[fid]
        return {
            "flag_id": f.flag_id,
            "name": f.name,
            "enabled": f.enabled,
            "rollout_pct": f.rollout_pct,
            "environments": list(f.environments),
            "description": f.description,
            "tags": list(f.tags),
            "created_at": f.created_at,
            "updated_at": f.updated_at,
        }

    def remove_flag(self, name: str) -> bool:
        fid = self._name_index.pop(name, None)
        if not fid:
            return False
        self._flags.pop(fid, None)
        return True

    # ------------------------------------------------------------------
    # Flag operations
    # ------------------------------------------------------------------

    def enable_flag(self, name: str) -> bool:
        fid = self._name_index.get(name)
        if not fid:
            return False
        f = self._flags[fid]
        f.enabled = True
        f.updated_at = time.time()
        self._record_event(name, "enabled")
        self._fire("flag_enabled", {"name": name})
        return True

    def disable_flag(self, name: str) -> bool:
        fid = self._name_index.get(name)
        if not fid:
            return False
        f = self._flags[fid]
        f.enabled = False
        f.updated_at = time.time()
        self._record_event(name, "disabled")
        self._fire("flag_disabled", {"name": name})
        return True

    def set_rollout(self, name: str, rollout_pct: float) -> bool:
        fid = self._name_index.get(name)
        if not fid:
            return False
        f = self._flags[fid]
        f.rollout_pct = max(0.0, min(100.0, rollout_pct))
        f.updated_at = time.time()
        self._record_event(name, "updated")
        return True

    def set_environments(self, name: str, environments: List[str]) -> bool:
        fid = self._name_index.get(name)
        if not fid:
            return False
        f = self._flags[fid]
        f.environments = list(environments)
        f.updated_at = time.time()
        self._record_event(name, "updated")
        return True

    def set_environment(self, env: str) -> None:
        """Set current environment for evaluation."""
        self._current_env = env

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def is_enabled(self, name: str, user_id: str = "") -> bool:
        """Check if a feature flag is enabled.

        Takes into account: enabled state, environment targeting, and
        rollout percentage (using user_id for deterministic bucketing).
        """
        fid = self._name_index.get(name)
        if not fid:
            return False
        f = self._flags[fid]
        self._total_evaluations += 1

        # Must be enabled
        if not f.enabled:
            return False

        # Environment check
        if f.environments and self._current_env not in f.environments:
            return False

        # Rollout check
        if f.rollout_pct >= 100.0:
            return True
        if f.rollout_pct <= 0.0:
            return False

        if user_id:
            # Deterministic bucketing based on flag name + user_id
            raw = f"{name}-{user_id}"
            h = int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)
            bucket = (h % 10000) / 100.0  # 0.00 to 99.99
            return bucket < f.rollout_pct
        else:
            # Random evaluation without user_id
            return random.random() * 100.0 < f.rollout_pct

    def evaluate_all(self, user_id: str = "") -> Dict[str, bool]:
        """Evaluate all flags for a user."""
        results = {}
        for name in self._name_index:
            results[name] = self.is_enabled(name, user_id)
        return results

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_flags(self, enabled: Optional[bool] = None, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for f in self._flags.values():
            if enabled is not None and f.enabled != enabled:
                continue
            if tag and tag not in f.tags:
                continue
            results.append(self.get_flag(f.name))
        return results

    def get_enabled_count(self) -> int:
        return sum(1 for f in self._flags.values() if f.enabled)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        flag_name: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if flag_name and ev.flag_name != flag_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "flag_name": ev.flag_name,
                "action": ev.action,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, flag_name: str, action: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{flag_name}-{action}-{now}-{self._seq}"
        evid = "fev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _FlagEvent(
            event_id=evid, flag_name=flag_name,
            action=action, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        enabled = sum(1 for f in self._flags.values() if f.enabled)
        return {
            "current_flags": len(self._flags),
            "enabled_flags": enabled,
            "disabled_flags": len(self._flags) - enabled,
            "total_created": self._total_created,
            "total_evaluations": self._total_evaluations,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._flags.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_evaluations = 0
