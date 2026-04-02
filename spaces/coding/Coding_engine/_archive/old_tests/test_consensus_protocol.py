"""Test consensus protocol."""
import sys
import time
sys.path.insert(0, ".")

from src.services.consensus_protocol import ConsensusProtocol


def test_register_voter():
    """Register and unregister voters."""
    cp = ConsensusProtocol()
    assert cp.register_voter("Alice", weight=2.0) is True
    assert cp.register_voter("Alice") is False  # Duplicate

    voters = cp.list_voters()
    assert len(voters) == 1
    assert voters[0]["name"] == "Alice"
    assert voters[0]["weight"] == 2.0

    assert cp.unregister_voter("Alice") is True
    assert cp.unregister_voter("Alice") is False
    print("OK: register voter")


def test_create_proposal():
    """Create a proposal."""
    cp = ConsensusProtocol()
    cp.register_voter("Alice")
    cp.register_voter("Bob")

    pid = cp.create_proposal("Deploy v2", proposer="Alice",
                              description="Deploy to prod",
                              tags={"deploy"}, metadata={"env": "prod"})
    assert pid.startswith("prop-")

    prop = cp.get_proposal(pid)
    assert prop is not None
    assert prop["title"] == "Deploy v2"
    assert prop["proposer"] == "Alice"
    assert prop["status"] == "open"
    assert prop["eligible_count"] == 2
    print("OK: create proposal")


def test_vote_approve():
    """Vote to approve a proposal."""
    cp = ConsensusProtocol(default_quorum=2, default_threshold=0.5)
    cp.register_voter("Alice")
    cp.register_voter("Bob")

    pid = cp.create_proposal("Test", proposer="Alice")

    assert cp.vote(pid, "Alice", "approve") is True
    assert cp.vote(pid, "Bob", "approve") is True

    prop = cp.get_proposal(pid)
    assert prop["status"] == "approved"
    print("OK: vote approve")


def test_vote_reject():
    """Vote to reject a proposal."""
    cp = ConsensusProtocol(default_quorum=2, default_threshold=0.5)
    cp.register_voter("Alice")
    cp.register_voter("Bob")

    pid = cp.create_proposal("Bad idea", proposer="Alice")
    cp.vote(pid, "Alice", "reject")
    cp.vote(pid, "Bob", "reject")

    prop = cp.get_proposal(pid)
    assert prop["status"] == "rejected"
    print("OK: vote reject")


def test_vote_invalid():
    """Invalid vote scenarios."""
    cp = ConsensusProtocol()
    cp.register_voter("Alice")

    pid = cp.create_proposal("Test", proposer="Alice")

    # Invalid choice
    assert cp.vote(pid, "Alice", "maybe") is False

    # Not eligible
    assert cp.vote(pid, "Charlie", "approve") is False

    # Vote then try again
    cp.vote(pid, "Alice", "approve")
    assert cp.vote(pid, "Alice", "reject") is False  # Already voted

    # Nonexistent proposal
    assert cp.vote("fake", "Alice", "approve") is False
    print("OK: vote invalid")


def test_quorum_not_met():
    """Proposal stays open when quorum not met."""
    cp = ConsensusProtocol(default_quorum=3)
    cp.register_voter("Alice")
    cp.register_voter("Bob")
    cp.register_voter("Charlie")

    pid = cp.create_proposal("Test", proposer="Alice")
    cp.vote(pid, "Alice", "approve")
    cp.vote(pid, "Bob", "approve")

    prop = cp.get_proposal(pid)
    assert prop["status"] == "open"  # Need 3 votes

    cp.vote(pid, "Charlie", "approve")
    prop = cp.get_proposal(pid)
    assert prop["status"] == "approved"
    print("OK: quorum not met")


def test_threshold():
    """Custom approval threshold."""
    cp = ConsensusProtocol(default_quorum=2)
    cp.register_voter("Alice")
    cp.register_voter("Bob")
    cp.register_voter("Charlie")

    # 100% threshold
    pid = cp.create_proposal("Unanimous", proposer="Alice", threshold=1.0)
    cp.vote(pid, "Alice", "approve")
    cp.vote(pid, "Bob", "reject")
    prop = cp.get_proposal(pid)
    assert prop["status"] == "rejected"  # Not unanimous
    print("OK: threshold")


def test_weighted_voting():
    """Weighted votes affect outcome."""
    cp = ConsensusProtocol(default_quorum=2, default_threshold=0.5)
    cp.register_voter("Boss", weight=10.0)
    cp.register_voter("Worker", weight=1.0)

    pid = cp.create_proposal("Boss decision", proposer="Boss")
    cp.vote(pid, "Boss", "approve")
    cp.vote(pid, "Worker", "reject")

    # Boss has weight 10, Worker has 1
    # Approve ratio: 10/11 > 0.5
    prop = cp.get_proposal(pid)
    assert prop["status"] == "approved"
    print("OK: weighted voting")


def test_get_tally():
    """Get vote tally."""
    cp = ConsensusProtocol(default_quorum=5)
    cp.register_voter("A")
    cp.register_voter("B")
    cp.register_voter("C")
    cp.register_voter("D")
    cp.register_voter("E")

    pid = cp.create_proposal("Test", proposer="A")
    cp.vote(pid, "A", "approve")
    cp.vote(pid, "B", "reject")
    cp.vote(pid, "C", "abstain")

    tally = cp.get_tally(pid)
    assert tally is not None
    assert tally["total_votes"] == 3
    assert tally["quorum_met"] is False
    assert tally["approve_weight"] == 1.0
    assert tally["reject_weight"] == 1.0
    assert len(tally["remaining_voters"]) == 2

    assert cp.get_tally("fake") is None
    print("OK: get tally")


def test_get_votes():
    """Get votes for a proposal."""
    cp = ConsensusProtocol(default_quorum=3)
    cp.register_voter("A")
    cp.register_voter("B")

    pid = cp.create_proposal("Test", proposer="A")
    cp.vote(pid, "A", "approve", reason="LGTM")
    cp.vote(pid, "B", "reject", reason="Not ready")

    votes = cp.get_votes(pid)
    assert len(votes) == 2
    assert votes[0]["reason"] == "LGTM"

    assert cp.get_votes("fake") == []
    print("OK: get votes")


def test_deadline_expiry():
    """Proposal expires after deadline."""
    cp = ConsensusProtocol()
    cp.register_voter("Alice")

    pid = cp.create_proposal("Urgent", proposer="Alice",
                              deadline_seconds=0.01)
    time.sleep(0.02)

    prop = cp.get_proposal(pid)
    assert prop["status"] == "expired"
    print("OK: deadline expiry")


def test_cancel_proposal():
    """Cancel an open proposal."""
    cp = ConsensusProtocol()
    cp.register_voter("Alice")

    pid = cp.create_proposal("Test", proposer="Alice")
    assert cp.cancel_proposal(pid) is True

    prop = cp.get_proposal(pid)
    assert prop["status"] == "cancelled"
    assert cp.cancel_proposal(pid) is False  # Already cancelled
    print("OK: cancel proposal")


def test_list_proposals():
    """List proposals with filters."""
    cp = ConsensusProtocol(default_quorum=1)
    cp.register_voter("Alice")

    p1 = cp.create_proposal("Open", proposer="Alice")
    p2 = cp.create_proposal("Done", proposer="Alice")
    cp.vote(p2, "Alice", "approve")
    p3 = cp.create_proposal("By Bob", proposer="Bob")

    all_props = cp.list_proposals()
    assert len(all_props) == 3

    open_props = cp.list_proposals(status="open")
    assert len(open_props) == 2

    by_alice = cp.list_proposals(proposer="Alice")
    assert len(by_alice) == 2

    limited = cp.list_proposals(limit=1)
    assert len(limited) == 1
    print("OK: list proposals")


def test_callbacks():
    """Callbacks on approval/rejection."""
    results = []
    cp = ConsensusProtocol(default_quorum=1)
    cp.register_voter("Alice")

    pid = cp.create_proposal("Test", proposer="Alice",
                              on_approved=lambda p: results.append("approved"))
    cp.vote(pid, "Alice", "approve")
    assert results == ["approved"]

    results.clear()
    pid2 = cp.create_proposal("Bad", proposer="Alice",
                               on_rejected=lambda p: results.append("rejected"))
    cp.vote(pid2, "Alice", "reject")
    assert results == ["rejected"]
    print("OK: callbacks")


def test_voter_history():
    """Get voting history for a voter."""
    cp = ConsensusProtocol(default_quorum=1)
    cp.register_voter("Alice")

    p1 = cp.create_proposal("A", proposer="Alice")
    cp.vote(p1, "Alice", "approve")
    p2 = cp.create_proposal("B", proposer="Alice")
    cp.vote(p2, "Alice", "reject")

    history = cp.get_voter_history("Alice")
    assert len(history) == 2
    choices = {h["choice"] for h in history}
    assert choices == {"approve", "reject"}
    print("OK: voter history")


def test_eligible_voters_subset():
    """Custom eligible voters."""
    cp = ConsensusProtocol(default_quorum=1)
    cp.register_voter("Alice")
    cp.register_voter("Bob")

    pid = cp.create_proposal("Private", proposer="Alice",
                              eligible_voters={"Alice"})

    assert cp.vote(pid, "Bob", "approve") is False  # Not eligible
    assert cp.vote(pid, "Alice", "approve") is True
    print("OK: eligible voters subset")


def test_abstain_vote():
    """Abstain votes count for quorum but not approval ratio."""
    cp = ConsensusProtocol(default_quorum=2, default_threshold=0.5)
    cp.register_voter("Alice")
    cp.register_voter("Bob")

    pid = cp.create_proposal("Test", proposer="Alice")
    cp.vote(pid, "Alice", "approve")
    cp.vote(pid, "Bob", "abstain")

    # Quorum met (2 votes), approve ratio: 1/1 decisive = 100%
    prop = cp.get_proposal(pid)
    assert prop["status"] == "approved"
    print("OK: abstain vote")


def test_prune_proposals():
    """Prune old proposals."""
    cp = ConsensusProtocol(max_proposals=3, default_quorum=1)
    cp.register_voter("Alice")

    for i in range(6):
        pid = cp.create_proposal(f"P-{i}", proposer="Alice")
        cp.vote(pid, "Alice", "approve")

    assert len(cp._proposals) <= 3
    print("OK: prune proposals")


def test_stats():
    """Stats are accurate."""
    cp = ConsensusProtocol(default_quorum=1)
    cp.register_voter("Alice")

    p1 = cp.create_proposal("A", proposer="Alice")
    cp.vote(p1, "Alice", "approve")

    p2 = cp.create_proposal("B", proposer="Alice")
    cp.vote(p2, "Alice", "reject")

    stats = cp.get_stats()
    assert stats["total_proposals"] == 2
    assert stats["total_votes"] == 2
    assert stats["total_approved"] == 1
    assert stats["total_rejected"] == 1
    assert stats["total_voters"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cp = ConsensusProtocol()
    cp.register_voter("Alice")
    cp.create_proposal("Test", proposer="Alice")

    cp.reset()
    assert cp.list_voters() == []
    assert cp.list_proposals() == []
    stats = cp.get_stats()
    assert stats["total_proposals"] == 0
    assert stats["total_voters"] == 0
    print("OK: reset")


def main():
    print("=== Consensus Protocol Tests ===\n")
    test_register_voter()
    test_create_proposal()
    test_vote_approve()
    test_vote_reject()
    test_vote_invalid()
    test_quorum_not_met()
    test_threshold()
    test_weighted_voting()
    test_get_tally()
    test_get_votes()
    test_deadline_expiry()
    test_cancel_proposal()
    test_list_proposals()
    test_callbacks()
    test_voter_history()
    test_eligible_voters_subset()
    test_abstain_vote()
    test_prune_proposals()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
