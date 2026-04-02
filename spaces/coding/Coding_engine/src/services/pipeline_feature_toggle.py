"""Pipeline Feature Toggle – runtime feature flags for pipeline control.

Manages named feature flags that can be toggled on/off at runtime.
Supports percentage-based rollouts, environment targeting, and
toggle history tracking.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Toggle:
    toggle_id: str
    name: str
    enabled: bool
    rollout_pct: float  # 0.0-100.0, for gradual rollout
    environment: str  # e.g. "prod", "staging", "dev", "" for all
    description: str
    tags: List[str]
    total_checks: int
    total_enabled_checks: int
    created_at: float
    updated_at: float


class PipelineFeatureToggle:
    """Runtime feature flags for pipeline control."""

    def __init__(self, max_toggles: int = 10000):
        self._toggles: Dict[str, _Toggle] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_toggles = max_toggles
        self._seq = 0

        # stats
        self._total_toggles = 0
        self._total_checks = 0

    # ------------------------------------------------------------------
    # Toggles
    # ------------------------------------------------------------------

    def create_toggle(
        self,
        name: str,
        enabled: bool = False,
        rollout_pct: float = 100.0,
        environment: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._toggles) >= self._max_toggles:
            return ""
        rollout_pct = max(0.0, min(100.0, rollout_pct))

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        tid = "tgl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        toggle = _Toggle(
            toggle_id=tid,
            name=name,
            enabled=enabled,
            rollout_pct=rollout_pct,
            environment=environment,
            description=description,
            tags=tags or [],
            total_checks=0,
            total_enabled_checks=0,
            created_at=now,
            updated_at=now,
        )
        self._toggles[tid] = toggle
        self._name_index[name] = tid
        self._total_toggles += 1
        self._fire("toggle_created", {"toggle_id": tid, "name": name})
        return tid

    def get_toggle(self, toggle_id: str) -> Optional[Dict[str, Any]]:
        t = self._toggles.get(toggle_id)
        if not t:
            return None
        return {
            "toggle_id": t.toggle_id,
            "name": t.name,
            "enabled": t.enabled,
            "rollout_pct": t.rollout_pct,
            "environment": t.environment,
            "description": t.description,
            "tags": list(t.tags),
            "total_checks": t.total_checks,
            "total_enabled_checks": t.total_enabled_checks,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }

    def get_toggle_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        tid = self._name_index.get(name)
        if not tid:
            return None
        return self.get_toggle(tid)

    def remove_toggle(self, toggle_id: str) -> bool:
        t = self._toggles.pop(toggle_id, None)
        if not t:
            return False
        self._name_index.pop(t.name, None)
        self._fire("toggle_removed", {"toggle_id": toggle_id})
        return True

    # ------------------------------------------------------------------
    # Toggle operations
    # ------------------------------------------------------------------

    def enable_toggle(self, toggle_id: str) -> bool:
        t = self._toggles.get(toggle_id)
        if not t or t.enabled:
            return False
        t.enabled = True
        t.updated_at = time.time()
        self._fire("toggle_enabled", {"toggle_id": toggle_id, "name": t.name})
        return True

    def disable_toggle(self, toggle_id: str) -> bool:
        t = self._toggles.get(toggle_id)
        if not t or not t.enabled:
            return False
        t.enabled = False
        t.updated_at = time.time()
        self._fire("toggle_disabled", {"toggle_id": toggle_id, "name": t.name})
        return True

    def set_rollout(self, toggle_id: str, pct: float) -> bool:
        t = self._toggles.get(toggle_id)
        if not t:
            return False
        t.rollout_pct = max(0.0, min(100.0, pct))
        t.updated_at = time.time()
        return True

    def is_enabled(self, name: str, environment: str = "") -> bool:
        """Check if a feature is enabled for the given environment."""
        tid = self._name_index.get(name)
        if not tid:
            return False
        t = self._toggles[tid]
        t.total_checks += 1
        self._total_checks += 1

        if not t.enabled:
            return False
        if t.environment and environment and t.environment != environment:
            return False

        # Rollout check: use hash of name+check_count for determinism
        if t.rollout_pct < 100.0:
            h = hash(f"{name}-{t.total_checks}") % 100
            if h >= t.rollout_pct:
                return False

        t.total_enabled_checks += 1
        return True

    def is_enabled_simple(self, name: str) -> bool:
        """Simple check without environment filtering."""
        return self.is_enabled(name)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_toggles(
        self,
        enabled: Optional[bool] = None,
        environment: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for t in self._toggles.values():
            if enabled is not None and t.enabled != enabled:
                continue
            if environment and t.environment != environment:
                continue
            if tag and tag not in t.tags:
                continue
            results.append(self.get_toggle(t.toggle_id))
        return results

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
        return {
            "current_toggles": len(self._toggles),
            "total_toggles": self._total_toggles,
            "total_checks": self._total_checks,
            "enabled_count": sum(1 for t in self._toggles.values() if t.enabled),
        }

    def reset(self) -> None:
        self._toggles.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_toggles = 0
        self._total_checks = 0
