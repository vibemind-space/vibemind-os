"""Test agent consensus voting."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_consensus_voting import AgentConsensusVoting


def test_register_voter():
    """Register and unregister voters."""
    cv = AgentConsensusVoting()
    assert cv.register_voter("Alice", weight=2.0, groups={"senior"}) is True
    assert cv.register_voter("Alice") is False  # Duplicate

    v = cv.get_voter("Alice")
    assert v is not None
    assert v["weight"] == 2.0
    assert "senior" in v["groups"]

    assert cv.unregister_voter("Alice") is True
    assert cv.unregister_voter("Alice") is False
    print("OK: register voter")


def test_invalid_voter():
    """Invalid voter params rejected."""
    cv = AgentConsensusVoting()
    assert cv.register_voter("bad", weight=0) is False
    assert cv.register_voter("bad", weight=-1) is False
    print("OK: invalid voter")


def test_voter_weight():
    """Set voter weight."""
    cv = AgentConsensusVoting()
    cv.register_voter("Alice")
    assert cv.set_voter_weight("Alice", 3.0) is True
    assert cv.get_voter("Alice")["weight"] == 3.0
    assert cv.set_voter_weight("Alice", 0) is False
    assert cv.set_voter_weight("fake", 1.0) is False
    print("OK: voter weight")


def test_voter_groups():
    """Add and remove voter groups."""
    cv = AgentConsensusVoting()
    cv.register_voter("Alice")
    assert cv.add_voter_group("Alice", "senior") is True
    assert cv.add_voter_group("Alice", "senior") is False
    assert cv.remove_voter_group("Alice", "senior") is True
    assert cv.remove_voter_group("Alice", "senior") is False
    print("OK: voter groups")


def test_list_voters():
    """List voters with filter."""
    cv = AgentConsensusVoting()
    cv.register_voter("Alice", groups={"dev"})
    cv.register_voter("Bob", groups={"ops"})

    all_v = cv.list_voters()
    assert len(all_v) == 2

    devs = cv.list_voters(group="dev")
    assert len(devs) == 1
    assert devs[0]["name"] == "Alice"
    print("OK: list voters")


def test_create_proposal():
    """Create proposal."""
    cv = AgentConsensusVoting()
    cv.register_voter("Alice")
    pid = cv.create_proposal("Feature X", "Add feature X", "Alice")
    assert pid.startswith("prop-")

    p = cv.get_proposal(pid)
    assert p is not None
    assert p["title"] == "Feature X"
    assert p["status"] == "open"
    assert p["options"] == ["yes", "no"]
    print("OK: create proposal")


def test_invalid_proposal():
    """Invalid proposals rejected."""
    cv = AgentConsensusVoting()
    cv.register_voter("Alice")
    assert cv.create_proposal("X", "x", "fake") == ""  # Bad proposer
    assert cv.create_proposal("X", "x", "Alice", voting_method="invalid") == ""
    assert cv.create_proposal("X", "x", "Alice", options=["only_one"]) == ""
    assert cv.create_proposal("X", "x", "Alice", min_votes=0) == ""
    assert cv.create_proposal("X", "x", "Alice", required_voters={"nonexistent"}) == ""
    print("OK: invalid proposal")


def test_cast_vote():
    """Cast a vote."""
    cv = AgentConsensusVoting()
    cv.register_voter("Alice")
    cv.register_voter("Bob")
    pid = cv.create_proposal("X", "x", "Alice")

    assert cv.cast_vote(pid, "Bob", "yes") is True
    assert cv.cast_vote(pid, "Bob", "no") is False  # Already voted
    assert cv.cast_vote(pid, "fake", "yes") is False
    assert cv.cast_vote(pid, "Alice", "invalid") is False

    assert cv.has_voted(pid, "Bob") is True
    assert cv.has_voted(pid, "Alice") is False
    print("OK: cast vote")


def test_change_vote():
    """Change an existing vote."""
    cv = AgentConsensusVoting()
    cv.register_voter("Alice")
    cv.register_voter("Bob")
    pid = cv.create_proposal("X", "x", "Alice")

    cv.cast_vote(pid, "Bob", "yes")
    assert cv.change_vote(pid, "Bob", "no") is True
    votes = cv.get_votes(pid)
    assert votes["Bob"] == "no"

    assert cv.change_vote(pid, "Alice", "yes") is False  # Hasn't voted
    print("OK: change vote")


def test_majority_pass():
    """Majority vote passes."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")
    cv.register_voter("C")
    pid = cv.create_proposal("X", "x", "A", voting_method="majority")

    cv.cast_vote(pid, "A", "yes")
    cv.cast_vote(pid, "B", "yes")
    cv.cast_vote(pid, "C", "no")

    result = cv.close_and_tally(pid)
    assert result is not None
    assert result["winner"] == "yes"
    assert cv.get_proposal(pid)["status"] == "passed"
    print("OK: majority pass")


def test_majority_fail():
    """Majority vote fails (tie)."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")
    pid = cv.create_proposal("X", "x", "A", voting_method="majority")

    cv.cast_vote(pid, "A", "yes")
    cv.cast_vote(pid, "B", "no")

    result = cv.close_and_tally(pid)
    assert result["winner"] == ""
    assert cv.get_proposal(pid)["status"] == "failed"
    print("OK: majority fail")


def test_supermajority():
    """Supermajority requires >2/3."""
    cv = AgentConsensusVoting()
    for name in ["A", "B", "C"]:
        cv.register_voter(name)
    pid = cv.create_proposal("X", "x", "A", voting_method="supermajority")

    cv.cast_vote(pid, "A", "yes")
    cv.cast_vote(pid, "B", "yes")
    cv.cast_vote(pid, "C", "no")

    result = cv.close_and_tally(pid)
    # 2/3 = 66.7%, need >66.7%, so 2/3 doesn't pass
    assert result["winner"] == ""
    print("OK: supermajority")


def test_unanimous():
    """Unanimous requires all same vote."""
    cv = AgentConsensusVoting()
    for name in ["A", "B", "C"]:
        cv.register_voter(name)
    pid = cv.create_proposal("X", "x", "A", voting_method="unanimous")

    cv.cast_vote(pid, "A", "yes")
    cv.cast_vote(pid, "B", "yes")
    cv.cast_vote(pid, "C", "yes")

    result = cv.close_and_tally(pid)
    assert result["winner"] == "yes"
    print("OK: unanimous")


def test_ranked_choice():
    """Ranked choice voting."""
    cv = AgentConsensusVoting()
    for name in ["A", "B", "C"]:
        cv.register_voter(name)
    options = ["red", "blue", "green"]
    pid = cv.create_proposal("Color", "pick color", "A",
                             options=options, voting_method="ranked")

    cv.cast_vote(pid, "A", ["red", "blue", "green"])
    cv.cast_vote(pid, "B", ["blue", "red", "green"])
    cv.cast_vote(pid, "C", ["blue", "green", "red"])

    result = cv.close_and_tally(pid)
    assert result["winner"] == "blue"  # blue gets 2 first-choice
    assert len(result["rounds"]) >= 1
    print("OK: ranked choice")


def test_weighted_voting():
    """Weighted voting."""
    cv = AgentConsensusVoting()
    cv.register_voter("A", weight=5.0)
    cv.register_voter("B", weight=1.0)
    cv.register_voter("C", weight=1.0)
    pid = cv.create_proposal("X", "x", "A", voting_method="weighted")

    cv.cast_vote(pid, "A", "yes")
    cv.cast_vote(pid, "B", "no")
    cv.cast_vote(pid, "C", "no")

    result = cv.close_and_tally(pid)
    # A's weight 5 > B+C weight 2, so yes wins
    assert result["winner"] == "yes"
    assert result["total_weight"] == 7.0
    print("OK: weighted voting")


def test_min_votes():
    """Insufficient votes fails."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")
    pid = cv.create_proposal("X", "x", "A", min_votes=2)

    cv.cast_vote(pid, "A", "yes")
    result = cv.close_and_tally(pid)
    assert cv.get_proposal(pid)["status"] == "failed"
    assert cv.get_proposal(pid)["result"] == "insufficient_votes"
    print("OK: min votes")


def test_required_voters():
    """Required voters must vote."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")
    pid = cv.create_proposal("X", "x", "A", required_voters={"A", "B"})

    cv.cast_vote(pid, "A", "yes")
    # B hasn't voted
    result = cv.close_and_tally(pid)
    assert cv.get_proposal(pid)["status"] == "failed"
    assert cv.get_proposal(pid)["result"] == "missing_required_voters"
    print("OK: required voters")


def test_expiry():
    """Proposals expire."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    pid = cv.create_proposal("X", "x", "A", deadline_seconds=0.02)

    time.sleep(0.03)
    p = cv.get_proposal(pid)
    assert p["status"] == "expired"
    print("OK: expiry")


def test_cancel_proposal():
    """Cancel proposal."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    pid = cv.create_proposal("X", "x", "A")

    assert cv.cancel_proposal(pid) is True
    assert cv.get_proposal(pid)["status"] == "cancelled"
    assert cv.cancel_proposal(pid) is False
    print("OK: cancel proposal")


def test_tally_without_close():
    """Tally without closing."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")
    pid = cv.create_proposal("X", "x", "A")

    cv.cast_vote(pid, "A", "yes")
    tally = cv.tally(pid)
    assert tally is not None
    assert tally["counts"]["yes"] == 1
    assert cv.get_proposal(pid)["status"] == "open"  # Still open
    print("OK: tally without close")


def test_list_proposals():
    """List proposals with filters."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")

    cv.create_proposal("P1", "x", "A")
    p2 = cv.create_proposal("P2", "x", "B")
    cv.cancel_proposal(p2)

    all_p = cv.list_proposals()
    assert len(all_p) == 2

    open_p = cv.list_proposals(status="open")
    assert len(open_p) == 1

    by_b = cv.list_proposals(proposer="B")
    assert len(by_b) == 1
    print("OK: list proposals")


def test_callbacks():
    """Event callbacks fire."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")

    fired = []
    assert cv.on_event("mon", lambda act, pid, data: fired.append(act)) is True
    assert cv.on_event("mon", lambda a, p, d: None) is False

    pid = cv.create_proposal("X", "x", "A")
    cv.cast_vote(pid, "A", "yes")
    cv.cast_vote(pid, "B", "yes")
    cv.close_and_tally(pid)

    assert "vote" in fired
    assert "passed" in fired

    assert cv.remove_callback("mon") is True
    assert cv.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.register_voter("B")

    pid = cv.create_proposal("X", "x", "A")
    cv.cast_vote(pid, "A", "yes")
    cv.cast_vote(pid, "B", "yes")
    cv.close_and_tally(pid)

    stats = cv.get_stats()
    assert stats["total_proposals"] == 1
    assert stats["total_votes_cast"] == 2
    assert stats["total_passed"] == 1
    assert stats["total_voters"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cv = AgentConsensusVoting()
    cv.register_voter("A")
    cv.create_proposal("X", "x", "A")

    cv.reset()
    assert cv.list_voters() == []
    assert cv.list_proposals() == []
    stats = cv.get_stats()
    assert stats["total_proposals"] == 0
    assert stats["total_voters"] == 0
    print("OK: reset")


def main():
    print("=== Agent Consensus Voting Tests ===\n")
    test_register_voter()
    test_invalid_voter()
    test_voter_weight()
    test_voter_groups()
    test_list_voters()
    test_create_proposal()
    test_invalid_proposal()
    test_cast_vote()
    test_change_vote()
    test_majority_pass()
    test_majority_fail()
    test_supermajority()
    test_unanimous()
    test_ranked_choice()
    test_weighted_voting()
    test_min_votes()
    test_required_voters()
    test_expiry()
    test_cancel_proposal()
    test_tally_without_close()
    test_list_proposals()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 24 TESTS PASSED ===")


if __name__ == "__main__":
    main()
