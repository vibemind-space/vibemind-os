"""Test agent context manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_context_manager import AgentContextManager


def test_create_context():
    cm = AgentContextManager()
    cid = cm.create_context("agent-1", context_data={"env": "prod"})
    assert len(cid) > 0
    assert cid.startswith("acm2-")
    print("OK: create context")


def test_get_context():
    cm = AgentContextManager()
    cid = cm.create_context("agent-1", context_data={"env": "prod"})
    ctx = cm.get_context(cid)
    assert ctx is not None
    assert ctx["agent_id"] == "agent-1"
    assert ctx["data"]["env"] == "prod"
    assert cm.get_context("nonexistent") is None
    print("OK: get context")


def test_update_context():
    cm = AgentContextManager()
    cid = cm.create_context("agent-1")
    assert cm.update_context(cid, "key", "value") is True
    val = cm.get_context_value(cid, "key")
    assert val == "value"
    print("OK: update context")


def test_get_context_value():
    cm = AgentContextManager()
    cid = cm.create_context("agent-1", context_data={"env": "prod"})
    assert cm.get_context_value(cid, "env") == "prod"
    assert cm.get_context_value(cid, "missing") is None
    print("OK: get context value")


def test_close_context():
    cm = AgentContextManager()
    cid = cm.create_context("agent-1")
    assert cm.close_context(cid) is True
    ctx = cm.get_context(cid)
    assert ctx["status"] == "closed"
    print("OK: close context")


def test_get_agent_contexts():
    cm = AgentContextManager()
    cm.create_context("agent-1", context_data={"a": 1})
    cm.create_context("agent-1", context_data={"b": 2})
    cm.create_context("agent-2")
    contexts = cm.get_agent_contexts("agent-1")
    assert len(contexts) == 2
    print("OK: get agent contexts")


def test_get_active_contexts():
    cm = AgentContextManager()
    c1 = cm.create_context("agent-1")
    c2 = cm.create_context("agent-1")
    cm.close_context(c1)
    active = cm.get_active_contexts("agent-1")
    assert len(active) == 1
    print("OK: get active contexts")


def test_remove_context():
    cm = AgentContextManager()
    cid = cm.create_context("agent-1")
    assert cm.remove_context(cid) is True
    assert cm.remove_context(cid) is False
    print("OK: remove context")


def test_list_agents():
    cm = AgentContextManager()
    cm.create_context("agent-1")
    cm.create_context("agent-2")
    agents = cm.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    cm = AgentContextManager()
    fired = []
    cm.on_change("mon", lambda a, d: fired.append(a))
    cm.create_context("agent-1")
    assert len(fired) >= 1
    assert cm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cm = AgentContextManager()
    cm.create_context("agent-1")
    stats = cm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cm = AgentContextManager()
    cm.create_context("agent-1")
    cm.reset()
    assert cm.get_context_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Context Manager Tests ===\n")
    test_create_context()
    test_get_context()
    test_update_context()
    test_get_context_value()
    test_close_context()
    test_get_agent_contexts()
    test_get_active_contexts()
    test_remove_context()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
