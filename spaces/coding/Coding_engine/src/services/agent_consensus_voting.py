"""Agent consensus voting - multi-agent decision making through voting protocols."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Proposal:
    proposal_id: str
    title: str
    description: str
    proposer: str
    options: List[str]
    voting_method: str  # majority, supermajority, unanimous, ranked, weighted
    required_voters: Set[str]
    min_votes: int
    deadline: float  # timestamp
    status: str  # open, closed, passed, failed, expired
    votes: Dict[str, Any]  # voter -> vote value
    weights: Dict[str, float]  # voter -> weight (for weighted voting)
    created_at: float = 0.0
    closed_at: float = 0.0
    result: str = ""
    metadata: Dict = field(default_factory=dict)


class AgentConsensusVoting:
    """Multi-agent consensus voting system with multiple voting protocols."""

    VOTING_METHODS = ("majority", "supermajority", "unanimous", "ranked", "weighted")

    def __init__(self, max_proposals: int = 5000, max_voters: int = 1000):
        self._max_proposals = max_proposals
        self._max_voters = max_voters
        self._proposals: Dict[str, _Proposal] = {}
        self._voters: Dict[str, Dict] = {}  # name -> {weight, groups, registered_at}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_proposals": 0,
            "total_votes_cast": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_expired": 0,
        }

    # ── Voter Management ──

    def register_voter(self, name: str, weight: float = 1.0,
                       groups: Optional[Set[str]] = None, metadata: Optional[Dict] = None) -> bool:
        """Register a voter."""
        if name in self._voters or len(self._voters) >= self._max_voters:
            return False
        if weight <= 0:
            return False
        self._voters[name] = {
            "name": name,
            "weight": weight,
            "groups": groups or set(),
            "registered_at": time.time(),
            "total_votes": 0,
            "metadata": metadata or {},
        }
        return True

    def unregister_voter(self, name: str) -> bool:
        """Unregister a voter."""
        if name not in self._voters:
            return False
        del self._voters[name]
        return True

    def get_voter(self, name: str) -> Optional[Dict]:
        """Get voter info."""
        v = self._voters.get(name)
        if not v:
            return None
        return {**v, "groups": set(v["groups"])}

    def set_voter_weight(self, name: str, weight: float) -> bool:
        """Set voter weight."""
        if name not in self._voters or weight <= 0:
            return False
        self._voters[name]["weight"] = weight
        return True

    def add_voter_group(self, name: str, group: str) -> bool:
        """Add voter to a group."""
        if name not in self._voters:
            return False
        if group in self._voters[name]["groups"]:
            return False
        self._voters[name]["groups"].add(group)
        return True

    def remove_voter_group(self, name: str, group: str) -> bool:
        """Remove voter from a group."""
        if name not in self._voters or group not in self._voters[name]["groups"]:
            return False
        self._voters[name]["groups"].discard(group)
        return True

    def list_voters(self, group: str = "") -> List[Dict]:
        """List voters, optionally filtered by group."""
        result = []
        for v in self._voters.values():
            if group and group not in v["groups"]:
                continue
            result.append({**v, "groups": set(v["groups"])})
        return result

    # ── Proposal Management ──

    def create_proposal(self, title: str, description: str, proposer: str,
                        options: Optional[List[str]] = None,
                        voting_method: str = "majority",
                        required_voters: Optional[Set[str]] = None,
                        min_votes: int = 1,
                        deadline_seconds: float = 3600.0,
                        voter_weights: Optional[Dict[str, float]] = None,
                        metadata: Optional[Dict] = None) -> str:
        """Create a new proposal."""
        if voting_method not in self.VOTING_METHODS:
            return ""
        if len(self._proposals) >= self._max_proposals:
            return ""
        if proposer not in self._voters:
            return ""
        if min_votes < 1:
            return ""

        # Default options for simple yes/no
        if not options:
            options = ["yes", "no"]
        if len(options) < 2:
            return ""

        # Validate required voters exist
        req = required_voters or set()
        for v in req:
            if v not in self._voters:
                return ""

        pid = f"prop-{uuid.uuid4().hex[:12]}"
        now = time.time()
        self._proposals[pid] = _Proposal(
            proposal_id=pid,
            title=title,
            description=description,
            proposer=proposer,
            options=list(options),
            voting_method=voting_method,
            required_voters=set(req),
            min_votes=min_votes,
            deadline=now + deadline_seconds,
            status="open",
            votes={},
            weights=voter_weights or {},
            created_at=now,
            metadata=metadata or {},
        )
        self._stats["total_proposals"] += 1
        return pid

    def get_proposal(self, proposal_id: str) -> Optional[Dict]:
        """Get proposal info."""
        self._check_expired(proposal_id)
        p = self._proposals.get(proposal_id)
        if not p:
            return None
        return {
            "proposal_id": p.proposal_id,
            "title": p.title,
            "description": p.description,
            "proposer": p.proposer,
            "options": list(p.options),
            "voting_method": p.voting_method,
            "required_voters": set(p.required_voters),
            "min_votes": p.min_votes,
            "status": p.status,
            "votes_count": len(p.votes),
            "result": p.result,
            "created_at": p.created_at,
            "closed_at": p.closed_at,
        }

    def cancel_proposal(self, proposal_id: str) -> bool:
        """Cancel an open proposal."""
        p = self._proposals.get(proposal_id)
        if not p or p.status != "open":
            return False
        p.status = "cancelled"
        p.closed_at = time.time()
        return True

    def list_proposals(self, status: str = "", proposer: str = "", limit: int = 50) -> List[Dict]:
        """List proposals with optional filters."""
        result = []
        for p in self._proposals.values():
            self._check_expired(p.proposal_id)
            if status and p.status != status:
                continue
            if proposer and p.proposer != proposer:
                continue
            result.append({
                "proposal_id": p.proposal_id,
                "title": p.title,
                "proposer": p.proposer,
                "voting_method": p.voting_method,
                "status": p.status,
                "votes_count": len(p.votes),
                "result": p.result,
            })
            if len(result) >= limit:
                break
        return result

    # ── Voting ──

    def cast_vote(self, proposal_id: str, voter: str, vote: Any) -> bool:
        """Cast a vote on a proposal."""
        self._check_expired(proposal_id)
        p = self._proposals.get(proposal_id)
        if not p or p.status != "open":
            return False
        if voter not in self._voters:
            return False
        if voter in p.votes:
            return False  # Already voted

        # Validate vote value
        if p.voting_method == "ranked":
            # Vote should be a list of options in preference order
            if not isinstance(vote, list):
                return False
            if set(vote) != set(p.options):
                return False
        else:
            # Vote should be one of the options
            if vote not in p.options:
                return False

        p.votes[voter] = vote
        self._voters[voter]["total_votes"] += 1
        self._stats["total_votes_cast"] += 1

        self._fire_callbacks("vote", proposal_id, voter)
        return True

    def change_vote(self, proposal_id: str, voter: str, new_vote: Any) -> bool:
        """Change an existing vote."""
        p = self._proposals.get(proposal_id)
        if not p or p.status != "open":
            return False
        if voter not in p.votes:
            return False

        # Validate new vote
        if p.voting_method == "ranked":
            if not isinstance(new_vote, list) or set(new_vote) != set(p.options):
                return False
        else:
            if new_vote not in p.options:
                return False

        p.votes[voter] = new_vote
        return True

    def get_votes(self, proposal_id: str) -> Dict[str, Any]:
        """Get all votes for a proposal."""
        p = self._proposals.get(proposal_id)
        if not p:
            return {}
        return dict(p.votes)

    def has_voted(self, proposal_id: str, voter: str) -> bool:
        """Check if a voter has voted."""
        p = self._proposals.get(proposal_id)
        if not p:
            return False
        return voter in p.votes

    # ── Tallying ──

    def tally(self, proposal_id: str) -> Optional[Dict]:
        """Tally votes without closing."""
        p = self._proposals.get(proposal_id)
        if not p:
            return None
        return self._compute_tally(p)

    def close_and_tally(self, proposal_id: str) -> Optional[Dict]:
        """Close voting and compute final result."""
        self._check_expired(proposal_id)
        p = self._proposals.get(proposal_id)
        if not p or p.status != "open":
            return None

        # Check min votes
        if len(p.votes) < p.min_votes:
            p.status = "failed"
            p.result = "insufficient_votes"
            p.closed_at = time.time()
            self._stats["total_failed"] += 1
            self._fire_callbacks("failed", proposal_id, "")
            return self._compute_tally(p)

        # Check required voters
        if p.required_voters:
            missing = p.required_voters - set(p.votes.keys())
            if missing:
                p.status = "failed"
                p.result = "missing_required_voters"
                p.closed_at = time.time()
                self._stats["total_failed"] += 1
                self._fire_callbacks("failed", proposal_id, "")
                return self._compute_tally(p)

        tally = self._compute_tally(p)
        winner = tally.get("winner", "")

        if winner:
            p.status = "passed"
            p.result = winner
            self._stats["total_passed"] += 1
            self._fire_callbacks("passed", proposal_id, winner)
        else:
            p.status = "failed"
            p.result = "no_winner"
            self._stats["total_failed"] += 1
            self._fire_callbacks("failed", proposal_id, "")

        p.closed_at = time.time()
        return tally

    def _compute_tally(self, p: _Proposal) -> Dict:
        """Compute vote tally based on voting method."""
        method = p.voting_method
        votes = p.votes
        options = p.options
        total_voters = len(votes)

        if method == "majority":
            return self._tally_majority(votes, options, total_voters, threshold=0.5)
        elif method == "supermajority":
            return self._tally_majority(votes, options, total_voters, threshold=2/3)
        elif method == "unanimous":
            return self._tally_unanimous(votes, options, total_voters)
        elif method == "ranked":
            return self._tally_ranked(votes, options)
        elif method == "weighted":
            return self._tally_weighted(votes, options, p.weights)
        return {"counts": {}, "winner": "", "total_votes": 0}

    def _tally_majority(self, votes: Dict, options: List[str],
                        total: int, threshold: float) -> Dict:
        counts = {o: 0 for o in options}
        for v in votes.values():
            if v in counts:
                counts[v] += 1

        winner = ""
        if total > 0:
            for opt, cnt in counts.items():
                if cnt / total > threshold:
                    winner = opt
                    break

        return {"counts": counts, "winner": winner, "total_votes": total,
                "threshold": threshold}

    def _tally_unanimous(self, votes: Dict, options: List[str], total: int) -> Dict:
        counts = {o: 0 for o in options}
        for v in votes.values():
            if v in counts:
                counts[v] += 1

        winner = ""
        if total > 0:
            for opt, cnt in counts.items():
                if cnt == total:
                    winner = opt
                    break

        return {"counts": counts, "winner": winner, "total_votes": total}

    def _tally_ranked(self, votes: Dict, options: List[str]) -> Dict:
        """Instant-runoff / ranked-choice tally."""
        if not votes:
            return {"rounds": [], "winner": "", "total_votes": 0}

        # Copy rankings
        active_votes = {v: list(ranking) for v, ranking in votes.items()}
        eliminated = set()
        rounds = []

        while True:
            # Count first preferences
            counts = {o: 0 for o in options if o not in eliminated}
            for ranking in active_votes.values():
                for choice in ranking:
                    if choice not in eliminated:
                        counts[choice] += 1
                        break

            total = sum(counts.values())
            rounds.append(dict(counts))

            # Check for majority
            for opt, cnt in counts.items():
                if total > 0 and cnt / total > 0.5:
                    return {"rounds": rounds, "winner": opt, "total_votes": len(votes)}

            # Eliminate lowest
            if not counts:
                break
            min_count = min(counts.values())
            for opt, cnt in counts.items():
                if cnt == min_count:
                    eliminated.add(opt)
                    break

            if len(eliminated) >= len(options):
                break

        return {"rounds": rounds, "winner": "", "total_votes": len(votes)}

    def _tally_weighted(self, votes: Dict, options: List[str],
                        proposal_weights: Dict[str, float]) -> Dict:
        counts = {o: 0.0 for o in options}
        for voter, vote in votes.items():
            # Use proposal-specific weight, then voter default, then 1.0
            w = proposal_weights.get(voter,
                    self._voters.get(voter, {}).get("weight", 1.0))
            if vote in counts:
                counts[vote] += w

        total_weight = sum(counts.values())
        winner = ""
        if total_weight > 0:
            best = max(counts, key=counts.get)
            if counts[best] / total_weight > 0.5:
                winner = best

        return {"counts": counts, "winner": winner, "total_votes": len(votes),
                "total_weight": total_weight}

    # ── Expiry ──

    def _check_expired(self, proposal_id: str) -> None:
        p = self._proposals.get(proposal_id)
        if p and p.status == "open" and time.time() > p.deadline:
            p.status = "expired"
            p.closed_at = time.time()
            self._stats["total_expired"] += 1
            self._fire_callbacks("expired", proposal_id, "")

    # ── Callbacks ──

    def on_event(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, action: str, proposal_id: str, data: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, proposal_id, data)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_voters": len(self._voters),
            "total_active_proposals": sum(
                1 for p in self._proposals.values() if p.status == "open"
            ),
        }

    def reset(self) -> None:
        self._proposals.clear()
        self._voters.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
