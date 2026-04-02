"""Tests for AgentLabelManager."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "services"))

from agent_label_manager import AgentLabelManager


def test_add_label():
    mgr = AgentLabelManager()
    lid = mgr.add_label("agent-1", "gpu-enabled")
    assert lid.startswith("alm2-"), f"Expected alm2- prefix, got {lid}"
    assert mgr.get_label_count() == 1
    # empty args
    assert mgr.add_label("", "gpu-enabled") == ""
    assert mgr.add_label("agent-1", "") == ""
    print("  test_add_label PASSED")


def test_add_label_duplicate():
    mgr = AgentLabelManager()
    lid1 = mgr.add_label("agent-1", "gpu-enabled")
    lid2 = mgr.add_label("agent-1", "gpu-enabled")
    assert lid1 == lid2, "Duplicate add should return same ID"
    assert mgr.get_label_count() == 1, "Duplicate should not increase count"
    print("  test_add_label_duplicate PASSED")


def test_remove_label():
    mgr = AgentLabelManager()
    mgr.add_label("agent-1", "gpu-enabled")
    assert mgr.remove_label("agent-1", "gpu-enabled") is True
    assert mgr.get_label_count() == 0
    # remove non-existent
    assert mgr.remove_label("agent-1", "gpu-enabled") is False
    assert mgr.remove_label("agent-nope", "gpu-enabled") is False
    print("  test_remove_label PASSED")


def test_get_labels():
    mgr = AgentLabelManager()
    mgr.add_label("agent-1", "gpu-enabled")
    mgr.add_label("agent-1", "high-memory")
    mgr.add_label("agent-1", "arm64")
    labels = mgr.get_labels("agent-1")
    assert labels == ["arm64", "gpu-enabled", "high-memory"]
    # unknown agent
    assert mgr.get_labels("agent-nope") == []
    print("  test_get_labels PASSED")


def test_has_label():
    mgr = AgentLabelManager()
    mgr.add_label("agent-1", "gpu-enabled")
    assert mgr.has_label("agent-1", "gpu-enabled") is True
    assert mgr.has_label("agent-1", "cpu-only") is False
    assert mgr.has_label("agent-nope", "gpu-enabled") is False
    print("  test_has_label PASSED")


def test_find_agents():
    mgr = AgentLabelManager()
    mgr.add_label("agent-a", "gpu-enabled")
    mgr.add_label("agent-b", "gpu-enabled")
    mgr.add_label("agent-c", "cpu-only")
    agents = mgr.find_agents("gpu-enabled")
    assert agents == ["agent-a", "agent-b"]
    assert mgr.find_agents("cpu-only") == ["agent-c"]
    assert mgr.find_agents("nonexistent") == []
    print("  test_find_agents PASSED")


def test_get_label_count():
    mgr = AgentLabelManager()
    mgr.add_label("agent-1", "gpu-enabled")
    mgr.add_label("agent-1", "high-memory")
    mgr.add_label("agent-2", "gpu-enabled")
    assert mgr.get_label_count("agent-1") == 2
    assert mgr.get_label_count("agent-2") == 1
    assert mgr.get_label_count("agent-nope") == 0
    # total
    assert mgr.get_label_count() == 3
    print("  test_get_label_count PASSED")


def test_list_agents():
    mgr = AgentLabelManager()
    mgr.add_label("agent-b", "label-1")
    mgr.add_label("agent-a", "label-2")
    agents = mgr.list_agents()
    assert agents == ["agent-a", "agent-b"]
    print("  test_list_agents PASSED")


def test_list_all_labels():
    mgr = AgentLabelManager()
    mgr.add_label("agent-1", "gpu-enabled")
    mgr.add_label("agent-2", "gpu-enabled")
    mgr.add_label("agent-1", "high-memory")
    mgr.add_label("agent-3", "arm64")
    labels = mgr.list_all_labels()
    assert labels == ["arm64", "gpu-enabled", "high-memory"]
    print("  test_list_all_labels PASSED")


def test_callbacks():
    mgr = AgentLabelManager()
    events = []
    assert mgr.on_change("listener", lambda action, detail: events.append((action, detail))) is True
    # duplicate name returns False
    assert mgr.on_change("listener", lambda a, d: None) is False

    mgr.add_label("agent-1", "gpu-enabled")
    mgr.remove_label("agent-1", "gpu-enabled")

    assert len(events) == 2
    assert events[0][0] == "label_added"
    assert events[0][1]["agent_id"] == "agent-1"
    assert events[0][1]["label"] == "gpu-enabled"
    assert events[1][0] == "label_removed"

    # remove_callback
    assert mgr.remove_callback("listener") is True
    assert mgr.remove_callback("listener") is False
    print("  test_callbacks PASSED")


def test_stats():
    mgr = AgentLabelManager()
    mgr.add_label("agent-1", "gpu-enabled")
    mgr.add_label("agent-1", "high-memory")
    mgr.add_label("agent-2", "gpu-enabled")
    mgr.remove_label("agent-1", "gpu-enabled")

    stats = mgr.get_stats()
    assert stats["total_labels"] == 2
    assert stats["total_added"] == 3
    assert stats["total_removed"] == 1
    assert stats["total_agents"] == 2
    assert stats["unique_labels"] == 2
    assert stats["max_entries"] == 10000
    print("  test_stats PASSED")


def test_reset():
    mgr = AgentLabelManager()
    mgr.add_label("agent-1", "gpu-enabled")
    mgr.on_change("cb", lambda a, d: None)
    mgr.reset()
    assert mgr.get_label_count() == 0
    assert mgr.list_agents() == []
    assert mgr.list_all_labels() == []
    stats = mgr.get_stats()
    assert stats["total_added"] == 0
    assert stats["total_removed"] == 0
    assert stats["callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_add_label()
    test_add_label_duplicate()
    test_remove_label()
    test_get_labels()
    test_has_label()
    test_find_agents()
    test_get_label_count()
    test_list_agents()
    test_list_all_labels()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")
