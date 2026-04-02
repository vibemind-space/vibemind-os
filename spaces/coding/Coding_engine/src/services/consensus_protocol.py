"""
Consensus Protocol — multi-agent agreement system for pipeline decisions.

Features:
- Proposal creation with configurable voting rules
- Vote collection (approve/reject/abstain)
- Quorum and majority thresholds
- Timeout-based auto-resolution
- Weighted voting (optional)
- Proposal lifecycle tracking
- Voting history and audit trail
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

VOTE_OPTIONS = {"approve", "reject", "abstain"}


@dataclass
class Vote:
    """A single vote on a proposal."""
    voter: str
    choice: str  # approve, reject, abstain
    weight: float
    timestamp: float
    reason: str


@dataclass
class Proposal:
    """A consensus proposal."""
    proposal_id: str
    title: str
    description: str
    proposer: str
    created_at: float
    deadline: float  # 0 = no deadline
    status: str  # "open", "approved", "rejected", "expired", "cancelled"
    quorum: int  # minimum votes required
    threshold: float  # fraction of approve votes needed (0.0-1.0)
    eligible_voters: Set[str]
    votes: Dict[str, Vote] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    resolved_at: float = 0.0
    on_approved: Optional[Callable] = None
    on_rejected: Optional[Callable] = None


# ---------------------------------------------------------------------------
# Consensus Protocol
# ---------------------------------------------------------------------------

class ConsensusProtocol:
    """Multi-agent consensus and voting system."""

    def __init__(
        self,
        default_quorum: int = 2,
        default_threshold: float = 0.5,
        default_deadline_seconds: float = 300.0,
        max_proposals: int = 1000,
    ):
        self._default_quorum = default_quorum
        self._default_threshold = default_threshold
        self._default_deadline = default_deadline_seconds
        self._max_proposals = max_proposals

        self._proposals: Dict[str, Proposal] = {}
        self._voter_weights: Dict[str, float] = {}

        self._stats = {
            "total_proposals": 0,
            "total_votes": 0,
            "total_approved": 0,
            "total_rejected": 0,
            "total_expired": 0,
        }

    # ------------------------------------------------------------------
    # Voter management
    # ------------------------------------------------------------------

    def register_voter(self, name: str, weight: float = 1.0) -> bool:
        """Register a voter with optional weight."""
        if name in self._voter_weights:
            return False
        self._voter_weights[name] = max(0.1, weight)
        return True

    def unregister_voter(self, name: str) -> bool:
        """Unregister a voter."""
        if name not in self._voter_weights:
            return False
        del self._voter_weights[name]
        return True

    def list_voters(self) -> List[Dict]:
        """List registered voters."""
        return sorted([
            {"name": n, "weight": w}
            for n, w in self._voter_weights.items()
        ], key=lambda x: x["name"])

    # ------------------------------------------------------------------
    # Proposal lifecycle
    # ------------------------------------------------------------------

    def create_proposal(
        self,
        title: str,
        proposer: str,
        description: str = "",
        eligible_voters: Optional[Set[str]] = None,
        quorum: int = 0,
        threshold: float = 0.0,
        deadline_seconds: float = 0.0,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
        on_approved: Optional[Callable] = None,
        on_rejected: Optional[Callable] = None,
    ) -> str:
        """Create a new proposal. Returns proposal_id."""
        pid = f"prop-{uuid.uuid4().hex[:8]}"
        now = time.time()

        q = quorum if quorum > 0 else self._default_quorum
        t = threshold if threshold > 0 else self._default_threshold
        dl = deadline_seconds if deadline_seconds > 0 else self._default_deadline
        deadline = now + dl if dl > 0 else 0.0

        # Default eligible: all registered voters
        voters = eligible_voters or set(self._voter_weights.keys())

        self._proposals[pid] = Proposal(
            proposal_id=pid,
            title=title,
            description=description,
            proposer=proposer,
            created_at=now,
            deadline=deadline,
            status="open",
            quorum=q,
            threshold=t,
            eligible_voters=voters,
            tags=tags or set(),
            metadata=metadata or {},
            on_approved=on_approved,
            on_rejected=on_rejected,
        )
        self._stats["total_proposals"] += 1
        self._prune()
        return pid

    def get_proposal(self, proposal_id: str) -> Optional[Dict]:
        """Get proposal details."""
        p = self._proposals.get(proposal_id)
        if not p:
            return None
        self._check_deadline(p)
        return self._proposal_to_dict(p)

    def list_proposals(
        self,
        status: Optional[str] = None,
        proposer: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List proposals with filters."""
        # Check deadlines first
        for p in self._proposals.values():
            self._check_deadline(p)

        results = []
        for p in sorted(self._proposals.values(),
                        key=lambda x: x.created_at, reverse=True):
            if status and p.status != status:
                continue
            if proposer and p.proposer != proposer:
                continue
            results.append(self._proposal_to_dict(p))
            if len(results) >= limit:
                break
        return results

    def cancel_proposal(self, proposal_id: str) -> bool:
        """Cancel an open proposal."""
        p = self._proposals.get(proposal_id)
        if not p or p.status != "open":
            return False
        p.status = "cancelled"
        p.resolved_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def vote(
        self,
        proposal_id: str,
        voter: str,
        choice: str,
        reason: str = "",
    ) -> bool:
        """Cast a vote on a proposal."""
        p = self._proposals.get(proposal_id)
        if not p:
            return False

        self._check_deadline(p)
        if p.status != "open":
            return False

        if choice not in VOTE_OPTIONS:
            return False

        if voter not in p.eligible_voters:
            return False

        # Already voted?
        if voter in p.votes:
            return False

        weight = self._voter_weights.get(voter, 1.0)
        p.votes[voter] = Vote(
            voter=voter,
            choice=choice,
            weight=weight,
            timestamp=time.time(),
            reason=reason,
        )
        self._stats["total_votes"] += 1

        # Check if resolved
        self._check_resolution(p)
        return True

    def get_votes(self, proposal_id: str) -> List[Dict]:
        """Get all votes for a proposal."""
        p = self._proposals.get(proposal_id)
        if not p:
            return []
        return sorted([
            {
                "voter": v.voter,
                "choice": v.choice,
                "weight": v.weight,
                "timestamp": v.timestamp,
                "reason": v.reason,
            }
            for v in p.votes.values()
        ], key=lambda x: x["timestamp"])

    def get_tally(self, proposal_id: str) -> Optional[Dict]:
        """Get current vote tally."""
        p = self._proposals.get(proposal_id)
        if not p:
            return None

        approve_weight = sum(
            v.weight for v in p.votes.values() if v.choice == "approve"
        )
        reject_weight = sum(
            v.weight for v in p.votes.values() if v.choice == "reject"
        )
        abstain_weight = sum(
            v.weight for v in p.votes.values() if v.choice == "abstain"
        )
        total_weight = approve_weight + reject_weight + abstain_weight
        total_votes = len(p.votes)

        approve_pct = 0.0
        if total_weight > 0:
            approve_pct = round(approve_weight / total_weight * 100, 2)

        return {
            "proposal_id": proposal_id,
            "total_votes": total_votes,
            "quorum": p.quorum,
            "quorum_met": total_votes >= p.quorum,
            "threshold": p.threshold,
            "approve_weight": round(approve_weight, 2),
            "reject_weight": round(reject_weight, 2),
            "abstain_weight": round(abstain_weight, 2),
            "approve_percent": approve_pct,
            "remaining_voters": sorted(
                p.eligible_voters - set(p.votes.keys())
            ),
        }

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _check_deadline(self, p: Proposal) -> None:
        """Check if proposal has expired."""
        if p.status != "open":
            return
        if p.deadline > 0 and time.time() > p.deadline:
            p.status = "expired"
            p.resolved_at = time.time()
            self._stats["total_expired"] += 1

    def _check_resolution(self, p: Proposal) -> None:
        """Check if proposal can be resolved based on votes."""
        if p.status != "open":
            return

        total_votes = len(p.votes)
        if total_votes < p.quorum:
            return

        approve_weight = sum(
            v.weight for v in p.votes.values() if v.choice == "approve"
        )
        reject_weight = sum(
            v.weight for v in p.votes.values() if v.choice == "reject"
        )
        total_decisive = approve_weight + reject_weight
        if total_decisive == 0:
            return

        approve_ratio = approve_weight / total_decisive

        if approve_ratio >= p.threshold:
            p.status = "approved"
            p.resolved_at = time.time()
            self._stats["total_approved"] += 1
            if p.on_approved:
                try:
                    p.on_approved(self._proposal_to_dict(p))
                except Exception:
                    pass
        elif reject_weight / total_decisive > (1.0 - p.threshold):
            p.status = "rejected"
            p.resolved_at = time.time()
            self._stats["total_rejected"] += 1
            if p.on_rejected:
                try:
                    p.on_rejected(self._proposal_to_dict(p))
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def get_voter_history(self, voter: str, limit: int = 50) -> List[Dict]:
        """Get voting history for a voter."""
        results = []
        for p in sorted(self._proposals.values(),
                        key=lambda x: x.created_at, reverse=True):
            if voter in p.votes:
                v = p.votes[voter]
                results.append({
                    "proposal_id": p.proposal_id,
                    "title": p.title,
                    "choice": v.choice,
                    "weight": v.weight,
                    "timestamp": v.timestamp,
                    "proposal_status": p.status,
                })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _proposal_to_dict(self, p: Proposal) -> Dict:
        approve = sum(1 for v in p.votes.values() if v.choice == "approve")
        reject = sum(1 for v in p.votes.values() if v.choice == "reject")
        abstain = sum(1 for v in p.votes.values() if v.choice == "abstain")
        return {
            "proposal_id": p.proposal_id,
            "title": p.title,
            "description": p.description,
            "proposer": p.proposer,
            "status": p.status,
            "created_at": p.created_at,
            "deadline": p.deadline,
            "resolved_at": p.resolved_at,
            "quorum": p.quorum,
            "threshold": p.threshold,
            "total_votes": len(p.votes),
            "approves": approve,
            "rejects": reject,
            "abstains": abstain,
            "eligible_count": len(p.eligible_voters),
            "tags": sorted(p.tags),
            "metadata": p.metadata,
        }

    def _prune(self) -> None:
        if len(self._proposals) <= self._max_proposals:
            return
        closed = sorted(
            [p for p in self._proposals.values()
             if p.status in ("approved", "rejected", "expired", "cancelled")],
            key=lambda x: x.created_at,
        )
        to_remove = len(self._proposals) - self._max_proposals
        for p in closed[:to_remove]:
            del self._proposals[p.proposal_id]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_active_proposals": sum(
                1 for p in self._proposals.values() if p.status == "open"
            ),
            "total_voters": len(self._voter_weights),
            "total_stored_proposals": len(self._proposals),
        }

    def reset(self) -> None:
        self._proposals.clear()
        self._voter_weights.clear()
        self._stats = {k: 0 for k in self._stats}
