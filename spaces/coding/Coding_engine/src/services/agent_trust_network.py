"""Agent Trust Network – manages trust relationships between agents.

Tracks directional trust scores between agent pairs.  Trust can increase
through successful interactions and decrease through failures or betrayals.
Provides trust-path queries for transitive trust evaluation.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class _TrustEdge:
    edge_id: str
    from_agent: str
    to_agent: str
    trust_score: float  # 0.0 to 100.0
    interactions: int
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _TrustEvent:
    event_id: str
    from_agent: str
    to_agent: str
    action: str
    old_score: float
    new_score: float
    timestamp: float


class AgentTrustNetwork:
    """Manages trust relationships between agents."""

    def __init__(self, max_edges: int = 100000, max_history: int = 100000, default_trust: float = 50.0, trust_increment: float = 5.0, trust_decrement: float = 10.0):
        self._edges: Dict[str, _TrustEdge] = {}
        self._pair_index: Dict[Tuple[str, str], str] = {}  # (from, to) -> edge_id
        self._history: List[_TrustEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_edges = max_edges
        self._max_history = max_history
        self._default_trust = default_trust
        self._trust_increment = trust_increment
        self._trust_decrement = trust_decrement
        self._seq = 0
        self._total_created = 0
        self._total_updates = 0

    def establish_trust(self, from_agent: str, to_agent: str, initial_trust: float = 0.0, tags: Optional[List[str]] = None) -> str:
        if not from_agent or not to_agent or from_agent == to_agent:
            return ""
        pair = (from_agent, to_agent)
        if pair in self._pair_index:
            return ""
        if len(self._edges) >= self._max_edges:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{from_agent}-{to_agent}-{now}-{self._seq}"
        eid = "te-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        trust = initial_trust if initial_trust > 0 else self._default_trust
        trust = max(0.0, min(100.0, trust))
        edge = _TrustEdge(edge_id=eid, from_agent=from_agent, to_agent=to_agent, trust_score=trust, interactions=0, tags=tags or [], created_at=now, updated_at=now)
        self._edges[eid] = edge
        self._pair_index[pair] = eid
        self._total_created += 1
        self._fire("trust_established", {"edge_id": eid, "from": from_agent, "to": to_agent, "trust": trust})
        return eid

    def get_trust(self, from_agent: str, to_agent: str) -> float:
        eid = self._pair_index.get((from_agent, to_agent))
        if not eid:
            return 0.0
        return self._edges[eid].trust_score

    def record_positive(self, from_agent: str, to_agent: str, bonus: float = 0.0) -> bool:
        eid = self._pair_index.get((from_agent, to_agent))
        if not eid:
            return False
        edge = self._edges[eid]
        old = edge.trust_score
        inc = bonus if bonus > 0 else self._trust_increment
        edge.trust_score = min(100.0, edge.trust_score + inc)
        edge.interactions += 1
        edge.updated_at = time.time()
        self._total_updates += 1
        self._record_event(from_agent, to_agent, "positive", old, edge.trust_score)
        self._fire("trust_increased", {"from": from_agent, "to": to_agent, "old": old, "new": edge.trust_score})
        return True

    def record_negative(self, from_agent: str, to_agent: str, penalty: float = 0.0) -> bool:
        eid = self._pair_index.get((from_agent, to_agent))
        if not eid:
            return False
        edge = self._edges[eid]
        old = edge.trust_score
        dec = penalty if penalty > 0 else self._trust_decrement
        edge.trust_score = max(0.0, edge.trust_score - dec)
        edge.interactions += 1
        edge.updated_at = time.time()
        self._total_updates += 1
        self._record_event(from_agent, to_agent, "negative", old, edge.trust_score)
        self._fire("trust_decreased", {"from": from_agent, "to": to_agent, "old": old, "new": edge.trust_score})
        return True

    def remove_trust(self, from_agent: str, to_agent: str) -> bool:
        pair = (from_agent, to_agent)
        eid = self._pair_index.pop(pair, None)
        if not eid:
            return False
        self._edges.pop(eid, None)
        return True

    def get_edge(self, from_agent: str, to_agent: str) -> Optional[Dict[str, Any]]:
        eid = self._pair_index.get((from_agent, to_agent))
        if not eid:
            return None
        e = self._edges[eid]
        return {"edge_id": e.edge_id, "from_agent": e.from_agent, "to_agent": e.to_agent, "trust_score": e.trust_score, "interactions": e.interactions, "tags": list(e.tags), "created_at": e.created_at, "updated_at": e.updated_at}

    def get_trusted_by(self, agent: str, min_trust: float = 0.0) -> List[Dict[str, Any]]:
        """Get agents that trust this agent."""
        results = []
        for e in self._edges.values():
            if e.to_agent == agent and e.trust_score >= min_trust:
                results.append(self.get_edge(e.from_agent, e.to_agent))
        return [r for r in results if r]

    def get_trusts(self, agent: str, min_trust: float = 0.0) -> List[Dict[str, Any]]:
        """Get agents that this agent trusts."""
        results = []
        for e in self._edges.values():
            if e.from_agent == agent and e.trust_score >= min_trust:
                results.append(self.get_edge(e.from_agent, e.to_agent))
        return [r for r in results if r]

    def get_mutual_trust(self, agent_a: str, agent_b: str) -> Dict[str, float]:
        return {"a_trusts_b": self.get_trust(agent_a, agent_b), "b_trusts_a": self.get_trust(agent_b, agent_a)}

    def decay_all(self, decay_pct: float = 1.0) -> int:
        count = 0
        for edge in self._edges.values():
            old = edge.trust_score
            diff = edge.trust_score - self._default_trust
            edge.trust_score -= diff * (decay_pct / 100.0)
            edge.trust_score = max(0.0, min(100.0, edge.trust_score))
            if abs(edge.trust_score - old) > 0.001:
                count += 1
        return count

    def list_edges(self, min_trust: float = 0.0, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for e in self._edges.values():
            if e.trust_score < min_trust:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_edge(e.from_agent, e.to_agent))
        return [r for r in results if r]

    def get_history(self, from_agent: str = "", to_agent: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if from_agent and ev.from_agent != from_agent:
                continue
            if to_agent and ev.to_agent != to_agent:
                continue
            if action and ev.action != action:
                continue
            results.append({"event_id": ev.event_id, "from_agent": ev.from_agent, "to_agent": ev.to_agent, "action": ev.action, "old_score": ev.old_score, "new_score": ev.new_score, "timestamp": ev.timestamp})
            if len(results) >= limit:
                break
        return results

    def _record_event(self, from_agent: str, to_agent: str, action: str, old_score: float, new_score: float) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{from_agent}-{to_agent}-{action}-{now}-{self._seq}"
        evid = "trv-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _TrustEvent(event_id=evid, from_agent=from_agent, to_agent=to_agent, action=action, old_score=old_score, new_score=new_score, timestamp=now)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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

    def get_stats(self) -> Dict[str, Any]:
        return {"current_edges": len(self._edges), "total_created": self._total_created, "total_updates": self._total_updates, "history_size": len(self._history)}

    def reset(self) -> None:
        self._edges.clear()
        self._pair_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_updates = 0
