"""Test agent consensus engine -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_consensus_engine import AgentConsensusEngine


def test_create_proposal():
    ce = AgentConsensusEngine()
    pid = ce.create_proposal("deploy strategy", ["blue-green", "canary", "rolling"])
    assert len(pid) > 0
    assert pid.startswith("acn-")
    print("OK: create proposal")


def test_get_proposal():
    ce = AgentConsensusEngine()
    pid = ce.create_proposal("deploy strategy", ["blue-green", "canary"], required_votes=2)
    prop = ce.get_proposal(pid)
    assert prop is not None
    assert prop["topic"] == "deploy strategy"
    assert prop["status"] == "open"
    assert prop["required_votes"] == 2
    assert ce.get_proposal("nonexistent") is None
    print("OK: get proposal")


def test_vote():
    ce = AgentConsensusEngine()
    pid = ce.create_proposal("strategy", ["A", "B"], required_votes=3)
    assert ce.vote(pid, "agent-1", "A") is True
    assert ce.vote(pid, "agent-1", "B") is False  # Already voted
    assert ce.vote(pid, "agent-2", "X") is False  # Invalid option
    assert ce.vote(pid, "agent-2", "A") is True
    print("OK: vote")


def test_get_result_undecided():
    ce = AgentConsensusEngine()
    pid = ce.create_proposal("strategy", ["A", "B"], required_votes=3)
    ce.vote(pid, "agent-1", "A")
    result = ce.get_result(pid)
    assert result["decided"] is False
    assert result["vote_count"] == 1
    print("OK: get result undecided")


def test_get_result_decided():
    ce = AgentConsensusEngine()
    pid = ce.create_proposal("strategy", ["A", "B"], required_votes=2)
    ce.vote(pid, "agent-1", "A")
    ce.vote(pid, "agent-2", "A")
    result = ce.get_result(pid)
    assert result["decided"] is True
    assert result["result"] == "A"
    assert result["tally"]["A"] == 2
    print("OK: get result decided")


def test_cancel_proposal():
    ce = AgentConsensusEngine()
    pid = ce.create_proposal("strategy", ["A", "B"])
    assert ce.cancel_proposal(pid) is True
    prop = ce.get_proposal(pid)
    assert prop["status"] == "cancelled"
    assert ce.cancel_proposal(pid) is False  # Already cancelled
    print("OK: cancel proposal")


def test_get_agent_votes():
    ce = AgentConsensusEngine()
    pid1 = ce.create_proposal("s1", ["A", "B"])
    pid2 = ce.create_proposal("s2", ["X", "Y"])
    ce.vote(pid1, "agent-1", "A")
    ce.vote(pid2, "agent-1", "X")
    votes = ce.get_agent_votes("agent-1")
    assert len(votes) == 2
    print("OK: get agent votes")


def test_list_open_proposals():
    ce = AgentConsensusEngine()
    pid1 = ce.create_proposal("s1", ["A", "B"], required_votes=1)
    ce.create_proposal("s2", ["X", "Y"])
    ce.vote(pid1, "agent-1", "A")  # This decides pid1
    open_props = ce.list_open_proposals()
    assert len(open_props) == 1
    print("OK: list open proposals")


def test_callbacks():
    ce = AgentConsensusEngine()
    fired = []
    ce.on_change("mon", lambda a, d: fired.append(a))
    ce.create_proposal("s1", ["A", "B"])
    assert len(fired) >= 1
    assert ce.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ce = AgentConsensusEngine()
    ce.create_proposal("s1", ["A", "B"])
    stats = ce.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ce = AgentConsensusEngine()
    ce.create_proposal("s1", ["A", "B"])
    ce.reset()
    assert ce.get_proposal_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Consensus Engine Tests ===\n")
    test_create_proposal()
    test_get_proposal()
    test_vote()
    test_get_result_undecided()
    test_get_result_decided()
    test_cancel_proposal()
    test_get_agent_votes()
    test_list_open_proposals()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
