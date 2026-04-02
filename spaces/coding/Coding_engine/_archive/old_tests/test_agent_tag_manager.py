"""Tests for AgentTagManager."""

import sys
sys.path.insert(0, ".")

from src.services.agent_tag_manager import AgentTagManager


def test_add_tag():
    mgr = AgentTagManager()
    tid = mgr.add_tag("agent-1", "env", "production")
    assert tid.startswith("atg-"), f"Expected atg- prefix, got {tid}"
    # Duplicate returns same ID
    tid2 = mgr.add_tag("agent-1", "env", "production")
    assert tid2 == tid, "Duplicate add should return same ID"
    # Empty agent/tag returns ""
    assert mgr.add_tag("", "env") == ""
    assert mgr.add_tag("agent-1", "") == ""
    print("  test_add_tag PASSED")


def test_remove_tag():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "prod")
    assert mgr.remove_tag("agent-1", "env") is True
    assert mgr.remove_tag("agent-1", "env") is False
    assert mgr.remove_tag("no-agent", "env") is False
    print("  test_remove_tag PASSED")


def test_get_tags():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "prod")
    mgr.add_tag("agent-1", "role", "worker")
    tags = mgr.get_tags("agent-1")
    assert len(tags) == 2
    assert tags[0] == {"tag": "env", "value": "prod"}
    assert tags[1] == {"tag": "role", "value": "worker"}
    # Unknown agent
    assert mgr.get_tags("unknown") == []
    print("  test_get_tags PASSED")


def test_has_tag():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "prod")
    assert mgr.has_tag("agent-1", "env") is True
    assert mgr.has_tag("agent-1", "missing") is False
    assert mgr.has_tag("unknown", "env") is False
    print("  test_has_tag PASSED")


def test_get_tag_value():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "production")
    assert mgr.get_tag_value("agent-1", "env") == "production"
    # Default value tag
    mgr.add_tag("agent-1", "flagged")
    assert mgr.get_tag_value("agent-1", "flagged") == ""
    # Missing
    assert mgr.get_tag_value("agent-1", "nope") == ""
    assert mgr.get_tag_value("unknown", "env") == ""
    print("  test_get_tag_value PASSED")


def test_find_by_tag():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "prod")
    mgr.add_tag("agent-2", "env", "staging")
    mgr.add_tag("agent-3", "role", "worker")
    result = mgr.find_by_tag("env")
    assert result == ["agent-1", "agent-2"]
    assert mgr.find_by_tag("role") == ["agent-3"]
    assert mgr.find_by_tag("missing") == []
    print("  test_find_by_tag PASSED")


def test_get_tag_count():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "prod")
    mgr.add_tag("agent-1", "role", "worker")
    mgr.add_tag("agent-2", "env", "staging")
    assert mgr.get_tag_count("agent-1") == 2
    assert mgr.get_tag_count("agent-2") == 1
    assert mgr.get_tag_count("unknown") == 0
    assert mgr.get_tag_count() == 3
    print("  test_get_tag_count PASSED")


def test_list_agents():
    mgr = AgentTagManager()
    mgr.add_tag("agent-2", "env", "prod")
    mgr.add_tag("agent-1", "role", "worker")
    assert mgr.list_agents() == ["agent-1", "agent-2"]
    print("  test_list_agents PASSED")


def test_callbacks():
    mgr = AgentTagManager()
    events = []
    mgr.on_change("tracker", lambda e, d: events.append((e, d)))
    # Duplicate name
    assert mgr.on_change("tracker", lambda e, d: None) is False
    mgr.add_tag("agent-1", "env", "prod")
    assert len(events) == 1
    assert events[0][0] == "tag_added"
    mgr.remove_tag("agent-1", "env")
    assert len(events) == 2
    assert events[1][0] == "tag_removed"
    # Remove callback
    assert mgr.remove_callback("tracker") is True
    assert mgr.remove_callback("tracker") is False
    mgr.add_tag("agent-1", "env", "prod")
    assert len(events) == 2  # no new event
    print("  test_callbacks PASSED")


def test_stats():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "prod")
    mgr.add_tag("agent-2", "role", "worker")
    mgr.remove_tag("agent-1", "env")
    stats = mgr.get_stats()
    assert stats["total_tags"] == 1
    assert stats["total_added"] == 2
    assert stats["total_removed"] == 1
    assert stats["total_agents"] == 1
    assert stats["max_entries"] == 10000
    assert stats["callbacks"] == 0
    print("  test_stats PASSED")


def test_reset():
    mgr = AgentTagManager()
    mgr.add_tag("agent-1", "env", "prod")
    mgr.on_change("cb", lambda e, d: None)
    mgr.reset()
    assert mgr.get_tag_count() == 0
    assert mgr.list_agents() == []
    stats = mgr.get_stats()
    assert stats["total_added"] == 0
    assert stats["total_removed"] == 0
    assert stats["callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_add_tag()
    test_remove_tag()
    test_get_tags()
    test_has_tag()
    test_get_tag_value()
    test_find_by_tag()
    test_get_tag_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")
