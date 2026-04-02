"""Test agent tag store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_tag_store import AgentTagStore


def test_add_tag():
    ts = AgentTagStore()
    aid = ts.add_tag("agent-1", "gpu", metadata={"type": "A100"})
    assert len(aid) > 0
    assert ts.add_tag("agent-1", "gpu") == ""  # duplicate
    print("OK: add tag")


def test_remove_tag():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    assert ts.remove_tag("agent-1", "gpu") is True
    assert ts.remove_tag("agent-1", "gpu") is False
    print("OK: remove tag")


def test_get_agent_tags():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    ts.add_tag("agent-1", "high-memory")
    tags = ts.get_agent_tags("agent-1")
    assert "gpu" in tags
    assert "high-memory" in tags
    print("OK: get agent tags")


def test_find_agents_by_tag():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    ts.add_tag("agent-2", "gpu")
    ts.add_tag("agent-3", "cpu")
    agents = ts.find_agents_by_tag("gpu")
    assert "agent-1" in agents
    assert "agent-2" in agents
    assert "agent-3" not in agents
    print("OK: find agents by tag")


def test_has_tag():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    assert ts.has_tag("agent-1", "gpu") is True
    assert ts.has_tag("agent-1", "cpu") is False
    print("OK: has tag")


def test_list_all_tags():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    ts.add_tag("agent-2", "cpu")
    tags = ts.list_all_tags()
    assert "gpu" in tags
    assert "cpu" in tags
    print("OK: list all tags")


def test_get_tag_count():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    ts.add_tag("agent-2", "gpu")
    ts.add_tag("agent-3", "gpu")
    assert ts.get_tag_count("gpu") == 3
    print("OK: get tag count")


def test_bulk_tag():
    ts = AgentTagStore()
    count = ts.bulk_tag(["agent-1", "agent-2", "agent-3"], "production")
    assert count == 3
    assert ts.has_tag("agent-2", "production") is True
    print("OK: bulk tag")


def test_callbacks():
    ts = AgentTagStore()
    fired = []
    ts.on_change("mon", lambda a, d: fired.append(a))
    ts.add_tag("agent-1", "gpu")
    assert len(fired) >= 1
    assert ts.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    stats = ts.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ts = AgentTagStore()
    ts.add_tag("agent-1", "gpu")
    ts.reset()
    assert ts.list_all_tags() == []
    print("OK: reset")


def main():
    print("=== Agent Tag Store Tests ===\n")
    test_add_tag()
    test_remove_tag()
    test_get_agent_tags()
    test_find_agents_by_tag()
    test_has_tag()
    test_list_all_tags()
    test_get_tag_count()
    test_bulk_tag()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
