"""Agent scheduling policy.

Defines scheduling policies for agents (FIFO, priority, round-robin),
controlling how many concurrent tasks each agent may run and in what order.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

VALID_POLICY_TYPES = ("fifo", "priority", "round-robin")


@dataclass
class _PolicyEntry:
    """A single scheduling policy for an agent."""
    policy_id: str = ""
    agent_id: str = ""
    policy_type: str = "fifo"
    max_concurrent: int = 1
    created_at: float = 0.0
    seq: int = 0


class AgentSchedulingPolicy:
    """Manages scheduling policies for agents (FIFO, priority, round-robin)."""

    def __init__(self, max_entries: int = 100000) -> None:
        self._policies: Dict[str, _PolicyEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max(1, max_entries)
        self._stats = {
            "total_created": 0,
            "total_updated": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # Policy Management
    # ------------------------------------------------------------------

    def create_policy(
        self,
        agent_id: str,
        policy_type: str = "fifo",
        max_concurrent: int = 1,
    ) -> str:
        """Create a scheduling policy for an agent. Returns policy ID or empty on failure."""
        if not agent_id:
            return ""
        if policy_type not in VALID_POLICY_TYPES:
            return ""
        if max_concurrent < 1:
            return ""
        # One policy per agent
        for entry in self._policies.values():
            if entry.agent_id == agent_id:
                return ""
        if len(self._policies) >= self._max_entries:
            self._prune()

        self._seq += 1
        now = time.time()

        raw = f"{agent_id}{policy_type}{now}{self._seq}".encode()
        pid = "asp-" + hashlib.sha256(raw).hexdigest()[:12]

        self._policies[pid] = _PolicyEntry(
            policy_id=pid,
            agent_id=agent_id,
            policy_type=policy_type,
            max_concurrent=max_concurrent,
            created_at=now,
            seq=self._seq,
        )
        self._stats["total_created"] += 1

        logger.debug("policy_created", policy_id=pid, agent_id=agent_id,
                      policy_type=policy_type, max_concurrent=max_concurrent)
        self._fire("policy_created", {
            "policy_id": pid,
            "agent_id": agent_id,
            "policy_type": policy_type,
            "max_concurrent": max_concurrent,
        })
        return pid

    def get_policy(self, agent_id: str) -> Optional[Dict]:
        """Get the scheduling policy for an agent."""
        for entry in self._policies.values():
            if entry.agent_id == agent_id:
                return self._to_dict(entry)
        return None

    def update_policy(
        self,
        agent_id: str,
        policy_type: str = "",
        max_concurrent: int = 0,
    ) -> bool:
        """Update the scheduling policy for an agent. Returns True on success."""
        if not agent_id:
            return False
        if policy_type and policy_type not in VALID_POLICY_TYPES:
            return False
        if max_concurrent < 0:
            return False

        entry: Optional[_PolicyEntry] = None
        for e in self._policies.values():
            if e.agent_id == agent_id:
                entry = e
                break
        if entry is None:
            return False

        changed = False
        if policy_type and policy_type != entry.policy_type:
            entry.policy_type = policy_type
            changed = True
        if max_concurrent > 0 and max_concurrent != entry.max_concurrent:
            entry.max_concurrent = max_concurrent
            changed = True

        if not changed:
            return False

        self._stats["total_updated"] += 1
        logger.debug("policy_updated", policy_id=entry.policy_id,
                      agent_id=agent_id, policy_type=entry.policy_type,
                      max_concurrent=entry.max_concurrent)
        self._fire("policy_updated", {
            "policy_id": entry.policy_id,
            "agent_id": agent_id,
            "policy_type": entry.policy_type,
            "max_concurrent": entry.max_concurrent,
        })
        return True

    def can_schedule(self, agent_id: str, current_running: int) -> bool:
        """Check if an agent can accept more tasks based on its policy."""
        if not agent_id:
            return False
        if current_running < 0:
            return False
        policy = self.get_policy(agent_id)
        if policy is None:
            return False
        return current_running < policy["max_concurrent"]

    def list_agents(self) -> List[str]:
        """Return a sorted list of agent IDs that have policies."""
        agents: set[str] = set()
        for entry in self._policies.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    def get_policy_count(self) -> int:
        """Return the number of stored policies."""
        return len(self._policies)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = cb
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return policy store statistics."""
        return {
            **self._stats,
            "current_entries": len(self._policies),
            "current_agents": len(self.list_agents()),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all policies, callbacks, and stats."""
        self._policies.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(e: _PolicyEntry) -> Dict:
        return {
            "policy_id": e.policy_id,
            "agent_id": e.agent_id,
            "policy_type": e.policy_type,
            "max_concurrent": e.max_concurrent,
            "created_at": e.created_at,
            "seq": e.seq,
        }

    def _prune(self) -> None:
        """Remove the oldest quarter of entries."""
        items = sorted(self._policies.items(),
                       key=lambda x: (x[1].created_at, x[1].seq))
        to_remove = max(1, len(items) // 4)
        for k, _ in items[:to_remove]:
            del self._policies[k]
        self._stats["total_pruned"] += to_remove
        logger.debug("policies_pruned", count=to_remove)

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.warning("callback_error", action=action, exc_info=True)
