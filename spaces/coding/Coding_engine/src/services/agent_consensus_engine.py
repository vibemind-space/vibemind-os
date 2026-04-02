"""Agent Consensus Engine -- manages structured proposal-based consensus decisions.

Agents create proposals with a set of options, then vote on them.
When any option reaches the required vote threshold the proposal is
automatically decided.  Supports callbacks for mutation events,
cancellation, per-agent vote history, and tally inspection.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal dataclass
# ------------------------------------------------------------------

@dataclass
class _ProposalRecord:
    """A single consensus proposal."""

    proposal_id: str = ""
    topic: str = ""
    options: List[str] = field(default_factory=list)
    required_votes: int = 2
    votes: Dict[str, str] = field(default_factory=dict)   # agent_id -> chosen option
    status: str = "open"          # open | decided | cancelled
    result: Optional[str] = None  # winning option once decided
    created_at: float = 0.0
    seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentConsensusEngine:
    """Enables agents to reach consensus through structured proposal voting.

    Parameters
    ----------
    max_proposals:
        Upper limit on stored proposals.  Oldest entries are *not*
        automatically pruned -- callers should cancel or let proposals
        decide naturally.
    """

    def __init__(self, max_proposals: int = 10000) -> None:
        self._max_proposals = max_proposals
        self._proposals: Dict[str, _ProposalRecord] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_created": 0,
            "total_votes": 0,
            "total_decided": 0,
            "total_cancelled": 0,
        }

        logger.debug("agent_consensus_engine.init", max_proposals=max_proposals)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, topic: str, now: float) -> str:
        """Create a collision-free proposal ID using SHA-256 + _seq."""
        raw = f"{topic}-{now}-{self._seq}"
        return "acn-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Proposal lifecycle
    # ------------------------------------------------------------------

    def create_proposal(
        self,
        topic: str,
        options: List[str],
        required_votes: int = 2,
    ) -> str:
        """Create a new consensus proposal.

        Returns the proposal_id (``acn-...``) on success, or ``""`` on
        validation failure.
        """
        if not topic or not options or len(options) < 2:
            logger.warning("agent_consensus_engine.create_proposal.invalid",
                           topic=topic, options_len=len(options) if options else 0)
            return ""
        if required_votes < 1:
            return ""
        if len(self._proposals) >= self._max_proposals:
            logger.warning("agent_consensus_engine.create_proposal.limit_reached")
            return ""

        now = time.time()
        self._seq += 1
        pid = self._generate_id(topic, now)

        self._proposals[pid] = _ProposalRecord(
            proposal_id=pid,
            topic=topic,
            options=list(options),
            required_votes=required_votes,
            votes={},
            status="open",
            result=None,
            created_at=now,
            seq=self._seq,
        )

        self._stats["total_created"] += 1
        logger.info("agent_consensus_engine.proposal_created",
                    proposal_id=pid, topic=topic, required_votes=required_votes)
        self._fire("proposal_created", {"proposal_id": pid, "topic": topic})
        return pid

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Return a dict representation of the proposal, or ``None``."""
        p = self._proposals.get(proposal_id)
        if p is None:
            return None
        return {
            "proposal_id": p.proposal_id,
            "topic": p.topic,
            "options": list(p.options),
            "required_votes": p.required_votes,
            "votes": dict(p.votes),
            "status": p.status,
            "result": p.result,
            "created_at": p.created_at,
        }

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def vote(self, proposal_id: str, agent_id: str, option: str) -> bool:
        """Cast a vote on a proposal.

        Returns ``True`` if the vote was accepted, ``False`` if the
        proposal was not found, is closed, the option is invalid, or
        the agent has already voted.
        """
        p = self._proposals.get(proposal_id)
        if p is None:
            return False
        if p.status != "open":
            return False
        if option not in p.options:
            return False
        if agent_id in p.votes:
            return False

        p.votes[agent_id] = option
        self._stats["total_votes"] += 1
        logger.info("agent_consensus_engine.vote",
                    proposal_id=proposal_id, agent_id=agent_id, option=option)
        self._fire("vote_cast", {
            "proposal_id": proposal_id,
            "agent_id": agent_id,
            "option": option,
        })

        # Check if any option has reached the threshold
        tally: Dict[str, int] = {}
        for chosen in p.votes.values():
            tally[chosen] = tally.get(chosen, 0) + 1

        for opt, count in tally.items():
            if count >= p.required_votes:
                p.status = "decided"
                p.result = opt
                self._stats["total_decided"] += 1
                logger.info("agent_consensus_engine.decided",
                            proposal_id=proposal_id, result=opt)
                self._fire("proposal_decided", {
                    "proposal_id": proposal_id,
                    "result": opt,
                })
                break

        return True

    # ------------------------------------------------------------------
    # Result inspection
    # ------------------------------------------------------------------

    def get_result(self, proposal_id: str) -> Dict[str, Any]:
        """Return the current result/tally for a proposal.

        Always returns a dict with keys ``decided``, ``result``,
        ``vote_count``, and ``tally``.
        """
        p = self._proposals.get(proposal_id)
        if p is None:
            return {"decided": False, "result": None, "vote_count": 0, "tally": {}}

        tally: Dict[str, int] = {}
        for chosen in p.votes.values():
            tally[chosen] = tally.get(chosen, 0) + 1

        return {
            "decided": p.status == "decided",
            "result": p.result,
            "vote_count": len(p.votes),
            "tally": tally,
        }

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel_proposal(self, proposal_id: str) -> bool:
        """Cancel an open proposal.

        Returns ``True`` if cancelled, ``False`` if not found or
        already decided/cancelled.
        """
        p = self._proposals.get(proposal_id)
        if p is None:
            return False
        if p.status != "open":
            return False

        p.status = "cancelled"
        self._stats["total_cancelled"] += 1
        logger.info("agent_consensus_engine.cancelled", proposal_id=proposal_id)
        self._fire("proposal_cancelled", {"proposal_id": proposal_id})
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent_votes(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return list of proposal dicts where *agent_id* has voted."""
        results: List[Dict[str, Any]] = []
        for p in self._proposals.values():
            if agent_id in p.votes:
                results.append(self.get_proposal(p.proposal_id))  # type: ignore[arg-type]
        return results

    def list_open_proposals(self) -> List[Dict[str, Any]]:
        """Return all proposals with status ``"open"``."""
        return [
            self.get_proposal(pid)  # type: ignore[misc]
            for pid, p in self._proposals.items()
            if p.status == "open"
        ]

    def get_proposal_count(self) -> int:
        """Return the total number of stored proposals."""
        return len(self._proposals)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named callback for mutation events."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback.  Returns ``True`` if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("agent_consensus_engine.callback_error",
                                 action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics."""
        return {
            **self._stats,
            "current_proposals": len(self._proposals),
            "open_proposals": sum(
                1 for p in self._proposals.values() if p.status == "open"
            ),
        }

    def reset(self) -> None:
        """Clear all proposals, callbacks, and reset counters."""
        self._proposals.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("agent_consensus_engine.reset")
