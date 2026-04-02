"""Agent trust scorer - track and compute trust scores for agents."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class TrustRecord:
    """Trust event record."""
    record_id: str = ""
    agent: str = ""
    event_type: str = ""
    delta: float = 0.0
    reason: str = ""
    source: str = ""
    created_at: float = 0.0


@dataclass
class AgentTrust:
    """Agent trust profile."""
    agent: str = ""
    score: float = 50.0
    total_positive: int = 0
    total_negative: int = 0
    history: list = field(default_factory=list)
    registered_at: float = 0.0


class AgentTrustScorer:
    """Track and compute trust scores for agents based on behavior."""

    EVENT_TYPES = (
        "task_completed", "task_failed", "verification_passed",
        "verification_failed", "timeout", "violation",
        "collaboration", "manual_boost", "manual_penalty",
    )

    def __init__(self, max_agents: int = 5000, max_history: int = 1000,
                 min_score: float = 0.0, max_score: float = 100.0,
                 default_score: float = 50.0):
        self._max_agents = max(1, max_agents)
        self._max_history = max(1, max_history)
        self._min_score = min_score
        self._max_score = max_score
        self._default_score = default_score
        self._agents: Dict[str, AgentTrust] = {}
        self._records: Dict[str, TrustRecord] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_registered": 0,
            "total_events": 0,
            "total_positive": 0,
            "total_negative": 0,
        }

    # --- Agent Management ---

    def register_agent(self, agent: str, initial_score: float = 0.0) -> bool:
        """Register an agent for trust tracking."""
        if not agent or agent in self._agents:
            return False
        if len(self._agents) >= self._max_agents:
            return False

        score = initial_score if initial_score > 0 else self._default_score
        self._agents[agent] = AgentTrust(
            agent=agent,
            score=max(self._min_score, min(self._max_score, score)),
            registered_at=time.time(),
        )
        self._stats["total_registered"] += 1
        return True

    def unregister_agent(self, agent: str) -> bool:
        """Unregister an agent."""
        if agent not in self._agents:
            return False
        # Clean up history records
        a = self._agents[agent]
        for rid in a.history:
            self._records.pop(rid, None)
        del self._agents[agent]
        return True

    def get_agent(self, agent: str) -> Optional[Dict]:
        """Get agent trust profile."""
        a = self._agents.get(agent)
        if not a:
            return None
        return {
            "agent": a.agent,
            "score": round(a.score, 2),
            "total_positive": a.total_positive,
            "total_negative": a.total_negative,
            "history_count": len(a.history),
            "registered_at": a.registered_at,
        }

    def list_agents(self, min_score: float = -1.0, max_score_filter: float = -1.0) -> List[Dict]:
        """List agents with optional score filter."""
        results = []
        for a in self._agents.values():
            if min_score >= 0 and a.score < min_score:
                continue
            if max_score_filter >= 0 and a.score > max_score_filter:
                continue
            results.append({
                "agent": a.agent,
                "score": round(a.score, 2),
                "total_positive": a.total_positive,
                "total_negative": a.total_negative,
            })
        results.sort(key=lambda x: -x["score"])
        return results

    # --- Trust Events ---

    def record_event(
        self,
        agent: str,
        event_type: str,
        delta: float = 0.0,
        reason: str = "",
        source: str = "",
    ) -> str:
        """Record a trust event. Returns record_id."""
        a = self._agents.get(agent)
        if not a:
            return ""
        if event_type not in self.EVENT_TYPES:
            return ""

        # Auto-determine delta if not provided
        if delta == 0.0:
            delta = self._default_delta(event_type)

        rid = f"trust-{uuid.uuid4().hex[:12]}"
        now = time.time()

        self._records[rid] = TrustRecord(
            record_id=rid,
            agent=agent,
            event_type=event_type,
            delta=delta,
            reason=reason,
            source=source,
            created_at=now,
        )

        # Update score
        old_score = a.score
        a.score = max(self._min_score, min(self._max_score, a.score + delta))

        if delta > 0:
            a.total_positive += 1
            self._stats["total_positive"] += 1
        elif delta < 0:
            a.total_negative += 1
            self._stats["total_negative"] += 1

        # Manage history
        a.history.append(rid)
        if len(a.history) > self._max_history:
            old_rid = a.history.pop(0)
            self._records.pop(old_rid, None)

        self._stats["total_events"] += 1

        # Fire callbacks
        if a.score < 20 and old_score >= 20:
            self._fire("trust_low", {"agent": agent, "score": a.score})
        if a.score >= 80 and old_score < 80:
            self._fire("trust_high", {"agent": agent, "score": a.score})

        self._fire("trust_changed", {"agent": agent, "delta": delta, "score": a.score})
        return rid

    def get_history(self, agent: str, limit: int = 50) -> List[Dict]:
        """Get trust history for an agent (newest first)."""
        a = self._agents.get(agent)
        if not a:
            return []
        results = []
        for rid in reversed(a.history):
            r = self._records.get(rid)
            if r:
                results.append({
                    "record_id": r.record_id,
                    "event_type": r.event_type,
                    "delta": r.delta,
                    "reason": r.reason,
                    "source": r.source,
                    "created_at": r.created_at,
                })
            if len(results) >= limit:
                break
        return results

    # --- Analytics ---

    def get_score(self, agent: str) -> float:
        """Get current trust score."""
        a = self._agents.get(agent)
        return round(a.score, 2) if a else -1.0

    def get_ranking(self, limit: int = 10) -> List[Dict]:
        """Get agents ranked by trust score."""
        return self.list_agents()[:limit]

    def get_trusted_agents(self, min_score: float = 70.0) -> List[str]:
        """Get agents above trust threshold."""
        return [a.agent for a in self._agents.values() if a.score >= min_score]

    def get_untrusted_agents(self, max_score: float = 30.0) -> List[str]:
        """Get agents below trust threshold."""
        return [a.agent for a in self._agents.values() if a.score <= max_score]

    def get_average_score(self) -> float:
        """Get average trust score across all agents."""
        if not self._agents:
            return 0.0
        return round(sum(a.score for a in self._agents.values()) / len(self._agents), 2)

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
            "current_agents": len(self._agents),
            "average_score": self.get_average_score(),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._records.clear()
        self._callbacks.clear()
        self._stats = {
            "total_registered": 0,
            "total_events": 0,
            "total_positive": 0,
            "total_negative": 0,
        }

    # --- Internal ---

    def _default_delta(self, event_type: str) -> float:
        """Default delta for event types."""
        defaults = {
            "task_completed": 2.0,
            "task_failed": -3.0,
            "verification_passed": 3.0,
            "verification_failed": -5.0,
            "timeout": -2.0,
            "violation": -10.0,
            "collaboration": 1.0,
            "manual_boost": 5.0,
            "manual_penalty": -5.0,
        }
        return defaults.get(event_type, 0.0)

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
