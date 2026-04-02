"""Agent Quota Tracker – tracks per-agent resource quotas with usage monitoring.

Provides quota allocation, usage tracking, and remaining capacity queries
for autonomous pipeline agents across named resources.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _State:
    quotas: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentQuotaTracker:
    """Tracks per-agent resource quotas with usage monitoring."""

    def __init__(self, max_entries: int = 10000):
        self._state = _State()
        self._max_entries = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, prefix: str, seed: str) -> str:
        self._state._seq += 1
        raw = f"{seed}-{time.time()}-{self._state._seq}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        total = sum(
            len(resources)
            for resources in self._state.quotas.values()
        )
        if total <= self._max_entries:
            return
        # Flatten, sort by created_at, remove oldest
        all_entries: List[tuple] = []
        for agent_id, resources in self._state.quotas.items():
            for resource, entry in resources.items():
                all_entries.append((agent_id, resource, entry["created_at"]))
        all_entries.sort(key=lambda x: x[2])
        to_remove = total - self._max_entries
        for agent_id, resource, _ in all_entries[:to_remove]:
            if agent_id in self._state.quotas:
                self._state.quotas[agent_id].pop(resource, None)
                if not self._state.quotas[agent_id]:
                    del self._state.quotas[agent_id]
        logger.debug("pruned_quotas", removed=to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_quota(self, agent_id: str, resource: str, limit: int) -> str:
        """Set quota limit for an agent/resource pair. Returns quota_id."""
        now = time.time()

        if agent_id not in self._state.quotas:
            self._state.quotas[agent_id] = {}

        existing = self._state.quotas[agent_id].get(resource)
        if existing:
            existing["limit"] = limit
            logger.info("quota_updated", agent_id=agent_id, resource=resource, limit=limit)
            self._fire("quota_updated", agent_id=agent_id, resource=resource, limit=limit)
            return existing["quota_id"]

        qid = self._gen_id("aqt-", f"{agent_id}-{resource}")
        self._state.quotas[agent_id][resource] = {
            "quota_id": qid,
            "agent_id": agent_id,
            "resource": resource,
            "limit": limit,
            "used": 0,
            "created_at": now,
        }
        self._prune_if_needed()

        logger.info("quota_created", quota_id=qid, agent_id=agent_id, resource=resource, limit=limit)
        self._fire("quota_created", quota_id=qid, agent_id=agent_id, resource=resource, limit=limit)
        return qid

    def use_quota(self, agent_id: str, resource: str, amount: int = 1) -> bool:
        """Use quota. Returns True if within limit, False if exceeded."""
        agent_quotas = self._state.quotas.get(agent_id)
        if not agent_quotas:
            return False

        entry = agent_quotas.get(resource)
        if not entry:
            return False

        if entry["used"] + amount <= entry["limit"]:
            entry["used"] += amount
            logger.debug("quota_used", agent_id=agent_id, resource=resource, amount=amount)
            self._fire("quota_used", agent_id=agent_id, resource=resource, amount=amount)
            return True

        logger.warning("quota_exceeded", agent_id=agent_id, resource=resource, requested=amount)
        self._fire("quota_exceeded", agent_id=agent_id, resource=resource, requested=amount)
        return False

    def get_remaining_quota(self, agent_id: str, resource: str) -> int:
        """Get remaining quota for an agent/resource pair."""
        agent_quotas = self._state.quotas.get(agent_id)
        if not agent_quotas:
            return 0

        entry = agent_quotas.get(resource)
        if not entry:
            return 0

        return entry["limit"] - entry["used"]

    def get_usage(self, agent_id: str, resource: str) -> dict:
        """Returns usage dict with used, limit, remaining."""
        agent_quotas = self._state.quotas.get(agent_id)
        if not agent_quotas:
            return {"used": 0, "limit": 0, "remaining": 0}

        entry = agent_quotas.get(resource)
        if not entry:
            return {"used": 0, "limit": 0, "remaining": 0}

        return {
            "used": entry["used"],
            "limit": entry["limit"],
            "remaining": entry["limit"] - entry["used"],
        }

    def reset_quota(self, agent_id: str, resource: str) -> bool:
        """Reset usage to 0 for an agent/resource pair."""
        agent_quotas = self._state.quotas.get(agent_id)
        if not agent_quotas:
            return False

        entry = agent_quotas.get(resource)
        if not entry:
            return False

        entry["used"] = 0
        logger.info("quota_reset", agent_id=agent_id, resource=resource)
        self._fire("quota_reset", agent_id=agent_id, resource=resource)
        return True

    def get_quota_count(self, agent_id: str = "") -> int:
        """Count quotas, optionally filtered by agent_id."""
        if agent_id:
            agent_quotas = self._state.quotas.get(agent_id)
            return len(agent_quotas) if agent_quotas else 0
        return sum(len(resources) for resources in self._state.quotas.values())

    def list_agents(self) -> list:
        """Return list of agent IDs with quotas."""
        return list(self._state.quotas.keys())

    def get_stats(self) -> dict:
        """Return tracker statistics."""
        total_quotas = sum(len(r) for r in self._state.quotas.values())
        total_used = sum(
            entry["used"]
            for resources in self._state.quotas.values()
            for entry in resources.values()
        )
        return {
            "total_quotas": total_quotas,
            "total_agents": len(self._state.quotas),
            "total_used": total_used,
            "callbacks_registered": len(self._state.callbacks),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state.quotas.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("quota_tracker_reset")
