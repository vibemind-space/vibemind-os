"""Agent reputation ledger - immutable record of agent reputation events."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ReputationEntry:
    """An immutable reputation ledger entry."""
    entry_id: str = ""
    agent: str = ""
    action: str = ""
    category: str = ""
    points: float = 0.0
    reason: str = ""
    source: str = ""
    timestamp: float = 0.0


class AgentReputationLedger:
    """Immutable ledger tracking agent reputation over time."""

    CATEGORIES = (
        "quality", "reliability", "speed", "collaboration",
        "innovation", "compliance", "custom",
    )

    ACTIONS = (
        "reward", "penalty", "bonus", "deduction",
        "achievement", "infraction", "adjustment",
    )

    def __init__(self, max_entries: int = 100000, decay_rate: float = 0.0):
        self._max_entries = max(1, max_entries)
        self._decay_rate = max(0.0, decay_rate)
        self._entries: List[ReputationEntry] = []
        self._agent_scores: Dict[str, float] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_entries": 0,
            "total_rewards": 0,
            "total_penalties": 0,
        }

    # --- Ledger Operations ---

    def record(
        self,
        agent: str,
        action: str,
        points: float,
        category: str = "custom",
        reason: str = "",
        source: str = "",
    ) -> str:
        """Record a reputation event."""
        if not agent or not action:
            return ""
        if action not in self.ACTIONS:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if len(self._entries) >= self._max_entries:
            self._entries = self._entries[-(self._max_entries // 2):]

        eid = f"rep-{uuid.uuid4().hex[:12]}"
        entry = ReputationEntry(
            entry_id=eid,
            agent=agent,
            action=action,
            category=category,
            points=points,
            reason=reason,
            source=source,
            timestamp=time.time(),
        )
        self._entries.append(entry)

        # Update score
        if agent not in self._agent_scores:
            self._agent_scores[agent] = 0.0
        self._agent_scores[agent] += points

        self._stats["total_entries"] += 1
        if points > 0:
            self._stats["total_rewards"] += 1
        elif points < 0:
            self._stats["total_penalties"] += 1

        self._fire("reputation_recorded", {
            "agent": agent, "action": action, "points": points,
        })
        return eid

    def get_score(self, agent: str) -> float:
        """Get current reputation score for an agent."""
        return self._agent_scores.get(agent, 0.0)

    def get_agent_history(
        self,
        agent: str,
        category: str = "",
        action: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """Get reputation history for an agent."""
        results = []
        for entry in reversed(self._entries):
            if entry.agent != agent:
                continue
            if category and entry.category != category:
                continue
            if action and entry.action != action:
                continue
            results.append({
                "entry_id": entry.entry_id,
                "action": entry.action,
                "category": entry.category,
                "points": entry.points,
                "reason": entry.reason,
                "source": entry.source,
                "timestamp": entry.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    # --- Rankings ---

    def get_rankings(self, limit: int = 10) -> List[Dict]:
        """Get top agents by reputation score."""
        ranked = sorted(
            self._agent_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            {"agent": agent, "score": round(score, 2), "rank": i + 1}
            for i, (agent, score) in enumerate(ranked[:limit])
        ]

    def get_bottom_agents(self, limit: int = 10) -> List[Dict]:
        """Get lowest reputation agents."""
        ranked = sorted(
            self._agent_scores.items(),
            key=lambda x: x[1],
        )
        return [
            {"agent": agent, "score": round(score, 2)}
            for agent, score in ranked[:limit]
        ]

    # --- Analytics ---

    def get_agent_summary(self, agent: str) -> Dict:
        """Get reputation summary for an agent."""
        total_positive = 0.0
        total_negative = 0.0
        count_positive = 0
        count_negative = 0
        categories: Dict[str, float] = {}

        for entry in self._entries:
            if entry.agent != agent:
                continue
            if entry.points > 0:
                total_positive += entry.points
                count_positive += 1
            elif entry.points < 0:
                total_negative += entry.points
                count_negative += 1
            categories[entry.category] = categories.get(entry.category, 0.0) + entry.points

        if count_positive == 0 and count_negative == 0:
            return {}

        return {
            "agent": agent,
            "score": round(self._agent_scores.get(agent, 0.0), 2),
            "total_positive": round(total_positive, 2),
            "total_negative": round(total_negative, 2),
            "count_positive": count_positive,
            "count_negative": count_negative,
            "by_category": {k: round(v, 2) for k, v in categories.items()},
        }

    def get_category_leaders(self, category: str, limit: int = 10) -> List[Dict]:
        """Get top agents in a specific category."""
        cat_scores: Dict[str, float] = {}
        for entry in self._entries:
            if entry.category != category:
                continue
            cat_scores[entry.agent] = cat_scores.get(entry.agent, 0.0) + entry.points

        ranked = sorted(cat_scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {"agent": agent, "category_score": round(score, 2)}
            for agent, score in ranked[:limit]
        ]

    def get_recent_activity(self, limit: int = 20) -> List[Dict]:
        """Get most recent reputation activity."""
        results = []
        for entry in reversed(self._entries):
            results.append({
                "entry_id": entry.entry_id,
                "agent": entry.agent,
                "action": entry.action,
                "points": entry.points,
                "category": entry.category,
                "timestamp": entry.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def get_all_agents(self) -> List[str]:
        """Get all agents with reputation entries."""
        return sorted(self._agent_scores.keys())

    # --- Callbacks ---

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

    # --- Stats ---

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "tracked_agents": len(self._agent_scores),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._agent_scores.clear()
        self._callbacks.clear()
        self._stats = {
            "total_entries": 0,
            "total_rewards": 0,
            "total_penalties": 0,
        }

    # --- Internal ---

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
