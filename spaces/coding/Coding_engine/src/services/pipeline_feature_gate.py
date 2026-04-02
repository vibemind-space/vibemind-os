"""Pipeline Feature Gate – controls feature availability via flags.

Manages feature flags with support for percentage rollouts, targeting
rules, and kill switches. Tracks flag evaluations for analytics.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _FeatureFlag:
    flag_id: str
    name: str
    enabled: bool
    rollout_pct: float
    allowed_agents: List[str]
    blocked_agents: List[str]
    total_checks: int
    total_enabled: int
    total_disabled: int
    tags: List[str]
    metadata: Dict[str, Any]
    created_at: float
    updated_at: float


class PipelineFeatureGate:
    """Controls feature availability via feature flags."""

    def __init__(self, max_flags: int = 5000, max_history: int = 100000):
        self._flags: Dict[str, _FeatureFlag] = {}
        self._name_index: Dict[str, str] = {}
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_flags = max_flags
        self._max_history = max_history
        self._seq = 0

        self._total_created = 0
        self._total_checks = 0

    # ------------------------------------------------------------------
    # Flag management
    # ------------------------------------------------------------------

    def create_flag(
        self,
        name: str,
        enabled: bool = False,
        rollout_pct: float = 100.0,
        allowed_agents: Optional[List[str]] = None,
        blocked_agents: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
        fid = "ffg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        flag = _FeatureFlag(
            flag_id=fid,
            name=name,
            enabled=enabled,
            rollout_pct=max(0.0, min(100.0, rollout_pct)),
            allowed_agents=allowed_agents or [],
            blocked_agents=blocked_agents or [],
            total_checks=0,
            total_enabled=0,
            total_disabled=0,
            tags=tags or [],
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._flags[fid] = flag
        self._name_index[name] = fid
        self._total_created += 1
        self._fire("flag_created", {"flag_id": fid, "name": name})
        return fid

    def get_flag(self, flag_id: str) -> Optional[Dict[str, Any]]:
        f = self._flags.get(flag_id)
        if not f:
            return None
        return {
            "flag_id": f.flag_id,
            "name": f.name,
            "enabled": f.enabled,
            "rollout_pct": f.rollout_pct,
            "allowed_agents": list(f.allowed_agents),
            "blocked_agents": list(f.blocked_agents),
            "total_checks": f.total_checks,
            "total_enabled": f.total_enabled,
            "total_disabled": f.total_disabled,
            "tags": list(f.tags),
            "metadata": dict(f.metadata),
            "created_at": f.created_at,
        }

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        fid = self._name_index.get(name)
        if not fid:
            return None
        return self.get_flag(fid)

    def remove_flag(self, flag_id: str) -> bool:
        f = self._flags.pop(flag_id, None)
        if not f:
            return False
        self._name_index.pop(f.name, None)
        return True

    def enable_flag(self, flag_id: str) -> bool:
        f = self._flags.get(flag_id)
        if not f or f.enabled:
            return False
        f.enabled = True
        f.updated_at = time.time()
        self._fire("flag_enabled", {"flag_id": flag_id, "name": f.name})
        return True

    def disable_flag(self, flag_id: str) -> bool:
        f = self._flags.get(flag_id)
        if not f or not f.enabled:
            return False
        f.enabled = False
        f.updated_at = time.time()
        self._fire("flag_disabled", {"flag_id": flag_id, "name": f.name})
        return True

    def set_rollout_pct(self, flag_id: str, pct: float) -> bool:
        f = self._flags.get(flag_id)
        if not f:
            return False
        f.rollout_pct = max(0.0, min(100.0, pct))
        f.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def is_enabled(self, name: str, agent: str = "") -> bool:
        """Check if a feature is enabled for a given agent."""
        fid = self._name_index.get(name)
        if not fid:
            return False
        f = self._flags.get(fid)
        if not f:
            return False

        f.total_checks += 1
        self._total_checks += 1

        if not f.enabled:
            f.total_disabled += 1
            self._record_check(f, agent, False)
            return False

        # Check blocked list
        if agent and f.blocked_agents and agent in f.blocked_agents:
            f.total_disabled += 1
            self._record_check(f, agent, False)
            return False

        # Check allowed list (if set, only those agents)
        if agent and f.allowed_agents and agent not in f.allowed_agents:
            f.total_disabled += 1
            self._record_check(f, agent, False)
            return False

        # Check rollout percentage
        if f.rollout_pct < 100.0:
            # deterministic: hash agent name to get consistent result
            if agent:
                h = int(hashlib.md5(f"{name}:{agent}".encode()).hexdigest()[:8], 16)
                bucket = (h % 10000) / 100.0
                if bucket >= f.rollout_pct:
                    f.total_disabled += 1
                    self._record_check(f, agent, False)
                    return False

        f.total_enabled += 1
        self._record_check(f, agent, True)
        return True

    def is_enabled_by_id(self, flag_id: str, agent: str = "") -> bool:
        f = self._flags.get(flag_id)
        if not f:
            return False
        return self.is_enabled(f.name, agent)

    def check_all(self, agent: str = "") -> Dict[str, bool]:
        results = {}
        for f in self._flags.values():
            results[f.name] = self.is_enabled(f.name, agent)
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
            results.append(self.get_flag(f.flag_id))
        return results

    def get_enabled_flags(self) -> List[str]:
        return [f.name for f in self._flags.values() if f.enabled]

    def get_history(self, name: str = "", agent: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for h in reversed(self._history):
            if name and h.get("name") != name:
                continue
            if agent and h.get("agent") != agent:
                continue
            results.append(h)
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_check(self, flag: _FeatureFlag, agent: str, result: bool) -> None:
        record = {
            "flag_id": flag.flag_id,
            "name": flag.name,
            "agent": agent,
            "result": result,
            "timestamp": time.time(),
        }
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(record)

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
        enabled_count = sum(1 for f in self._flags.values() if f.enabled)
        return {
            "current_flags": len(self._flags),
            "enabled_flags": enabled_count,
            "total_created": self._total_created,
            "total_checks": self._total_checks,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._flags.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_checks = 0
