"""Agent work distributor — distributes work items across agents.

Uses round-robin or least-loaded strategies to assign work items
to groups of agents. Tracks assignments per agent and per group.

Usage::

    dist = AgentWorkDistributor()
    did = dist.register_agents("grp-1", ["agent-a", "agent-b"])
    assigned = dist.distribute("grp-1", "task-build-index")
    items = dist.get_assignments("agent-a")
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentWorkDistributor:
    """Distributes work items across agents using round-robin or least-loaded strategies."""

    max_entries: int = 10000
    _distributors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _assignments: Dict[str, List[str]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_registered: int = field(default=0)
    _total_distributed: int = field(default=0)

    def _next_id(self, seed: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{seed}{self._seq}".encode()).hexdigest()[:12]
        return f"awd-{raw}"

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "agent_work_distributor.callback_error",
                    callback=name,
                    event=event,
                )

    # -- public API ----------------------------------------------------------

    def register_agents(self, group_id: str, agent_ids: list,
                        strategy: str = "round_robin") -> str:
        """Register a group of agents for work distribution.

        Returns distributor ID (awd-xxx).
        strategy: 'round_robin' or 'least_loaded'.
        """
        if not group_id or not agent_ids:
            return ""
        if strategy not in ("round_robin", "least_loaded"):
            return ""
        if group_id in self._distributors:
            return ""
        if len(self._distributors) >= self.max_entries:
            return ""

        did = self._next_id(group_id)
        self._distributors[group_id] = {
            "distributor_id": did,
            "group_id": group_id,
            "agent_ids": list(agent_ids),
            "strategy": strategy,
            "rr_index": 0,
            "created_at": time.time(),
        }
        # Ensure each agent has an assignment list
        for aid in agent_ids:
            if aid not in self._assignments:
                self._assignments[aid] = []

        self._total_registered += 1
        logger.info(
            "agent_work_distributor.registered",
            group_id=group_id,
            distributor_id=did,
            agent_count=len(agent_ids),
            strategy=strategy,
        )
        self._fire("register_agents", {
            "distributor_id": did,
            "group_id": group_id,
            "agent_ids": list(agent_ids),
            "strategy": strategy,
        })
        return did

    def distribute(self, group_id: str, work_item: str) -> str:
        """Assign work item to next agent per strategy. Returns assigned agent_id."""
        if not group_id or not work_item:
            return ""
        dist = self._distributors.get(group_id)
        if dist is None:
            return ""

        agent_ids = dist["agent_ids"]
        if not agent_ids:
            return ""

        strategy = dist["strategy"]
        if strategy == "round_robin":
            idx = dist["rr_index"] % len(agent_ids)
            chosen = agent_ids[idx]
            dist["rr_index"] = idx + 1
        elif strategy == "least_loaded":
            chosen = min(agent_ids, key=lambda aid: len(self._assignments.get(aid, [])))
        else:
            return ""

        if chosen not in self._assignments:
            self._assignments[chosen] = []
        self._assignments[chosen].append(work_item)
        self._total_distributed += 1

        logger.info(
            "agent_work_distributor.distributed",
            group_id=group_id,
            agent_id=chosen,
            work_item=work_item,
        )
        self._fire("distribute", {
            "group_id": group_id,
            "agent_id": chosen,
            "work_item": work_item,
        })
        return chosen

    def get_assignments(self, agent_id: str) -> list:
        """Get work items assigned to an agent."""
        return list(self._assignments.get(agent_id, []))

    def get_assignment_count(self, agent_id: str = "") -> int:
        """Count assignments. If agent_id given, count for that agent; else total."""
        if agent_id:
            return len(self._assignments.get(agent_id, []))
        return sum(len(v) for v in self._assignments.values())

    def get_distributor(self, group_id: str) -> Optional[Dict]:
        """Get distributor info for a group."""
        dist = self._distributors.get(group_id)
        if dist is None:
            return None
        return {
            "distributor_id": dist["distributor_id"],
            "group_id": dist["group_id"],
            "agent_ids": list(dist["agent_ids"]),
            "strategy": dist["strategy"],
            "rr_index": dist["rr_index"],
            "created_at": dist["created_at"],
        }

    def get_distributor_count(self) -> int:
        """Return the number of registered distributor groups."""
        return len(self._distributors)

    def list_groups(self) -> list:
        """Return a list of registered group IDs."""
        return list(self._distributors.keys())

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        logger.debug("agent_work_distributor.callback_registered", name=name)
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("agent_work_distributor.callback_removed", name=name)
        return True

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_distributors": len(self._distributors),
            "total_registered": self._total_registered,
            "total_distributed": self._total_distributed,
            "total_assignments": sum(len(v) for v in self._assignments.values()),
            "total_agents": len(self._assignments),
            "max_entries": self.max_entries,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._distributors.clear()
        self._assignments.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_distributed = 0
        logger.info("agent_work_distributor.reset")
