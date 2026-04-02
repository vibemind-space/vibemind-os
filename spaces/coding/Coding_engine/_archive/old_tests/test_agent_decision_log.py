"""Test agent decision log -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_decision_log import AgentDecisionLog


def test_log_decision():
    dl = AgentDecisionLog()
    did = dl.log_decision("agent-1", "routing", "option-A", alternatives=["option-B", "option-C"])
    assert len(did) > 0
    assert did.startswith("adl-")
    print("OK: log decision")


def test_get_decision():
    dl = AgentDecisionLog()
    did = dl.log_decision("agent-1", "routing", "option-A", reason="lowest latency")
    dec = dl.get_decision(did)
    assert dec is not None
    assert dec["agent_id"] == "agent-1"
    assert dec["decision_type"] == "routing"
    assert dec["choice"] == "option-A"
    assert dec["reason"] == "lowest latency"
    assert dl.get_decision("nonexistent") is None
    print("OK: get decision")


def test_get_agent_decisions():
    dl = AgentDecisionLog()
    dl.log_decision("agent-1", "routing", "A")
    dl.log_decision("agent-1", "scaling", "up")
    dl.log_decision("agent-2", "routing", "B")
    decs = dl.get_agent_decisions("agent-1")
    assert len(decs) == 2
    print("OK: get agent decisions")


def test_get_decisions_by_type():
    dl = AgentDecisionLog()
    dl.log_decision("agent-1", "routing", "A")
    dl.log_decision("agent-2", "routing", "B")
    dl.log_decision("agent-1", "scaling", "up")
    decs = dl.get_decisions_by_type("routing")
    assert len(decs) == 2
    print("OK: get decisions by type")


def test_get_decision_count():
    dl = AgentDecisionLog()
    dl.log_decision("agent-1", "routing", "A")
    dl.log_decision("agent-1", "scaling", "up")
    assert dl.get_decision_count("agent-1") == 2
    assert dl.get_decision_count() == 2
    print("OK: get decision count")


def test_get_recent_decisions():
    dl = AgentDecisionLog()
    for i in range(5):
        dl.log_decision("agent-1", f"type-{i}", f"choice-{i}")
    recent = dl.get_recent_decisions(limit=3)
    assert len(recent) == 3
    print("OK: get recent decisions")


def test_search_decisions():
    dl = AgentDecisionLog()
    dl.log_decision("agent-1", "routing", "A")
    dl.log_decision("agent-1", "scaling", "up")
    dl.log_decision("agent-2", "routing", "B")
    results = dl.search_decisions(agent_id="agent-1", decision_type="routing")
    assert len(results) == 1
    print("OK: search decisions")


def test_purge():
    dl = AgentDecisionLog()
    for i in range(10):
        dl.log_decision("agent-1", f"type-{i}", f"choice-{i}")
    removed = dl.purge("agent-1", keep_latest=3)
    assert removed == 7
    assert dl.get_decision_count("agent-1") == 3
    print("OK: purge")


def test_list_agents():
    dl = AgentDecisionLog()
    dl.log_decision("agent-1", "routing", "A")
    dl.log_decision("agent-2", "scaling", "up")
    agents = dl.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    dl = AgentDecisionLog()
    fired = []
    dl.on_change("mon", lambda a, d: fired.append(a))
    dl.log_decision("agent-1", "routing", "A")
    assert len(fired) >= 1
    assert dl.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dl = AgentDecisionLog()
    dl.log_decision("agent-1", "routing", "A")
    stats = dl.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dl = AgentDecisionLog()
    dl.log_decision("agent-1", "routing", "A")
    dl.reset()
    assert dl.get_decision_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Decision Log Tests ===\n")
    test_log_decision()
    test_get_decision()
    test_get_agent_decisions()
    test_get_decisions_by_type()
    test_get_decision_count()
    test_get_recent_decisions()
    test_search_decisions()
    test_purge()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
