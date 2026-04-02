"""Test agent capability cache -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_capability_cache import AgentCapabilityCache


def test_cache_capability():
    cc = AgentCapabilityCache()
    cid = cc.cache_capability("agent-1", "python", level=5)
    assert len(cid) > 0
    assert cid.startswith("acc-")
    print("OK: cache capability")


def test_get_capabilities():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python", level=5)
    cc.cache_capability("agent-1", "java", level=3)
    caps = cc.get_capabilities("agent-1")
    assert len(caps) == 2
    print("OK: get capabilities")


def test_has_capability():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python", level=5)
    assert cc.has_capability("agent-1", "python") is True
    assert cc.has_capability("agent-1", "rust") is False
    print("OK: has capability")


def test_get_capability_level():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python", level=5)
    assert cc.get_capability_level("agent-1", "python") == 5
    assert cc.get_capability_level("agent-1", "rust") == 0
    print("OK: get capability level")


def test_remove_capability():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python", level=5)
    assert cc.remove_capability("agent-1", "python") is True
    assert cc.remove_capability("agent-1", "nonexistent") is False
    assert cc.has_capability("agent-1", "python") is False
    print("OK: remove capability")


def test_get_capability_count():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python")
    cc.cache_capability("agent-2", "java")
    assert cc.get_capability_count() == 2
    assert cc.get_capability_count("agent-1") == 1
    print("OK: get capability count")


def test_list_agents():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python")
    cc.cache_capability("agent-2", "java")
    agents = cc.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    cc = AgentCapabilityCache()
    fired = []
    cc.on_change("mon", lambda a, d: fired.append(a))
    cc.cache_capability("agent-1", "python")
    assert len(fired) >= 1
    assert cc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python")
    stats = cc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cc = AgentCapabilityCache()
    cc.cache_capability("agent-1", "python")
    cc.reset()
    assert cc.get_capability_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Capability Cache Tests ===\n")
    test_cache_capability()
    test_get_capabilities()
    test_has_capability()
    test_get_capability_level()
    test_remove_capability()
    test_get_capability_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
