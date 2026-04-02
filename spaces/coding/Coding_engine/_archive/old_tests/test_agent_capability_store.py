"""Test agent capability store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_capability_store import AgentCapabilityStore


def test_register_agent():
    cs = AgentCapabilityStore()
    result = cs.register_agent("agent-1", tags=["ml"])
    assert len(result) > 0
    assert cs.register_agent("agent-1") == ""  # dup
    print("OK: register agent")


def test_add_capability():
    cs = AgentCapabilityStore()
    cs.register_agent("agent-1")
    assert cs.add_capability("agent-1", "python", level=0.9) is True
    caps = cs.get_capabilities("agent-1")
    assert len(caps) >= 1
    print("OK: add capability")


def test_remove_capability():
    cs = AgentCapabilityStore()
    cs.register_agent("agent-1")
    cs.add_capability("agent-1", "python", level=0.9)
    assert cs.remove_capability("agent-1", "python") is True
    assert cs.remove_capability("agent-1", "python") is False
    print("OK: remove capability")


def test_find_agents_with():
    cs = AgentCapabilityStore()
    cs.register_agent("a1")
    cs.register_agent("a2")
    cs.add_capability("a1", "python", level=0.9)
    cs.add_capability("a2", "python", level=0.5)
    cs.add_capability("a2", "java", level=0.8)
    agents = cs.find_agents_with("python")
    assert len(agents) == 2
    agents_min = cs.find_agents_with("python", min_level=0.7)
    assert len(agents_min) == 1
    print("OK: find agents with")


def test_get_best_agent():
    cs = AgentCapabilityStore()
    cs.register_agent("a1")
    cs.register_agent("a2")
    cs.add_capability("a1", "python", level=0.7)
    cs.add_capability("a2", "python", level=0.95)
    best = cs.get_best_agent("python")
    assert best is not None
    assert best["agent_id"] == "a2"
    print("OK: get best agent")


def test_compare_agents():
    cs = AgentCapabilityStore()
    cs.register_agent("a1")
    cs.register_agent("a2")
    cs.add_capability("a1", "python", level=0.9)
    cs.add_capability("a1", "java", level=0.7)
    cs.add_capability("a2", "python", level=0.8)
    cs.add_capability("a2", "rust", level=0.6)
    comparison = cs.compare_agents("a1", "a2")
    assert "shared" in comparison or "common" in comparison
    print("OK: compare agents")


def test_list_agents():
    cs = AgentCapabilityStore()
    cs.register_agent("a1", tags=["ml"])
    cs.register_agent("a2")
    assert len(cs.list_agents()) == 2
    assert len(cs.list_agents(tag="ml")) == 1
    print("OK: list agents")


def test_remove_agent():
    cs = AgentCapabilityStore()
    cs.register_agent("a1")
    assert cs.remove_agent("a1") is True
    assert cs.remove_agent("a1") is False
    print("OK: remove agent")


def test_get_all_capabilities():
    cs = AgentCapabilityStore()
    cs.register_agent("a1")
    cs.add_capability("a1", "python")
    cs.add_capability("a1", "java")
    all_caps = cs.get_all_capabilities()
    assert "python" in all_caps
    assert "java" in all_caps
    print("OK: get all capabilities")


def test_callbacks():
    cs = AgentCapabilityStore()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))
    cs.register_agent("a1")
    assert len(fired) >= 1
    assert cs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cs = AgentCapabilityStore()
    cs.register_agent("a1")
    stats = cs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cs = AgentCapabilityStore()
    cs.register_agent("a1")
    cs.reset()
    assert cs.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Capability Store Tests ===\n")
    test_register_agent()
    test_add_capability()
    test_remove_capability()
    test_find_agents_with()
    test_get_best_agent()
    test_compare_agents()
    test_list_agents()
    test_remove_agent()
    test_get_all_capabilities()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
