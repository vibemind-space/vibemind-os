"""Test agent capability index -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_capability_index import AgentCapabilityIndex


def test_register_capability():
    ci = AgentCapabilityIndex()
    eid = ci.register_capability("agent-1", "python", metadata={"level": "expert"})
    assert len(eid) > 0
    assert eid.startswith("aci-")
    print("OK: register capability")


def test_get_capability():
    ci = AgentCapabilityIndex()
    eid = ci.register_capability("agent-1", "python")
    cap = ci.get_capability(eid)
    assert cap is not None
    assert cap["agent_id"] == "agent-1"
    assert cap["capability"] == "python"
    assert ci.get_capability("nonexistent") is None
    print("OK: get capability")


def test_get_agent_capabilities():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    ci.register_capability("agent-1", "javascript")
    ci.register_capability("agent-2", "python")
    caps = ci.get_agent_capabilities("agent-1")
    assert "python" in caps
    assert "javascript" in caps
    assert len(caps) == 2
    print("OK: get agent capabilities")


def test_find_agents_with_capability():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    ci.register_capability("agent-2", "python")
    ci.register_capability("agent-3", "javascript")
    agents = ci.find_agents_with_capability("python")
    assert "agent-1" in agents
    assert "agent-2" in agents
    assert len(agents) == 2
    print("OK: find agents with capability")


def test_has_capability():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    assert ci.has_capability("agent-1", "python") is True
    assert ci.has_capability("agent-1", "rust") is False
    print("OK: has capability")


def test_remove_capability():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    assert ci.remove_capability("agent-1", "python") is True
    assert ci.remove_capability("agent-1", "python") is False
    print("OK: remove capability")


def test_list_capabilities():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    ci.register_capability("agent-1", "javascript")
    ci.register_capability("agent-2", "python")
    caps = ci.list_capabilities()
    assert "python" in caps
    assert "javascript" in caps
    print("OK: list capabilities")


def test_list_agents():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    ci.register_capability("agent-2", "javascript")
    agents = ci.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ci = AgentCapabilityIndex()
    fired = []
    ci.on_change("mon", lambda a, d: fired.append(a))
    ci.register_capability("agent-1", "python")
    assert len(fired) >= 1
    assert ci.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    stats = ci.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ci = AgentCapabilityIndex()
    ci.register_capability("agent-1", "python")
    ci.reset()
    assert ci.get_entry_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Capability Index Tests ===\n")
    test_register_capability()
    test_get_capability()
    test_get_agent_capabilities()
    test_find_agents_with_capability()
    test_has_capability()
    test_remove_capability()
    test_list_capabilities()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
