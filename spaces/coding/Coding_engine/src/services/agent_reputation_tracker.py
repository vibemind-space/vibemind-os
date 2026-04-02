"""Agent Reputation Tracker - tracks agent performance reputation scores.

Maintains weighted-average reputation scores for agents based on task
outcomes (success/failure, quality, importance weight).  Scores decay
toward a neutral baseline over time and can be used for routing,
trust decisions, and agent selection.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _AgentRecord:
    """Internal state for a single registered agent."""

    entry_id: str = ""
    agent_id: str = ""
    score: float = 50.0
    total_tasks: int = 0
    total_successes: int = 0
    quality_sum: float = 0.0
    weight_sum: float = 0.0
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class _HistoryEntry:
    """A single history record."""

    action: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class AgentReputationTracker:
    """Tracks agent performance reputation scores via weighted moving average."""

    def __init__(
        self,
        max_entries: int = 10000,
        max_history: int = 50000,
    ) -> None:
        self._agents: Dict[str, _AgentRecord] = {}
        self._id_index: Dict[str, str] = {}  # agent_id -> entry_id
        self._history: List[_HistoryEntry] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max(1, max_entries)
        self._max_history = max(1, max_history)
        self._seq = 0

        # counters
        self._total_registered = 0
        self._total_removed = 0
        self._total_outcomes = 0
        self._total_decays = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return "art-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        if len(self._history) >= self._max_history:
            self._history = self._history[-(self._max_history // 2) :]
        self._history.append(
            _HistoryEntry(action=action, detail=detail, timestamp=time.time())
        )

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return most recent history entries (newest first)."""
        results: List[Dict[str, Any]] = []
        for entry in reversed(self._history):
            results.append(
                {
                    "action": entry.action,
                    "detail": dict(entry.detail),
                    "timestamp": entry.timestamp,
                }
            )
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, fn: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = fn
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove lowest-score agents when at capacity."""
        if len(self._agents) < self._max_entries:
            return
        ranked = sorted(self._agents.values(), key=lambda r: r.score)
        to_remove = ranked[: len(ranked) // 4]
        for rec in to_remove:
            self._id_index.pop(rec.agent_id, None)
            self._agents.pop(rec.entry_id, None)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        initial_score: float = 50.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register an agent. Returns entry ID (art-...) or '' on dup/invalid."""
        if not agent_id:
            return ""
        if agent_id in self._id_index:
            return ""

        self._prune_if_needed()

        score = max(0.0, min(100.0, initial_score))
        eid = self._make_id(agent_id)
        now = time.time()

        rec = _AgentRecord(
            entry_id=eid,
            agent_id=agent_id,
            score=score,
            total_tasks=0,
            total_successes=0,
            quality_sum=0.0,
            weight_sum=0.0,
            tags=list(tags) if tags else [],
            created_at=now,
            updated_at=now,
        )
        self._agents[eid] = rec
        self._id_index[agent_id] = eid
        self._total_registered += 1

        detail = {"entry_id": eid, "agent_id": agent_id, "score": score}
        self._record_history("register_agent", detail)
        self._fire("register_agent", detail)
        return eid

    # ------------------------------------------------------------------
    # Outcome recording
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        agent_id: str,
        task_id: str,
        success: bool = True,
        quality: float = 1.0,
        weight: float = 1.0,
    ) -> bool:
        """Record a task outcome and update the agent's reputation score.

        Score formula (weighted moving average):
            new_score_input = (1 if success else 0) * quality * 100
            score = (old_score * (n-1) + new_score_input * weight) / (n-1 + weight)

        where n is total_tasks (after increment).
        """
        eid = self._id_index.get(agent_id)
        if not eid:
            return False
        if not task_id:
            return False

        quality = max(0.0, min(1.0, quality))
        weight = max(0.0, weight)
        if weight == 0.0:
            return False

        rec = self._agents[eid]
        new_score_input = (1.0 if success else 0.0) * quality * 100.0

        prev_weight = rec.weight_sum  # acts as (n-1) equivalent
        rec.score = (rec.score * prev_weight + new_score_input * weight) / (
            prev_weight + weight
        )
        rec.score = max(0.0, min(100.0, rec.score))

        rec.total_tasks += 1
        if success:
            rec.total_successes += 1
        rec.quality_sum += quality * weight
        rec.weight_sum += weight
        rec.updated_at = time.time()

        self._total_outcomes += 1

        detail = {
            "agent_id": agent_id,
            "task_id": task_id,
            "success": success,
            "quality": quality,
            "weight": weight,
            "new_score": rec.score,
        }
        self._record_history("record_outcome", detail)
        self._fire("record_outcome", detail)
        return True

    # ------------------------------------------------------------------
    # Reputation queries
    # ------------------------------------------------------------------

    def _agent_dict(self, rec: _AgentRecord) -> Dict[str, Any]:
        """Build a dict representation of an agent's reputation."""
        success_rate = (
            rec.total_successes / rec.total_tasks if rec.total_tasks > 0 else 0.0
        )
        avg_quality = (
            rec.quality_sum / rec.weight_sum if rec.weight_sum > 0.0 else 0.0
        )
        # Trend: compare score to neutral 50.0
        if rec.score > 55.0:
            trend = "rising"
        elif rec.score < 45.0:
            trend = "falling"
        else:
            trend = "stable"

        return {
            "entry_id": rec.entry_id,
            "agent_id": rec.agent_id,
            "score": round(rec.score, 4),
            "total_tasks": rec.total_tasks,
            "success_rate": round(success_rate, 4),
            "avg_quality": round(avg_quality, 4),
            "trend": trend,
            "tags": list(rec.tags),
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
        }

    def get_reputation(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent's full reputation dict, or None if not found."""
        eid = self._id_index.get(agent_id)
        if not eid:
            return None
        return self._agent_dict(self._agents[eid])

    def get_rankings(
        self, limit: int = 10, min_tasks: int = 0
    ) -> List[Dict[str, Any]]:
        """Top agents by score, optionally requiring a minimum task count."""
        candidates = [
            r for r in self._agents.values() if r.total_tasks >= min_tasks
        ]
        candidates.sort(key=lambda r: r.score, reverse=True)
        results: List[Dict[str, Any]] = []
        for rec in candidates[:limit]:
            d = self._agent_dict(rec)
            d["rank"] = len(results) + 1
            results.append(d)
        return results

    def get_underperformers(
        self, threshold: float = 30.0
    ) -> List[Dict[str, Any]]:
        """Return agents whose score is below *threshold*."""
        results: List[Dict[str, Any]] = []
        for rec in self._agents.values():
            if rec.score < threshold:
                results.append(self._agent_dict(rec))
        results.sort(key=lambda d: d["score"])
        return results

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    def apply_decay(self, decay_factor: float = 0.99) -> int:
        """Move every agent's score toward 50.0 neutral by *decay_factor*.

        new_score = 50.0 + (old_score - 50.0) * decay_factor

        Returns the number of agents whose score changed measurably.
        """
        decay_factor = max(0.0, min(1.0, decay_factor))
        neutral = 50.0
        count = 0
        for rec in self._agents.values():
            old = rec.score
            rec.score = neutral + (rec.score - neutral) * decay_factor
            rec.score = max(0.0, min(100.0, rec.score))
            if abs(rec.score - old) > 1e-6:
                count += 1
                rec.updated_at = time.time()
        if count:
            self._total_decays += 1
            detail = {"decay_factor": decay_factor, "affected": count}
            self._record_history("apply_decay", detail)
            self._fire("apply_decay", detail)
        return count

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def compare_agents(
        self, agent_id_1: str, agent_id_2: str
    ) -> Dict[str, Any]:
        """Compare two agents' reputations side by side."""
        rep1 = self.get_reputation(agent_id_1)
        rep2 = self.get_reputation(agent_id_2)
        if rep1 is None or rep2 is None:
            return {}

        score_diff = rep1["score"] - rep2["score"]
        if abs(score_diff) < 1.0:
            winner = "tie"
        elif score_diff > 0:
            winner = agent_id_1
        else:
            winner = agent_id_2

        return {
            "agent_1": rep1,
            "agent_2": rep2,
            "score_difference": round(abs(score_diff), 4),
            "winner": winner,
        }

    # ------------------------------------------------------------------
    # List / Remove
    # ------------------------------------------------------------------

    def list_agents(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all agents, optionally filtering by tag."""
        results: List[Dict[str, Any]] = []
        for rec in self._agents.values():
            if tag is not None and tag not in rec.tags:
                continue
            results.append(self._agent_dict(rec))
        return results

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from the tracker."""
        eid = self._id_index.pop(agent_id, None)
        if not eid:
            return False
        self._agents.pop(eid, None)
        self._total_removed += 1
        detail = {"agent_id": agent_id, "entry_id": eid}
        self._record_history("remove_agent", detail)
        self._fire("remove_agent", detail)
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a dict of operational counters."""
        scores = [r.score for r in self._agents.values()]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        return {
            "current_agents": len(self._agents),
            "total_registered": self._total_registered,
            "total_removed": self._total_removed,
            "total_outcomes": self._total_outcomes,
            "total_decays": self._total_decays,
            "avg_score": round(avg_score, 4),
            "history_size": len(self._history),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state back to initial."""
        self._agents.clear()
        self._id_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_removed = 0
        self._total_outcomes = 0
        self._total_decays = 0
