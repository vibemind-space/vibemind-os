"""Test agent negotiation protocol -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_negotiation_protocol import AgentNegotiationProtocol


def test_create_negotiation():
    np = AgentNegotiationProtocol()
    nid = np.create_negotiation("task_assign", "agent-1", ["agent-2", "agent-3"], resource="gpu_cluster")
    assert nid.startswith("anp-")
    n = np.get_negotiation(nid)
    assert n is not None
    assert n["topic"] == "task_assign"
    assert n["status"] == "open"
    print("OK: create negotiation")


def test_submit_proposal():
    np = AgentNegotiationProtocol()
    nid = np.create_negotiation("task", "a1", ["a2"])
    pid = np.submit_proposal(nid, "a2", offer={"price": 100, "time": "2h"}, priority=5.0)
    assert len(pid) > 0
    proposals = np.get_proposals(nid)
    assert len(proposals) == 1
    assert proposals[0]["offer"]["price"] == 100
    print("OK: submit proposal")


def test_accept_proposal():
    np = AgentNegotiationProtocol()
    nid = np.create_negotiation("task", "a1", ["a2"])
    pid = np.submit_proposal(nid, "a2", offer={"bid": 50})
    assert np.accept_proposal(nid, pid) is True
    n = np.get_negotiation(nid)
    assert n["status"] == "accepted"
    print("OK: accept proposal")


def test_reject_proposal():
    np = AgentNegotiationProtocol()
    nid = np.create_negotiation("task", "a1", ["a2"])
    pid = np.submit_proposal(nid, "a2", offer={"bid": 50})
    assert np.reject_proposal(nid, pid, reason="too expensive") is True
    proposals = np.get_proposals(nid)
    rejected = [p for p in proposals if p.get("status") == "rejected"]
    assert len(rejected) == 1
    print("OK: reject proposal")


def test_counter_offer():
    np = AgentNegotiationProtocol()
    nid = np.create_negotiation("task", "a1", ["a2"])
    pid = np.submit_proposal(nid, "a2", offer={"bid": 100})
    cpid = np.counter_offer(nid, pid, "a1", new_offer={"bid": 75}, priority=3.0)
    assert len(cpid) > 0
    proposals = np.get_proposals(nid)
    assert len(proposals) >= 2
    print("OK: counter offer")


def test_resolve_highest_priority():
    np = AgentNegotiationProtocol()
    nid = np.create_negotiation("task", "a1", ["a2", "a3"])
    np.submit_proposal(nid, "a2", offer={"bid": 50}, priority=3.0)
    np.submit_proposal(nid, "a3", offer={"bid": 30}, priority=8.0)
    result = np.resolve(nid, strategy="highest_priority")
    assert result["winning_agent"] == "a3"  # higher priority
    n = np.get_negotiation(nid)
    assert n["status"] == "resolved"
    print("OK: resolve highest priority")


def test_list_negotiations():
    np = AgentNegotiationProtocol()
    nid1 = np.create_negotiation("t1", "a1", ["a2"], tags=["urgent"])
    nid2 = np.create_negotiation("t2", "a1", ["a3"])
    np.submit_proposal(nid1, "a2", offer={})
    np.resolve(nid1)
    assert len(np.list_negotiations()) == 2
    assert len(np.list_negotiations(status="open")) == 1
    assert len(np.list_negotiations(tag="urgent")) == 1
    print("OK: list negotiations")


def test_remove_negotiation():
    np = AgentNegotiationProtocol()
    nid = np.create_negotiation("t1", "a1", ["a2"])
    assert np.remove_negotiation(nid) is True
    assert np.remove_negotiation(nid) is False
    print("OK: remove negotiation")


def test_history():
    np = AgentNegotiationProtocol()
    np.create_negotiation("t1", "a1", ["a2"])
    hist = np.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    np = AgentNegotiationProtocol()
    fired = []
    np.on_change("mon", lambda a, d: fired.append(a))
    np.create_negotiation("t1", "a1", ["a2"])
    assert len(fired) >= 1
    assert np.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    np = AgentNegotiationProtocol()
    np.create_negotiation("t1", "a1", ["a2"])
    stats = np.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    np = AgentNegotiationProtocol()
    np.create_negotiation("t1", "a1", ["a2"])
    np.reset()
    assert np.list_negotiations() == []
    print("OK: reset")


def main():
    print("=== Agent Negotiation Protocol Tests ===\n")
    test_create_negotiation()
    test_submit_proposal()
    test_accept_proposal()
    test_reject_proposal()
    test_counter_offer()
    test_resolve_highest_priority()
    test_list_negotiations()
    test_remove_negotiation()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
