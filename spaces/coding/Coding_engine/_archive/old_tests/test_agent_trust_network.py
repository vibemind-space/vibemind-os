"""Test agent trust network."""
import sys
sys.path.insert(0, ".")
from src.services.agent_trust_network import AgentTrustNetwork

def test_establish():
    tn = AgentTrustNetwork()
    eid = tn.establish_trust("a1", "a2", tags=["team"])
    assert eid.startswith("te-")
    e = tn.get_edge("a1", "a2")
    assert e["trust_score"] == 50.0
    print("OK: establish")

def test_invalid():
    tn = AgentTrustNetwork()
    assert tn.establish_trust("", "a2") == ""
    assert tn.establish_trust("a1", "") == ""
    assert tn.establish_trust("a1", "a1") == ""
    print("OK: invalid")

def test_duplicate():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2")
    assert tn.establish_trust("a1", "a2") == ""
    print("OK: duplicate")

def test_max_edges():
    tn = AgentTrustNetwork(max_edges=2)
    tn.establish_trust("a1", "a2")
    tn.establish_trust("a2", "a3")
    assert tn.establish_trust("a3", "a1") == ""
    print("OK: max edges")

def test_get_trust():
    tn = AgentTrustNetwork(default_trust=50.0)
    tn.establish_trust("a1", "a2")
    assert tn.get_trust("a1", "a2") == 50.0
    assert tn.get_trust("a2", "a1") == 0.0  # directional
    print("OK: get trust")

def test_positive():
    tn = AgentTrustNetwork(trust_increment=5.0)
    tn.establish_trust("a1", "a2", initial_trust=50.0)
    assert tn.record_positive("a1", "a2") is True
    assert tn.get_trust("a1", "a2") == 55.0
    assert tn.record_positive("nonexistent", "a2") is False
    print("OK: positive")

def test_negative():
    tn = AgentTrustNetwork(trust_decrement=10.0)
    tn.establish_trust("a1", "a2", initial_trust=50.0)
    assert tn.record_negative("a1", "a2") is True
    assert tn.get_trust("a1", "a2") == 40.0
    print("OK: negative")

def test_clamped():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2", initial_trust=95.0)
    tn.record_positive("a1", "a2", bonus=20.0)
    assert tn.get_trust("a1", "a2") == 100.0
    tn.establish_trust("a3", "a4", initial_trust=5.0)
    tn.record_negative("a3", "a4", penalty=20.0)
    assert tn.get_trust("a3", "a4") == 0.0
    print("OK: clamped")

def test_remove():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2")
    assert tn.remove_trust("a1", "a2") is True
    assert tn.remove_trust("a1", "a2") is False
    print("OK: remove")

def test_trusted_by():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a3", initial_trust=80.0)
    tn.establish_trust("a2", "a3", initial_trust=60.0)
    result = tn.get_trusted_by("a3", min_trust=70.0)
    assert len(result) == 1
    assert result[0]["from_agent"] == "a1"
    print("OK: trusted by")

def test_trusts():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2", initial_trust=80.0)
    tn.establish_trust("a1", "a3", initial_trust=30.0)
    result = tn.get_trusts("a1", min_trust=50.0)
    assert len(result) == 1
    print("OK: trusts")

def test_mutual():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2", initial_trust=80.0)
    tn.establish_trust("a2", "a1", initial_trust=60.0)
    m = tn.get_mutual_trust("a1", "a2")
    assert m["a_trusts_b"] == 80.0
    assert m["b_trusts_a"] == 60.0
    print("OK: mutual")

def test_decay():
    tn = AgentTrustNetwork(default_trust=50.0)
    tn.establish_trust("a1", "a2", initial_trust=90.0)
    count = tn.decay_all(decay_pct=10.0)
    assert count == 1
    # 90 - (90-50)*0.1 = 90 - 4 = 86
    assert abs(tn.get_trust("a1", "a2") - 86.0) < 0.01
    print("OK: decay")

def test_list_edges():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2", initial_trust=80.0, tags=["team"])
    tn.establish_trust("a2", "a3", initial_trust=30.0)
    assert len(tn.list_edges()) == 2
    assert len(tn.list_edges(min_trust=50.0)) == 1
    assert len(tn.list_edges(tag="team")) == 1
    print("OK: list edges")

def test_history():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2")
    tn.record_positive("a1", "a2")
    tn.record_negative("a1", "a2")
    hist = tn.get_history()
    assert len(hist) == 2
    limited = tn.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")

def test_callbacks():
    tn = AgentTrustNetwork()
    assert tn.on_change("m", lambda a, d: None) is True
    assert tn.on_change("m", lambda a, d: None) is False
    assert tn.remove_callback("m") is True
    assert tn.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2")
    tn.record_positive("a1", "a2")
    stats = tn.get_stats()
    assert stats["current_edges"] == 1
    assert stats["total_created"] == 1
    assert stats["total_updates"] == 1
    print("OK: stats")

def test_reset():
    tn = AgentTrustNetwork()
    tn.establish_trust("a1", "a2")
    tn.reset()
    assert tn.list_edges() == []
    assert tn.get_stats()["total_created"] == 0
    print("OK: reset")

def main():
    print("=== Agent Trust Network Tests ===\n")
    test_establish()
    test_invalid()
    test_duplicate()
    test_max_edges()
    test_get_trust()
    test_positive()
    test_negative()
    test_clamped()
    test_remove()
    test_trusted_by()
    test_trusts()
    test_mutual()
    test_decay()
    test_list_edges()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")

if __name__ == "__main__":
    main()
