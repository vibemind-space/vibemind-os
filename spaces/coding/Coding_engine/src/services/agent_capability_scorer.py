"""Agent Capability Scorer – scores and ranks agent capabilities.

Maintains a scoring system for agent capabilities, allowing evaluation
of agent fitness for specific tasks. Supports weighted scoring,
capability decay, and comparative ranking.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _CapabilityScore:
    score_id: str
    agent: str
    capability: str
    score: float  # 0.0 to 1.0
    weight: float
    evidence_count: int
    last_evaluated_at: float
    decay_rate: float  # score reduction per day
    tags: List[str]
    created_at: float
    updated_at: float


class AgentCapabilityScorer:
    """Scores and ranks agent capabilities."""

    def __init__(self, max_entries: int = 100000):
        self._scores: Dict[str, _CapabilityScore] = {}
        self._agent_index: Dict[str, List[str]] = {}
        self._cap_index: Dict[str, List[str]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # stats
        self._total_scored = 0
        self._total_evaluations = 0

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score(
        self,
        agent: str,
        capability: str,
        score: float,
        weight: float = 1.0,
        decay_rate: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not agent or not capability:
            return ""
        if score < 0.0 or score > 1.0:
            return ""
        if weight < 0.0:
            return ""

        # check for existing agent+capability combo
        for sid in self._agent_index.get(agent, []):
            s = self._scores.get(sid)
            if s and s.capability == capability:
                # update existing score
                s.score = score
                s.weight = weight
                s.evidence_count += 1
                s.last_evaluated_at = time.time()
                s.updated_at = time.time()
                self._total_evaluations += 1
                self._fire("score_updated", {
                    "score_id": sid, "agent": agent,
                    "capability": capability, "score": score,
                })
                return sid

        if len(self._scores) >= self._max_entries:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{capability}-{now}-{self._seq}"
        sid = "cap-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _CapabilityScore(
            score_id=sid,
            agent=agent,
            capability=capability,
            score=score,
            weight=weight,
            evidence_count=1,
            last_evaluated_at=now,
            decay_rate=decay_rate,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._scores[sid] = entry
        self._agent_index.setdefault(agent, []).append(sid)
        self._cap_index.setdefault(capability, []).append(sid)
        self._total_scored += 1
        self._total_evaluations += 1
        self._fire("capability_scored", {
            "score_id": sid, "agent": agent,
            "capability": capability, "score": score,
        })
        return sid

    def get_score(self, score_id: str) -> Optional[Dict[str, Any]]:
        s = self._scores.get(score_id)
        if not s:
            return None
        return {
            "score_id": s.score_id,
            "agent": s.agent,
            "capability": s.capability,
            "score": s.score,
            "weight": s.weight,
            "evidence_count": s.evidence_count,
            "last_evaluated_at": s.last_evaluated_at,
            "decay_rate": s.decay_rate,
            "tags": list(s.tags),
            "created_at": s.created_at,
        }

    def remove_score(self, score_id: str) -> bool:
        s = self._scores.pop(score_id, None)
        if not s:
            return False
        agent_list = self._agent_index.get(s.agent, [])
        if score_id in agent_list:
            agent_list.remove(score_id)
        cap_list = self._cap_index.get(s.capability, [])
        if score_id in cap_list:
            cap_list.remove(score_id)
        return True

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def get_agent_profile(self, agent: str) -> Dict[str, float]:
        """Get capability profile for an agent (capability->score mapping)."""
        sids = self._agent_index.get(agent, [])
        profile = {}
        for sid in sids:
            s = self._scores.get(sid)
            if s:
                profile[s.capability] = s.score
        return profile

    def get_weighted_score(self, agent: str) -> float:
        """Get weighted average score for an agent."""
        sids = self._agent_index.get(agent, [])
        total_weight = 0.0
        weighted_sum = 0.0
        for sid in sids:
            s = self._scores.get(sid)
            if s:
                weighted_sum += s.score * s.weight
                total_weight += s.weight
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def rank_agents_for_capability(self, capability: str) -> List[Dict[str, Any]]:
        """Rank agents by score for a specific capability."""
        sids = self._cap_index.get(capability, [])
        ranked = []
        for sid in sids:
            s = self._scores.get(sid)
            if s:
                ranked.append({
                    "agent": s.agent,
                    "score": s.score,
                    "evidence_count": s.evidence_count,
                })
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    def find_best_agent(self, capability: str) -> Optional[str]:
        """Find the best agent for a capability."""
        ranking = self.rank_agents_for_capability(capability)
        return ranking[0]["agent"] if ranking else None

    def compare_agents(self, agent_a: str, agent_b: str) -> Dict[str, Any]:
        """Compare two agents across all capabilities."""
        profile_a = self.get_agent_profile(agent_a)
        profile_b = self.get_agent_profile(agent_b)
        all_caps = set(list(profile_a.keys()) + list(profile_b.keys()))
        comparison = {}
        for cap in all_caps:
            a_score = profile_a.get(cap, 0.0)
            b_score = profile_b.get(cap, 0.0)
            comparison[cap] = {
                "agent_a": a_score,
                "agent_b": b_score,
                "winner": agent_a if a_score >= b_score else agent_b,
            }
        return comparison

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_scores(
        self,
        agent: str = "",
        capability: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for s in self._scores.values():
            if agent and s.agent != agent:
                continue
            if capability and s.capability != capability:
                continue
            if tag and tag not in s.tags:
                continue
            results.append(self.get_score(s.score_id))
        return results

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
        agents = set()
        caps = set()
        for s in self._scores.values():
            agents.add(s.agent)
            caps.add(s.capability)
        return {
            "current_scores": len(self._scores),
            "total_scored": self._total_scored,
            "total_evaluations": self._total_evaluations,
            "unique_agents": len(agents),
            "unique_capabilities": len(caps),
        }

    def reset(self) -> None:
        self._scores.clear()
        self._agent_index.clear()
        self._cap_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_scored = 0
        self._total_evaluations = 0
