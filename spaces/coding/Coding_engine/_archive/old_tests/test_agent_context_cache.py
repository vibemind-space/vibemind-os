"""Test agent context cache -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_context_cache import AgentContextCache


def test_store_context():
    cc = AgentContextCache()
    cid = cc.store_context("agent-1", "conversation", "Hello world", metadata={"turn": 1})
    assert len(cid) > 0
    assert cid.startswith("acc-")
    c = cc.get_context(cid)
    assert c is not None
    assert c["agent_id"] == "agent-1"
    assert c["context_type"] == "conversation"
    assert c["content"] == "Hello world"
    print("OK: store context")


def test_get_agent_contexts():
    cc = AgentContextCache()
    cc.store_context("agent-1", "conv", "msg1")
    cc.store_context("agent-1", "task", "task1")
    cc.store_context("agent-2", "conv", "msg2")
    all_c = cc.get_agent_contexts("agent-1")
    assert len(all_c) == 2
    conv_only = cc.get_agent_contexts("agent-1", context_type="conv")
    assert len(conv_only) == 1
    print("OK: get agent contexts")


def test_get_latest_context():
    cc = AgentContextCache()
    cc.store_context("agent-1", "conv", "first")
    cc.store_context("agent-1", "conv", "second")
    latest = cc.get_latest_context("agent-1", context_type="conv")
    assert latest is not None
    assert latest["content"] == "second"
    assert cc.get_latest_context("nonexistent") is None
    print("OK: get latest context")


def test_search_contexts():
    cc = AgentContextCache()
    cc.store_context("agent-1", "conv", "deploy to production")
    cc.store_context("agent-1", "conv", "run unit tests")
    cc.store_context("agent-1", "conv", "deploy staging")
    results = cc.search_contexts("agent-1", "deploy")
    assert len(results) == 2
    print("OK: search contexts")


def test_delete_context():
    cc = AgentContextCache()
    cid = cc.store_context("agent-1", "conv", "temp")
    assert cc.delete_context(cid) is True
    assert cc.delete_context(cid) is False
    print("OK: delete context")


def test_clear_agent_contexts():
    cc = AgentContextCache()
    cc.store_context("agent-1", "a", "x")
    cc.store_context("agent-1", "b", "y")
    cc.store_context("agent-2", "a", "z")
    count = cc.clear_agent_contexts("agent-1")
    assert count == 2
    assert cc.get_context_count("agent-1") == 0
    assert cc.get_context_count("agent-2") == 1
    print("OK: clear agent contexts")


def test_get_context_count():
    cc = AgentContextCache()
    cc.store_context("agent-1", "a", "x")
    cc.store_context("agent-1", "b", "y")
    assert cc.get_context_count("agent-1") == 2
    assert cc.get_context_count("nonexistent") == 0
    print("OK: get context count")


def test_list_agents():
    cc = AgentContextCache()
    cc.store_context("agent-1", "a", "x")
    cc.store_context("agent-2", "a", "y")
    agents = cc.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    cc = AgentContextCache()
    fired = []
    cc.on_change("mon", lambda a, d: fired.append(a))
    cc.store_context("agent-1", "conv", "hi")
    assert len(fired) >= 1
    assert cc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cc = AgentContextCache()
    cc.store_context("agent-1", "conv", "hi")
    stats = cc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cc = AgentContextCache()
    cc.store_context("agent-1", "conv", "hi")
    cc.reset()
    assert cc.get_context_count("agent-1") == 0
    print("OK: reset")


def main():
    print("=== Agent Context Cache Tests ===\n")
    test_store_context()
    test_get_agent_contexts()
    test_get_latest_context()
    test_search_contexts()
    test_delete_context()
    test_clear_agent_contexts()
    test_get_context_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
