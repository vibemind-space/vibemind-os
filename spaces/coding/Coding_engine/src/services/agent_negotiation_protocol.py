"""Agent Negotiation Protocol – structured multi-party negotiation between agents.

Agents create negotiations, submit proposals with priority, accept/reject/counter,
and resolve via configurable strategies (highest_priority, first_come, consensus).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Proposal:
    proposal_id: str
    negotiation_id: str
    agent_id: str
    offer: Any
    priority: float
    status: str  # pending, accepted, rejected, countered
    parent_proposal_id: str
    created_at: float


@dataclass
class _Negotiation:
    negotiation_id: str
    topic: str
    initiator: str
    participants: List[str]
    resource: str
    status: str  # open, accepted, resolved, expired
    tags: List[str]
    proposal_ids: List[str]
    accepted_proposal: str
    created_at: float
    updated_at: float


@dataclass
class _HistoryEntry:
    action: str
    detail: Dict[str, Any]
    timestamp: float


class AgentNegotiationProtocol:
    """Multi-party negotiation protocol with proposals, counters, and resolution strategies."""

    STATUSES = ("open", "accepted", "resolved", "expired")
    STRATEGIES = ("highest_priority", "first_come", "consensus")

    def __init__(self, max_entries: int = 10000, max_history: int = 50000):
        self._negotiations: Dict[str, _Negotiation] = {}
        self._proposals: Dict[str, _Proposal] = {}
        self._history: List[_HistoryEntry] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0
        self._total_negotiations = 0
        self._total_proposals = 0
        self._total_accepted = 0
        self._total_rejected = 0
        self._total_resolved = 0
        self._total_removed = 0

    # ── ID Generation ──

    def _generate_id(self, prefix: str, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}{digest}"

    # ── Negotiation Lifecycle ──

    def create_negotiation(
        self,
        topic: str,
        initiator: str,
        participants: List[str],
        resource: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Start a new negotiation. Returns negotiation ID (anp-...)."""
        if not topic or not initiator or not participants:
            return ""
        if len(self._negotiations) >= self._max_entries:
            self._prune_negotiations()
        if len(self._negotiations) >= self._max_entries:
            return ""

        nid = self._generate_id("anp-", f"neg-{topic}-{initiator}")
        now = time.time()
        neg = _Negotiation(
            negotiation_id=nid,
            topic=topic,
            initiator=initiator,
            participants=list(participants),
            resource=resource or "",
            status="open",
            tags=list(tags) if tags else [],
            proposal_ids=[],
            accepted_proposal="",
            created_at=now,
            updated_at=now,
        )
        self._negotiations[nid] = neg
        self._total_negotiations += 1
        self._record_history("negotiation_created", {
            "negotiation_id": nid, "topic": topic, "initiator": initiator,
        })
        self._fire("negotiation_created", {"negotiation_id": nid, "topic": topic})
        return nid

    def get_negotiation(self, negotiation_id: str) -> Optional[Dict[str, Any]]:
        """Get negotiation state as a dict."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None:
            return None
        return {
            "negotiation_id": neg.negotiation_id,
            "topic": neg.topic,
            "initiator": neg.initiator,
            "participants": list(neg.participants),
            "resource": neg.resource,
            "status": neg.status,
            "tags": list(neg.tags),
            "proposal_count": len(neg.proposal_ids),
            "accepted_proposal": neg.accepted_proposal,
            "created_at": neg.created_at,
            "updated_at": neg.updated_at,
        }

    def list_negotiations(
        self, status: Optional[str] = None, tag: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List negotiations, optionally filtered by status or tag."""
        results: List[Dict[str, Any]] = []
        for neg in self._negotiations.values():
            if status is not None and neg.status != status:
                continue
            if tag is not None and tag not in neg.tags:
                continue
            results.append({
                "negotiation_id": neg.negotiation_id,
                "topic": neg.topic,
                "initiator": neg.initiator,
                "status": neg.status,
                "tags": list(neg.tags),
                "proposal_count": len(neg.proposal_ids),
                "created_at": neg.created_at,
            })
        return results

    def remove_negotiation(self, negotiation_id: str) -> bool:
        """Remove a negotiation and its proposals."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None:
            return False
        for pid in neg.proposal_ids:
            self._proposals.pop(pid, None)
        del self._negotiations[negotiation_id]
        self._total_removed += 1
        self._record_history("negotiation_removed", {"negotiation_id": negotiation_id})
        self._fire("negotiation_removed", {"negotiation_id": negotiation_id})
        return True

    # ── Proposals ──

    def submit_proposal(
        self,
        negotiation_id: str,
        agent_id: str,
        offer: Any,
        priority: float = 1.0,
    ) -> str:
        """Submit a proposal to a negotiation. Returns proposal ID (anp-...)."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None or neg.status != "open":
            return ""
        if not agent_id:
            return ""
        if len(self._proposals) >= self._max_entries:
            self._prune_proposals()
        if len(self._proposals) >= self._max_entries:
            return ""

        pid = self._generate_id("anp-", f"prop-{negotiation_id}-{agent_id}")
        now = time.time()
        prop = _Proposal(
            proposal_id=pid,
            negotiation_id=negotiation_id,
            agent_id=agent_id,
            offer=offer,
            priority=priority,
            status="pending",
            parent_proposal_id="",
            created_at=now,
        )
        self._proposals[pid] = prop
        neg.proposal_ids.append(pid)
        neg.updated_at = now
        self._total_proposals += 1
        self._record_history("proposal_submitted", {
            "proposal_id": pid, "negotiation_id": negotiation_id, "agent_id": agent_id,
        })
        self._fire("proposal_submitted", {
            "proposal_id": pid, "negotiation_id": negotiation_id,
        })
        return pid

    def get_proposals(self, negotiation_id: str) -> List[Dict[str, Any]]:
        """Get all proposals for a negotiation."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None:
            return []
        results: List[Dict[str, Any]] = []
        for pid in neg.proposal_ids:
            prop = self._proposals.get(pid)
            if prop is None:
                continue
            results.append({
                "proposal_id": prop.proposal_id,
                "negotiation_id": prop.negotiation_id,
                "agent_id": prop.agent_id,
                "offer": prop.offer,
                "priority": prop.priority,
                "status": prop.status,
                "parent_proposal_id": prop.parent_proposal_id,
                "created_at": prop.created_at,
            })
        return results

    def accept_proposal(self, negotiation_id: str, proposal_id: str) -> bool:
        """Accept a proposal, closing the negotiation."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None or neg.status != "open":
            return False
        prop = self._proposals.get(proposal_id)
        if prop is None or prop.negotiation_id != negotiation_id:
            return False
        if prop.status != "pending":
            return False

        prop.status = "accepted"
        neg.status = "accepted"
        neg.accepted_proposal = proposal_id
        neg.updated_at = time.time()
        self._total_accepted += 1

        # Reject remaining pending proposals
        for pid in neg.proposal_ids:
            other = self._proposals.get(pid)
            if other and other.proposal_id != proposal_id and other.status == "pending":
                other.status = "rejected"

        self._record_history("proposal_accepted", {
            "negotiation_id": negotiation_id, "proposal_id": proposal_id,
        })
        self._fire("proposal_accepted", {
            "negotiation_id": negotiation_id, "proposal_id": proposal_id,
        })
        return True

    def reject_proposal(
        self, negotiation_id: str, proposal_id: str, reason: str = ""
    ) -> bool:
        """Reject a proposal."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None or neg.status != "open":
            return False
        prop = self._proposals.get(proposal_id)
        if prop is None or prop.negotiation_id != negotiation_id:
            return False
        if prop.status != "pending":
            return False

        prop.status = "rejected"
        neg.updated_at = time.time()
        self._total_rejected += 1
        self._record_history("proposal_rejected", {
            "negotiation_id": negotiation_id, "proposal_id": proposal_id,
            "reason": reason,
        })
        self._fire("proposal_rejected", {
            "negotiation_id": negotiation_id, "proposal_id": proposal_id,
        })
        return True

    def counter_offer(
        self,
        negotiation_id: str,
        original_proposal_id: str,
        agent_id: str,
        new_offer: Any,
        priority: float = 1.0,
    ) -> str:
        """Submit a counter-offer referencing an original proposal."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None or neg.status != "open":
            return ""
        orig = self._proposals.get(original_proposal_id)
        if orig is None or orig.negotiation_id != negotiation_id:
            return ""
        if orig.status != "pending":
            return ""
        if not agent_id:
            return ""

        # Mark original as countered
        orig.status = "countered"

        pid = self._generate_id("anp-", f"counter-{negotiation_id}-{agent_id}")
        now = time.time()
        prop = _Proposal(
            proposal_id=pid,
            negotiation_id=negotiation_id,
            agent_id=agent_id,
            offer=new_offer,
            priority=priority,
            status="pending",
            parent_proposal_id=original_proposal_id,
            created_at=now,
        )
        self._proposals[pid] = prop
        neg.proposal_ids.append(pid)
        neg.updated_at = now
        self._total_proposals += 1
        self._record_history("counter_offer", {
            "proposal_id": pid, "original_proposal_id": original_proposal_id,
            "negotiation_id": negotiation_id, "agent_id": agent_id,
        })
        self._fire("counter_offer", {
            "proposal_id": pid, "negotiation_id": negotiation_id,
        })
        return pid

    # ── Resolution ──

    def resolve(
        self, negotiation_id: str, strategy: str = "highest_priority"
    ) -> Dict[str, Any]:
        """Auto-resolve a negotiation by strategy. Returns resolution result."""
        neg = self._negotiations.get(negotiation_id)
        if neg is None or neg.status != "open":
            return {"resolved": False, "reason": "not_open"}

        pending = [
            self._proposals[pid]
            for pid in neg.proposal_ids
            if pid in self._proposals and self._proposals[pid].status == "pending"
        ]
        if not pending:
            return {"resolved": False, "reason": "no_pending_proposals"}

        winner: Optional[_Proposal] = None

        if strategy == "highest_priority":
            winner = max(pending, key=lambda p: p.priority)
        elif strategy == "first_come":
            winner = min(pending, key=lambda p: p.created_at)
        elif strategy == "consensus":
            # Consensus: pick proposal from the agent who appears most often
            agent_counts: Dict[str, int] = {}
            for p in pending:
                agent_counts[p.agent_id] = agent_counts.get(p.agent_id, 0) + 1
            top_agent = max(agent_counts, key=lambda a: agent_counts[a])
            agent_proposals = [p for p in pending if p.agent_id == top_agent]
            winner = max(agent_proposals, key=lambda p: p.priority)
        else:
            return {"resolved": False, "reason": "unknown_strategy"}

        # Accept the winning proposal
        winner.status = "accepted"
        neg.status = "resolved"
        neg.accepted_proposal = winner.proposal_id
        neg.updated_at = time.time()
        self._total_resolved += 1

        # Reject remaining pending
        for pid in neg.proposal_ids:
            other = self._proposals.get(pid)
            if other and other.proposal_id != winner.proposal_id and other.status == "pending":
                other.status = "rejected"

        self._record_history("negotiation_resolved", {
            "negotiation_id": negotiation_id,
            "strategy": strategy,
            "winning_proposal": winner.proposal_id,
            "winning_agent": winner.agent_id,
        })
        self._fire("negotiation_resolved", {
            "negotiation_id": negotiation_id,
            "winning_proposal": winner.proposal_id,
        })
        return {
            "resolved": True,
            "strategy": strategy,
            "winning_proposal": winner.proposal_id,
            "winning_agent": winner.agent_id,
            "winning_offer": winner.offer,
            "winning_priority": winner.priority,
        }

    # ── Pruning ──

    def _prune_negotiations(self) -> None:
        """Remove oldest closed negotiations when over max_entries."""
        closed = [
            (nid, n.updated_at)
            for nid, n in self._negotiations.items()
            if n.status != "open"
        ]
        closed.sort(key=lambda x: x[1])
        to_remove = len(self._negotiations) - self._max_entries + 1
        for nid, _ in closed[:max(to_remove, 0)]:
            neg = self._negotiations.get(nid)
            if neg:
                for pid in neg.proposal_ids:
                    self._proposals.pop(pid, None)
                del self._negotiations[nid]

    def _prune_proposals(self) -> None:
        """Remove oldest non-pending proposals when over max_entries."""
        removable = [
            (pid, p.created_at)
            for pid, p in self._proposals.items()
            if p.status != "pending"
        ]
        removable.sort(key=lambda x: x[1])
        to_remove = len(self._proposals) - self._max_entries + 1
        for pid, _ in removable[:max(to_remove, 0)]:
            self._proposals.pop(pid, None)

    # ── History ──

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        if len(self._history) >= self._max_history:
            self._history = self._history[-(self._max_history // 2) :]
        self._history.append(_HistoryEntry(
            action=action, detail=dict(detail), timestamp=time.time(),
        ))

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent history entries."""
        entries = self._history[-limit:] if limit < len(self._history) else self._history
        return [
            {"action": h.action, "detail": h.detail, "timestamp": h.timestamp}
            for h in reversed(entries)
        ]

    # ── Callbacks ──

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

    # ── Stats & Reset ──

    def get_stats(self) -> Dict[str, Any]:
        """Return counters and current state summary."""
        open_count = sum(1 for n in self._negotiations.values() if n.status == "open")
        return {
            "total_negotiations": self._total_negotiations,
            "total_proposals": self._total_proposals,
            "total_accepted": self._total_accepted,
            "total_rejected": self._total_rejected,
            "total_resolved": self._total_resolved,
            "total_removed": self._total_removed,
            "current_negotiations": len(self._negotiations),
            "current_proposals": len(self._proposals),
            "open_negotiations": open_count,
            "history_size": len(self._history),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._negotiations.clear()
        self._proposals.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_negotiations = 0
        self._total_proposals = 0
        self._total_accepted = 0
        self._total_rejected = 0
        self._total_resolved = 0
        self._total_removed = 0
