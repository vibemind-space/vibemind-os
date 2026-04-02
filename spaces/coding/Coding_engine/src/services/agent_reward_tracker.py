"""Agent Reward Tracker - tracks rewards granted to agents for completed tasks.

Maintains a ledger of rewards granted to agents, supporting queries by
agent, reward type, and aggregation (totals, leaderboards).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import hashlib
import time


@dataclass
class RewardEntry:
    """A single reward entry."""

    reward_id: str = ""
    agent_id: str = ""
    reward_type: str = ""
    amount: float = 0.0
    reason: str = ""
    created_at: float = 0.0


class AgentRewardTracker:
    """Tracks rewards granted to agents with aggregation and leaderboards."""

    def __init__(self) -> None:
        self._rewards: Dict[str, RewardEntry] = {}
        self._callbacks: Dict[str, Any] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"arw-{self._seq}-{id(self)}"
        return "arw-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> None:
        """Register a change callback by name."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: Any) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when over capacity."""
        if len(self._rewards) <= self._max_entries:
            return
        sorted_entries = sorted(
            self._rewards.values(), key=lambda e: e.created_at
        )
        to_remove = sorted_entries[: len(sorted_entries) // 4]
        for entry in to_remove:
            self._rewards.pop(entry.reward_id, None)

    # ------------------------------------------------------------------
    # Grant reward
    # ------------------------------------------------------------------

    def grant_reward(
        self,
        agent_id: str,
        reward_type: str,
        amount: float,
        reason: str = "",
    ) -> str:
        """Grant a reward to an agent. Returns reward_id starting with 'arw-'."""
        self._prune_if_needed()

        reward_id = self._generate_id()
        entry = RewardEntry(
            reward_id=reward_id,
            agent_id=agent_id,
            reward_type=reward_type,
            amount=amount,
            reason=reason,
            created_at=time.time(),
        )
        self._rewards[reward_id] = entry

        self._fire("grant_reward", {
            "reward_id": reward_id,
            "agent_id": agent_id,
            "reward_type": reward_type,
            "amount": amount,
            "reason": reason,
        })
        return reward_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_reward(self, reward_id: str) -> Optional[Dict[str, Any]]:
        """Get a single reward by ID, or None if not found."""
        entry = self._rewards.get(reward_id)
        if entry is None:
            return None
        return {
            "reward_id": entry.reward_id,
            "agent_id": entry.agent_id,
            "reward_type": entry.reward_type,
            "amount": entry.amount,
            "reason": entry.reason,
            "created_at": entry.created_at,
        }

    def get_agent_rewards(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all rewards for a given agent."""
        results: List[Dict[str, Any]] = []
        for entry in self._rewards.values():
            if entry.agent_id == agent_id:
                results.append({
                    "reward_id": entry.reward_id,
                    "agent_id": entry.agent_id,
                    "reward_type": entry.reward_type,
                    "amount": entry.amount,
                    "reason": entry.reason,
                    "created_at": entry.created_at,
                })
        return results

    def get_total_rewards(self, agent_id: str) -> float:
        """Return the sum of all reward amounts for an agent."""
        total = 0.0
        for entry in self._rewards.values():
            if entry.agent_id == agent_id:
                total += entry.amount
        return total

    def get_reward_by_type(self, reward_type: str) -> List[Dict[str, Any]]:
        """Return all rewards of a given type."""
        results: List[Dict[str, Any]] = []
        for entry in self._rewards.values():
            if entry.reward_type == reward_type:
                results.append({
                    "reward_id": entry.reward_id,
                    "agent_id": entry.agent_id,
                    "reward_type": entry.reward_type,
                    "amount": entry.amount,
                    "reason": entry.reason,
                    "created_at": entry.created_at,
                })
        return results

    def get_reward_count(self) -> int:
        """Return the total number of rewards."""
        return len(self._rewards)

    def get_leaderboard(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Return top agents by total reward amount (descending)."""
        totals: Dict[str, float] = {}
        for entry in self._rewards.values():
            totals[entry.agent_id] = totals.get(entry.agent_id, 0.0) + entry.amount
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        results: List[Dict[str, Any]] = []
        for agent_id, total in ranked[:top_n]:
            results.append({"agent_id": agent_id, "total": total})
        return results

    # ------------------------------------------------------------------
    # List helpers
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return a list of all agent IDs that have received rewards."""
        agents: set = set()
        for entry in self._rewards.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    def list_reward_types(self) -> List[str]:
        """Return a list of unique reward types."""
        types: set = set()
        for entry in self._rewards.values():
            types.add(entry.reward_type)
        return sorted(types)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a dict with counts."""
        return {
            "reward_count": len(self._rewards),
            "agent_count": len(set(e.agent_id for e in self._rewards.values())),
            "type_count": len(set(e.reward_type for e in self._rewards.values())),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state back to initial."""
        self._rewards.clear()
        self._callbacks.clear()
        self._seq = 0
        self._max_entries = 10000
