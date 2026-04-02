"""Agent Negotiation Engine – enables agents to negotiate over shared resources.

Agents submit proposals, counter-proposals, and votes.  The engine tracks
negotiation rounds, consensus, and resolution history.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Negotiation:
    negotiation_id: str
    topic: str
    status: str  # open, resolved, failed, cancelled
    participants: List[str]
    proposals: List[Dict[str, Any]]
    rounds: int
    max_rounds: int
    winner: str
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _NegotiationEvent:
    event_id: str
    negotiation_id: str
    action: str
    agent: str
    timestamp: float


class AgentNegotiationEngine:
    """Enables agents to negotiate over shared resources."""

    STATUSES = ("open", "resolved", "failed", "cancelled")

    def __init__(self, max_negotiations: int = 10000, max_history: int = 100000, default_max_rounds: int = 10):
        self._negotiations: Dict[str, _Negotiation] = {}
        self._history: List[_NegotiationEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_negotiations = max_negotiations
        self._max_history = max_history
        self._default_max_rounds = default_max_rounds
        self._seq = 0
        self._total_created = 0
        self._total_resolved = 0
        self._total_failed = 0

    def create_negotiation(self, topic: str, participants: List[str], max_rounds: int = 0, tags: Optional[List[str]] = None) -> str:
        if not topic or len(participants) < 2:
            return ""
        if len(self._negotiations) >= self._max_negotiations:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{topic}-{now}-{self._seq}"
        nid = "neg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        neg = _Negotiation(
            negotiation_id=nid, topic=topic, status="open",
            participants=list(participants), proposals=[],
            rounds=0, max_rounds=max_rounds if max_rounds > 0 else self._default_max_rounds,
            winner="", tags=tags or [], created_at=now, updated_at=now,
        )
        self._negotiations[nid] = neg
        self._total_created += 1
        self._record_event(nid, "created", "")
        self._fire("negotiation_created", {"negotiation_id": nid, "topic": topic})
        return nid

    def submit_proposal(self, negotiation_id: str, agent: str, value: Any, justification: str = "") -> bool:
        neg = self._negotiations.get(negotiation_id)
        if not neg or neg.status != "open":
            return False
        if agent not in neg.participants:
            return False
        neg.proposals.append({"agent": agent, "value": value, "justification": justification, "votes": [], "round": neg.rounds + 1})
        neg.rounds = max(neg.rounds, len(set(p["round"] for p in neg.proposals)))
        neg.updated_at = time.time()
        self._record_event(negotiation_id, "proposal_submitted", agent)
        self._fire("proposal_submitted", {"negotiation_id": negotiation_id, "agent": agent})
        if neg.rounds >= neg.max_rounds:
            self._resolve_by_votes(neg)
        return True

    def vote(self, negotiation_id: str, voter: str, proposal_index: int) -> bool:
        neg = self._negotiations.get(negotiation_id)
        if not neg or neg.status != "open":
            return False
        if voter not in neg.participants:
            return False
        if proposal_index < 0 or proposal_index >= len(neg.proposals):
            return False
        proposal = neg.proposals[proposal_index]
        if voter in proposal["votes"]:
            return False
        proposal["votes"].append(voter)
        neg.updated_at = time.time()
        self._record_event(negotiation_id, "voted", voter)
        # Check if majority reached
        majority = len(neg.participants) // 2 + 1
        if len(proposal["votes"]) >= majority:
            neg.status = "resolved"
            neg.winner = proposal["agent"]
            self._total_resolved += 1
            self._record_event(negotiation_id, "resolved", proposal["agent"])
            self._fire("negotiation_resolved", {"negotiation_id": negotiation_id, "winner": proposal["agent"]})
        return True

    def _resolve_by_votes(self, neg: _Negotiation) -> None:
        if not neg.proposals:
            neg.status = "failed"
            self._total_failed += 1
            self._fire("negotiation_failed", {"negotiation_id": neg.negotiation_id})
            return
        best = max(neg.proposals, key=lambda p: len(p["votes"]))
        if len(best["votes"]) > 0:
            neg.status = "resolved"
            neg.winner = best["agent"]
            self._total_resolved += 1
            self._fire("negotiation_resolved", {"negotiation_id": neg.negotiation_id, "winner": best["agent"]})
        else:
            neg.status = "failed"
            self._total_failed += 1
            self._fire("negotiation_failed", {"negotiation_id": neg.negotiation_id})

    def cancel_negotiation(self, negotiation_id: str) -> bool:
        neg = self._negotiations.get(negotiation_id)
        if not neg or neg.status != "open":
            return False
        neg.status = "cancelled"
        neg.updated_at = time.time()
        self._record_event(negotiation_id, "cancelled", "")
        self._fire("negotiation_cancelled", {"negotiation_id": negotiation_id})
        return True

    def get_negotiation(self, negotiation_id: str) -> Optional[Dict[str, Any]]:
        neg = self._negotiations.get(negotiation_id)
        if not neg:
            return None
        return {
            "negotiation_id": neg.negotiation_id, "topic": neg.topic, "status": neg.status,
            "participants": list(neg.participants), "proposals": list(neg.proposals),
            "rounds": neg.rounds, "max_rounds": neg.max_rounds, "winner": neg.winner,
            "tags": list(neg.tags), "created_at": neg.created_at, "updated_at": neg.updated_at,
        }

    def list_negotiations(self, status: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for neg in self._negotiations.values():
            if status and neg.status != status:
                continue
            if tag and tag not in neg.tags:
                continue
            results.append(self.get_negotiation(neg.negotiation_id))
        return results

    def get_history(self, negotiation_id: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if negotiation_id and ev.negotiation_id != negotiation_id:
                continue
            if action and ev.action != action:
                continue
            results.append({"event_id": ev.event_id, "negotiation_id": ev.negotiation_id, "action": ev.action, "agent": ev.agent, "timestamp": ev.timestamp})
            if len(results) >= limit:
                break
        return results

    def _record_event(self, negotiation_id: str, action: str, agent: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{negotiation_id}-{action}-{now}-{self._seq}"
        evid = "nev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _NegotiationEvent(event_id=evid, negotiation_id=negotiation_id, action=action, agent=agent, timestamp=now)
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
        return {
            "current_negotiations": len(self._negotiations),
            "open": sum(1 for n in self._negotiations.values() if n.status == "open"),
            "total_created": self._total_created,
            "total_resolved": self._total_resolved,
            "total_failed": self._total_failed,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._negotiations.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_resolved = 0
        self._total_failed = 0
