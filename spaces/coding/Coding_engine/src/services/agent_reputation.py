"""
Agent Reputation System — tracks and scores agent reliability and performance.

Features:
- Per-agent reputation scores (0-100)
- Success/failure tracking with weighted decay
- Task-type performance breakdown
- Reputation-based agent selection recommendations
- Penalty and reward system
- Reputation history with trend analysis
- Configurable scoring weights
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AgentRecord:
    """Reputation record for an agent."""
    agent_name: str
    score: float = 50.0  # Start neutral
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_penalties: float = 0.0
    total_rewards: float = 0.0
    registered_at: float = 0.0
    last_activity: float = 0.0
    task_type_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # task_type -> {"score": float, "count": int, "successes": int}
    history: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Agent Reputation System
# ---------------------------------------------------------------------------

class AgentReputation:
    """Tracks and scores agent reliability."""

    def __init__(
        self,
        success_weight: float = 5.0,
        failure_weight: float = 10.0,
        decay_factor: float = 0.95,
        max_history: int = 200,
        max_agents: int = 500,
    ):
        self._success_weight = success_weight
        self._failure_weight = failure_weight
        self._decay_factor = decay_factor
        self._max_history = max_history
        self._max_agents = max_agents

        self._agents: Dict[str, AgentRecord] = {}

        self._stats = {
            "total_registered": 0,
            "total_events": 0,
            "total_rewards": 0,
            "total_penalties": 0,
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        agent_name: str,
        initial_score: float = 50.0,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Register an agent for reputation tracking."""
        if agent_name in self._agents:
            return False
        now = time.time()
        self._agents[agent_name] = AgentRecord(
            agent_name=agent_name,
            score=max(0.0, min(100.0, initial_score)),
            registered_at=now,
            last_activity=now,
            tags=tags or set(),
            metadata=metadata or {},
        )
        self._stats["total_registered"] += 1
        return True

    def unregister(self, agent_name: str) -> bool:
        """Unregister an agent."""
        if agent_name not in self._agents:
            return False
        del self._agents[agent_name]
        return True

    def get_agent(self, agent_name: str) -> Optional[Dict]:
        """Get agent reputation details."""
        rec = self._agents.get(agent_name)
        if not rec:
            return None
        return self._record_to_dict(rec)

    def list_agents(
        self,
        min_score: float = 0.0,
        max_score: float = 100.0,
        tag: Optional[str] = None,
        sort_by: str = "score",
        limit: int = 50,
    ) -> List[Dict]:
        """List agents with reputation filters."""
        results = []
        for rec in self._agents.values():
            if rec.score < min_score or rec.score > max_score:
                continue
            if tag and tag not in rec.tags:
                continue
            results.append(self._record_to_dict(rec))

        reverse = sort_by in ("score",)
        results.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
        return results[:limit]

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_success(
        self,
        agent_name: str,
        task_type: str = "general",
        weight: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Record a successful task completion."""
        rec = self._agents.get(agent_name)
        if not rec:
            return False

        now = time.time()
        w = weight if weight > 0 else self._success_weight
        old_score = rec.score
        rec.score = min(100.0, rec.score + w)
        rec.total_tasks += 1
        rec.successful_tasks += 1
        rec.last_activity = now

        # Update task-type scores
        self._update_task_type(rec, task_type, success=True)

        # History
        self._add_history(rec, "success", old_score, rec.score, task_type, metadata)
        self._stats["total_events"] += 1
        return True

    def record_failure(
        self,
        agent_name: str,
        task_type: str = "general",
        weight: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Record a failed task."""
        rec = self._agents.get(agent_name)
        if not rec:
            return False

        now = time.time()
        w = weight if weight > 0 else self._failure_weight
        old_score = rec.score
        rec.score = max(0.0, rec.score - w)
        rec.total_tasks += 1
        rec.failed_tasks += 1
        rec.last_activity = now

        self._update_task_type(rec, task_type, success=False)
        self._add_history(rec, "failure", old_score, rec.score, task_type, metadata)
        self._stats["total_events"] += 1
        return True

    def reward(
        self,
        agent_name: str,
        amount: float,
        reason: str = "",
    ) -> bool:
        """Give a manual reputation reward."""
        rec = self._agents.get(agent_name)
        if not rec:
            return False

        old_score = rec.score
        rec.score = min(100.0, rec.score + abs(amount))
        rec.total_rewards += abs(amount)
        rec.last_activity = time.time()

        self._add_history(rec, "reward", old_score, rec.score, reason=reason)
        self._stats["total_rewards"] += 1
        self._stats["total_events"] += 1
        return True

    def penalize(
        self,
        agent_name: str,
        amount: float,
        reason: str = "",
    ) -> bool:
        """Apply a manual reputation penalty."""
        rec = self._agents.get(agent_name)
        if not rec:
            return False

        old_score = rec.score
        rec.score = max(0.0, rec.score - abs(amount))
        rec.total_penalties += abs(amount)
        rec.last_activity = time.time()

        self._add_history(rec, "penalty", old_score, rec.score, reason=reason)
        self._stats["total_penalties"] += 1
        self._stats["total_events"] += 1
        return True

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    def apply_decay(self) -> int:
        """Apply decay to all scores, pulling toward 50. Returns count affected."""
        affected = 0
        for rec in self._agents.values():
            old = rec.score
            rec.score = 50.0 + (rec.score - 50.0) * self._decay_factor
            if abs(rec.score - old) > 0.01:
                affected += 1
        return affected

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def get_ranking(self, limit: int = 20) -> List[Dict]:
        """Get agents ranked by reputation score."""
        ranked = sorted(
            self._agents.values(),
            key=lambda r: r.score,
            reverse=True,
        )
        result = []
        for i, rec in enumerate(ranked[:limit]):
            d = self._record_to_dict(rec)
            d["rank"] = i + 1
            result.append(d)
        return result

    def get_task_type_leaders(self, task_type: str, limit: int = 10) -> List[Dict]:
        """Get top agents for a specific task type."""
        results = []
        for rec in self._agents.values():
            if task_type in rec.task_type_scores:
                ts = rec.task_type_scores[task_type]
                results.append({
                    "agent_name": rec.agent_name,
                    "score": round(ts["score"], 2),
                    "count": int(ts["count"]),
                    "successes": int(ts["successes"]),
                    "success_rate": round(
                        ts["successes"] / ts["count"] * 100, 2
                    ) if ts["count"] > 0 else 0.0,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def recommend(
        self,
        task_type: str = "general",
        min_score: float = 30.0,
        limit: int = 5,
    ) -> List[Dict]:
        """Recommend agents for a task type based on reputation."""
        candidates = []
        for rec in self._agents.values():
            if rec.score < min_score:
                continue
            # Prefer task-type specific score if available
            type_score = rec.score
            if task_type in rec.task_type_scores:
                type_score = rec.task_type_scores[task_type]["score"]
            candidates.append({
                "agent_name": rec.agent_name,
                "overall_score": round(rec.score, 2),
                "task_type_score": round(type_score, 2),
                "total_tasks": rec.total_tasks,
                "success_rate": round(
                    rec.successful_tasks / rec.total_tasks * 100, 2
                ) if rec.total_tasks > 0 else 0.0,
            })
        candidates.sort(key=lambda x: x["task_type_score"], reverse=True)
        return candidates[:limit]

    def get_history(
        self,
        agent_name: str,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get reputation history for an agent."""
        rec = self._agents.get(agent_name)
        if not rec:
            return []
        history = rec.history
        if event_type:
            history = [h for h in history if h["event_type"] == event_type]
        return history[-limit:]

    def get_trend(self, agent_name: str, window: int = 10) -> Optional[Dict]:
        """Get recent reputation trend for an agent."""
        rec = self._agents.get(agent_name)
        if not rec or not rec.history:
            return None

        recent = rec.history[-window:]
        if len(recent) < 2:
            return {
                "agent_name": agent_name,
                "current_score": round(rec.score, 2),
                "direction": "stable",
                "change": 0.0,
                "data_points": len(recent),
            }

        first_score = recent[0]["new_score"]
        last_score = recent[-1]["new_score"]
        change = last_score - first_score

        direction = "stable"
        if change > 1.0:
            direction = "improving"
        elif change < -1.0:
            direction = "declining"

        return {
            "agent_name": agent_name,
            "current_score": round(rec.score, 2),
            "direction": direction,
            "change": round(change, 2),
            "data_points": len(recent),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_task_type(
        self,
        rec: AgentRecord,
        task_type: str,
        success: bool,
    ) -> None:
        if task_type not in rec.task_type_scores:
            rec.task_type_scores[task_type] = {
                "score": 50.0, "count": 0, "successes": 0,
            }
        ts = rec.task_type_scores[task_type]
        ts["count"] += 1
        if success:
            ts["successes"] += 1
            ts["score"] = min(100.0, ts["score"] + self._success_weight)
        else:
            ts["score"] = max(0.0, ts["score"] - self._failure_weight)

    def _add_history(
        self,
        rec: AgentRecord,
        event_type: str,
        old_score: float,
        new_score: float,
        task_type: str = "",
        metadata: Optional[Dict] = None,
        reason: str = "",
    ) -> None:
        entry = {
            "event_type": event_type,
            "old_score": round(old_score, 2),
            "new_score": round(new_score, 2),
            "timestamp": time.time(),
        }
        if task_type:
            entry["task_type"] = task_type
        if reason:
            entry["reason"] = reason
        if metadata:
            entry["metadata"] = metadata
        rec.history.append(entry)
        if len(rec.history) > self._max_history:
            rec.history = rec.history[-self._max_history:]

    def _record_to_dict(self, rec: AgentRecord) -> Dict:
        success_rate = 0.0
        if rec.total_tasks > 0:
            success_rate = round(rec.successful_tasks / rec.total_tasks * 100, 2)
        return {
            "agent_name": rec.agent_name,
            "score": round(rec.score, 2),
            "total_tasks": rec.total_tasks,
            "successful_tasks": rec.successful_tasks,
            "failed_tasks": rec.failed_tasks,
            "success_rate": success_rate,
            "total_rewards": round(rec.total_rewards, 2),
            "total_penalties": round(rec.total_penalties, 2),
            "registered_at": rec.registered_at,
            "last_activity": rec.last_activity,
            "task_types": sorted(rec.task_type_scores.keys()),
            "tags": sorted(rec.tags),
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        scores = [r.score for r in self._agents.values()]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        return {
            **self._stats,
            "total_agents": len(self._agents),
            "avg_score": avg_score,
            "min_score": round(min(scores), 2) if scores else 0.0,
            "max_score": round(max(scores), 2) if scores else 0.0,
        }

    def reset(self) -> None:
        self._agents.clear()
        self._stats = {k: 0 for k in self._stats}
