"""Test agent negotiation engine."""
import sys
sys.path.insert(0, ".")
from src.services.agent_negotiation_engine import AgentNegotiationEngine

def test_create():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("resource_split", ["a1", "a2", "a3"], tags=["critical"])
    assert nid.startswith("neg-")
    n = ne.get_negotiation(nid)
    assert n["topic"] == "resource_split"
    assert n["status"] == "open"
    assert len(n["participants"]) == 3
    print("OK: create")

def test_invalid_create():
    ne = AgentNegotiationEngine()
    assert ne.create_negotiation("", ["a", "b"]) == ""
    assert ne.create_negotiation("t", ["a"]) == ""  # need 2+ participants
    print("OK: invalid create")

def test_max_negotiations():
    ne = AgentNegotiationEngine(max_negotiations=2)
    ne.create_negotiation("t1", ["a", "b"])
    ne.create_negotiation("t2", ["a", "b"])
    assert ne.create_negotiation("t3", ["a", "b"]) == ""
    print("OK: max negotiations")

def test_submit_proposal():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("split", ["a1", "a2"])
    assert ne.submit_proposal(nid, "a1", 60, "I need more") is True
    n = ne.get_negotiation(nid)
    assert len(n["proposals"]) == 1
    assert n["proposals"][0]["value"] == 60
    print("OK: submit proposal")

def test_submit_non_participant():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("split", ["a1", "a2"])
    assert ne.submit_proposal(nid, "outsider", 50) is False
    print("OK: submit non participant")

def test_vote():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("split", ["a1", "a2", "a3"])
    ne.submit_proposal(nid, "a1", 60)
    assert ne.vote(nid, "a2", 0) is True
    n = ne.get_negotiation(nid)
    assert "a2" in n["proposals"][0]["votes"]
    print("OK: vote")

def test_vote_duplicate():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("split", ["a1", "a2"])
    ne.submit_proposal(nid, "a1", 60)
    ne.vote(nid, "a2", 0)
    assert ne.vote(nid, "a2", 0) is False  # already voted
    print("OK: vote duplicate")

def test_majority_resolves():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("split", ["a1", "a2", "a3"])
    ne.submit_proposal(nid, "a1", 60)
    ne.vote(nid, "a2", 0)  # 1 vote
    ne.vote(nid, "a3", 0)  # 2 votes = majority of 3
    n = ne.get_negotiation(nid)
    assert n["status"] == "resolved"
    assert n["winner"] == "a1"
    print("OK: majority resolves")

def test_cancel():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("split", ["a1", "a2"])
    assert ne.cancel_negotiation(nid) is True
    assert ne.get_negotiation(nid)["status"] == "cancelled"
    assert ne.cancel_negotiation(nid) is False
    print("OK: cancel")

def test_submit_to_closed():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("split", ["a1", "a2"])
    ne.cancel_negotiation(nid)
    assert ne.submit_proposal(nid, "a1", 50) is False
    print("OK: submit to closed")

def test_list():
    ne = AgentNegotiationEngine()
    nid1 = ne.create_negotiation("t1", ["a", "b"], tags=["urgent"])
    ne.create_negotiation("t2", ["a", "b"])
    ne.cancel_negotiation(nid1)
    assert len(ne.list_negotiations()) == 2
    assert len(ne.list_negotiations(status="cancelled")) == 1
    assert len(ne.list_negotiations(tag="urgent")) == 1
    print("OK: list")

def test_history():
    ne = AgentNegotiationEngine()
    nid = ne.create_negotiation("t1", ["a", "b"])
    ne.submit_proposal(nid, "a", 50)
    hist = ne.get_history()
    assert len(hist) >= 2
    limited = ne.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")

def test_callback():
    ne = AgentNegotiationEngine()
    fired = []
    ne.on_change("mon", lambda a, d: fired.append(a))
    ne.create_negotiation("t1", ["a", "b"])
    assert "negotiation_created" in fired
    print("OK: callback")

def test_callbacks():
    ne = AgentNegotiationEngine()
    assert ne.on_change("m", lambda a, d: None) is True
    assert ne.on_change("m", lambda a, d: None) is False
    assert ne.remove_callback("m") is True
    assert ne.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    ne = AgentNegotiationEngine()
    ne.create_negotiation("t1", ["a", "b"])
    stats = ne.get_stats()
    assert stats["total_created"] == 1
    assert stats["open"] == 1
    print("OK: stats")

def test_reset():
    ne = AgentNegotiationEngine()
    ne.create_negotiation("t1", ["a", "b"])
    ne.reset()
    assert ne.list_negotiations() == []
    assert ne.get_stats()["total_created"] == 0
    print("OK: reset")

def main():
    print("=== Agent Negotiation Engine Tests ===\n")
    test_create()
    test_invalid_create()
    test_max_negotiations()
    test_submit_proposal()
    test_submit_non_participant()
    test_vote()
    test_vote_duplicate()
    test_majority_resolves()
    test_cancel()
    test_submit_to_closed()
    test_list()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 16 TESTS PASSED ===")

if __name__ == "__main__":
    main()
