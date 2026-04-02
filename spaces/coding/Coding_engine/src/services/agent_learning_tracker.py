"""Agent Learning Tracker – monitors agent skill acquisition and progress.

Tracks learning events per agent, computes skill progress curves,
identifies top learners and struggling agents, and exposes trend
analysis for each tracked skill.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Agent:
    agent_id: str
    internal_id: str
    tags: List[str]
    created_at: float
    seq: int


@dataclass
class _LearningEvent:
    event_id: str
    agent_id: str
    skill: str
    score: float
    context: str
    created_at: float
    seq: int


@dataclass
class _HistoryEntry:
    action: str
    detail: Dict[str, Any]
    ts: float


class AgentLearningTracker:
    """Monitors agent skill acquisition, progress curves, and trends."""

    def __init__(self, max_entries: int = 10000,
                 max_history: int = 50000) -> None:
        self._max_entries = max_entries
        self._max_history = max_history
        self._agents: Dict[str, _Agent] = {}
        self._events: Dict[str, _LearningEvent] = {}
        self._agent_events: Dict[str, List[str]] = {}  # agent_id -> [event_id]
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._history: List[_HistoryEntry] = []
        self._stats = {
            "total_agents_registered": 0,
            "total_events_recorded": 0,
            "total_agents_removed": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"alt-{digest}_{self._seq}"

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        if len(self._history) >= self._max_history:
            self._history = self._history[-(self._max_history // 2):]
        self._history.append(_HistoryEntry(action=action, detail=detail,
                                           ts=time.time()))

    def get_history(self, limit: int = 100) -> List[Dict]:
        entries = self._history[-limit:]
        return [
            {"action": h.action, "detail": h.detail, "ts": h.ts}
            for h in entries
        ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_events(self) -> None:
        if len(self._events) <= self._max_entries:
            return
        sorted_ids = sorted(self._events, key=lambda k: self._events[k].seq)
        to_remove = sorted_ids[:len(self._events) - self._max_entries]
        for eid in to_remove:
            ev = self._events.pop(eid)
            lst = self._agent_events.get(ev.agent_id, [])
            if eid in lst:
                lst.remove(eid)

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str,
                       tags: Optional[List[str]] = None) -> str:
        if not agent_id:
            return ""
        if agent_id in self._agents:
            return ""
        internal_id = self._next_id(f"agent-{agent_id}")
        agent = _Agent(
            agent_id=agent_id,
            internal_id=internal_id,
            tags=list(tags or []),
            created_at=time.time(),
            seq=self._seq,
        )
        self._agents[agent_id] = agent
        self._agent_events[agent_id] = []
        self._stats["total_agents_registered"] += 1
        self._record_history("agent_registered",
                             {"agent_id": agent_id, "internal_id": internal_id})
        self._fire("agent_registered", {"agent_id": agent_id,
                                         "internal_id": internal_id})
        return internal_id

    # ------------------------------------------------------------------
    # Learning events
    # ------------------------------------------------------------------

    def record_learning(self, agent_id: str, skill: str,
                        score: float, context: str = "") -> bool:
        if agent_id not in self._agents:
            return False
        if not skill:
            return False
        score = max(0.0, min(1.0, score))
        eid = self._next_id(f"evt-{agent_id}-{skill}")
        event = _LearningEvent(
            event_id=eid, agent_id=agent_id, skill=skill,
            score=score, context=context,
            created_at=time.time(), seq=self._seq,
        )
        self._events[eid] = event
        self._agent_events.setdefault(agent_id, []).append(eid)
        self._stats["total_events_recorded"] += 1
        self._prune_events()
        self._record_history("learning_recorded",
                             {"agent_id": agent_id, "skill": skill,
                              "score": score})
        self._fire("learning_recorded", {"event_id": eid,
                                          "agent_id": agent_id,
                                          "skill": skill, "score": score})
        return True

    # ------------------------------------------------------------------
    # Profiles and progress
    # ------------------------------------------------------------------

    def _agent_skill_scores(self, agent_id: str) -> Dict[str, List[float]]:
        """Return {skill: [scores in order]} for an agent."""
        skill_scores: Dict[str, List[float]] = {}
        eids = self._agent_events.get(agent_id, [])
        for eid in eids:
            ev = self._events.get(eid)
            if ev is None:
                continue
            skill_scores.setdefault(ev.skill, []).append(ev.score)
        return skill_scores

    @staticmethod
    def _compute_trend(scores: List[float]) -> str:
        if len(scores) < 2:
            return "stable"
        half = len(scores) // 2
        first_avg = sum(scores[:half]) / half
        second_avg = sum(scores[half:]) / (len(scores) - half)
        diff = second_avg - first_avg
        if diff > 0.05:
            return "improving"
        if diff < -0.05:
            return "declining"
        return "stable"

    def get_agent_profile(self, agent_id: str) -> Optional[Dict]:
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        skill_scores = self._agent_skill_scores(agent_id)
        skills = list(skill_scores.keys())
        avg_scores: Dict[str, float] = {}
        for sk, scores in skill_scores.items():
            avg_scores[sk] = round(sum(scores) / len(scores), 4) if scores else 0.0
        overall_scores = [s for lst in skill_scores.values() for s in lst]
        trend = self._compute_trend(overall_scores)
        return {
            "agent_id": agent_id,
            "internal_id": agent.internal_id,
            "tags": list(agent.tags),
            "skills": skills,
            "avg_scores": avg_scores,
            "trend": trend,
            "total_events": len(overall_scores),
            "created_at": agent.created_at,
        }

    def get_skill_progress(self, agent_id: str, skill: str) -> Dict:
        skill_scores = self._agent_skill_scores(agent_id)
        scores = skill_scores.get(skill, [])
        trend = self._compute_trend(scores)
        improvement_rate = 0.0
        if len(scores) >= 2:
            improvement_rate = round(
                (scores[-1] - scores[0]) / len(scores), 4)
        return {
            "agent_id": agent_id,
            "skill": skill,
            "scores": list(scores),
            "trend": trend,
            "improvement_rate": improvement_rate,
            "total_events": len(scores),
        }

    def get_learning_curve(self, agent_id: str, skill: str) -> List[float]:
        skill_scores = self._agent_skill_scores(agent_id)
        return list(skill_scores.get(skill, []))

    # ------------------------------------------------------------------
    # Aggregation queries
    # ------------------------------------------------------------------

    def get_top_learners(self, skill: Optional[str] = None,
                         limit: int = 10) -> List[Dict]:
        results: List[Dict] = []
        for agent_id in self._agents:
            skill_scores = self._agent_skill_scores(agent_id)
            if skill is not None:
                scores = skill_scores.get(skill, [])
            else:
                scores = [s for lst in skill_scores.values() for s in lst]
            if len(scores) < 2:
                continue
            improvement = scores[-1] - scores[0]
            avg = round(sum(scores) / len(scores), 4)
            results.append({
                "agent_id": agent_id,
                "improvement": round(improvement, 4),
                "avg_score": avg,
                "total_events": len(scores),
                "trend": self._compute_trend(scores),
            })
        results.sort(key=lambda x: x["improvement"], reverse=True)
        return results[:limit]

    def get_struggling_agents(self, threshold: float = 0.3,
                              limit: int = 10) -> List[Dict]:
        results: List[Dict] = []
        for agent_id in self._agents:
            skill_scores = self._agent_skill_scores(agent_id)
            all_scores = [s for lst in skill_scores.values() for s in lst]
            if not all_scores:
                continue
            avg = sum(all_scores) / len(all_scores)
            if avg >= threshold:
                continue
            weak_skills = [
                sk for sk, sc in skill_scores.items()
                if sc and (sum(sc) / len(sc)) < threshold
            ]
            results.append({
                "agent_id": agent_id,
                "avg_score": round(avg, 4),
                "total_events": len(all_scores),
                "weak_skills": weak_skills,
                "trend": self._compute_trend(all_scores),
            })
        results.sort(key=lambda x: x["avg_score"])
        return results[:limit]

    # ------------------------------------------------------------------
    # Listing and removal
    # ------------------------------------------------------------------

    def list_agents(self, tag: Optional[str] = None) -> List[Dict]:
        results: List[Dict] = []
        for agent in self._agents.values():
            if tag is not None and tag not in agent.tags:
                continue
            results.append({
                "agent_id": agent.agent_id,
                "internal_id": agent.internal_id,
                "tags": list(agent.tags),
                "created_at": agent.created_at,
                "seq": agent.seq,
            })
        results.sort(key=lambda x: x["seq"])
        return results

    def remove_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        # Remove associated events
        eids = self._agent_events.pop(agent_id, [])
        for eid in eids:
            self._events.pop(eid, None)
        del self._agents[agent_id]
        self._stats["total_agents_removed"] += 1
        self._record_history("agent_removed", {"agent_id": agent_id})
        self._fire("agent_removed", {"agent_id": agent_id})
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_agents": len(self._agents),
            "current_events": len(self._events),
            "current_history": len(self._history),
            "current_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._events.clear()
        self._agent_events.clear()
        self._seq = 0
        self._callbacks.clear()
        self._history.clear()
        self._stats = {
            "total_agents_registered": 0,
            "total_events_recorded": 0,
            "total_agents_removed": 0,
        }
