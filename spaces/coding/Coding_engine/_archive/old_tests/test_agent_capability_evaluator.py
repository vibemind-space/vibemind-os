"""Test agent capability evaluator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_capability_evaluator import AgentCapabilityEvaluator


def test_register_capability():
    ce = AgentCapabilityEvaluator()
    eid = ce.register_capability("agent-1", "coding", initial_score=0.7)
    assert len(eid) > 0
    assert eid.startswith("ace-")
    # Duplicate returns ""
    assert ce.register_capability("agent-1", "coding") == ""
    print("OK: register capability")


def test_get_capability():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding", initial_score=0.7)
    cap = ce.get_capability("agent-1", "coding")
    assert cap is not None
    assert cap["agent_id"] == "agent-1"
    assert cap["capability_name"] == "coding"
    assert cap["score"] == 0.7
    assert ce.get_capability("agent-1", "missing") is None
    print("OK: get capability")


def test_evaluate():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding", initial_score=0.5)
    assert ce.evaluate("agent-1", "coding", 0.9) is True
    cap = ce.get_capability("agent-1", "coding")
    assert cap["score"] != 0.5  # Should be averaged
    assert ce.evaluate("agent-1", "missing", 0.5) is False
    print("OK: evaluate")


def test_get_agent_capabilities():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding")
    ce.register_capability("agent-1", "testing")
    ce.register_capability("agent-2", "coding")
    caps = ce.get_agent_capabilities("agent-1")
    assert len(caps) == 2
    print("OK: get agent capabilities")


def test_get_top_agents():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding", initial_score=0.9)
    ce.register_capability("agent-2", "coding", initial_score=0.7)
    ce.register_capability("agent-3", "coding", initial_score=0.8)
    top = ce.get_top_agents("coding", limit=2)
    assert len(top) == 2
    assert top[0]["agent_id"] == "agent-1"
    print("OK: get top agents")


def test_get_agent_score():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding", initial_score=0.8)
    ce.register_capability("agent-1", "testing", initial_score=0.6)
    score = ce.get_agent_score("agent-1")
    assert score == 0.7  # Average of 0.8 and 0.6
    assert ce.get_agent_score("nonexistent") == 0.0
    print("OK: get agent score")


def test_remove_capability():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding")
    assert ce.remove_capability("agent-1", "coding") is True
    assert ce.remove_capability("agent-1", "coding") is False
    print("OK: remove capability")


def test_list_capabilities():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding")
    ce.register_capability("agent-2", "testing")
    caps = ce.list_capabilities()
    assert "coding" in caps
    assert "testing" in caps
    print("OK: list capabilities")


def test_list_agents():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding")
    ce.register_capability("agent-2", "testing")
    agents = ce.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ce = AgentCapabilityEvaluator()
    fired = []
    ce.on_change("mon", lambda a, d: fired.append(a))
    ce.register_capability("agent-1", "coding")
    assert len(fired) >= 1
    assert ce.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding")
    stats = ce.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ce = AgentCapabilityEvaluator()
    ce.register_capability("agent-1", "coding")
    ce.reset()
    assert ce.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Capability Evaluator Tests ===\n")
    test_register_capability()
    test_get_capability()
    test_evaluate()
    test_get_agent_capabilities()
    test_get_top_agents()
    test_get_agent_score()
    test_remove_capability()
    test_list_capabilities()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
