"""Tests for AgentWorkDistributor."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "services"))

from agent_work_distributor import AgentWorkDistributor


def test_register_agents():
    dist = AgentWorkDistributor()
    did = dist.register_agents("grp-1", ["agent-a", "agent-b", "agent-c"])
    assert did.startswith("awd-"), f"Expected awd- prefix, got {did}"
    assert dist.get_distributor_count() == 1
    # duplicate group returns ""
    assert dist.register_agents("grp-1", ["agent-x"]) == ""
    # empty args
    assert dist.register_agents("", ["agent-x"]) == ""
    assert dist.register_agents("grp-2", []) == ""
    # invalid strategy
    assert dist.register_agents("grp-3", ["agent-x"], strategy="random") == ""
    print("  test_register_agents PASSED")


def test_distribute_round_robin():
    dist = AgentWorkDistributor()
    dist.register_agents("grp-1", ["agent-a", "agent-b", "agent-c"], strategy="round_robin")
    r1 = dist.distribute("grp-1", "task-1")
    r2 = dist.distribute("grp-1", "task-2")
    r3 = dist.distribute("grp-1", "task-3")
    r4 = dist.distribute("grp-1", "task-4")
    assert r1 == "agent-a"
    assert r2 == "agent-b"
    assert r3 == "agent-c"
    assert r4 == "agent-a"  # wraps around
    print("  test_distribute_round_robin PASSED")


def test_distribute_least_loaded():
    dist = AgentWorkDistributor()
    dist.register_agents("grp-1", ["agent-a", "agent-b"], strategy="least_loaded")
    # First item goes to either (both have 0); assign manually to check balancing
    r1 = dist.distribute("grp-1", "task-1")
    assert r1 in ("agent-a", "agent-b")
    # Now one has 1 item, the other has 0, so next should go to the other
    r2 = dist.distribute("grp-1", "task-2")
    assert r2 != r1, "least_loaded should pick the agent with fewer assignments"
    # Now both have 1, third goes to either
    r3 = dist.distribute("grp-1", "task-3")
    assert r3 in ("agent-a", "agent-b")
    print("  test_distribute_least_loaded PASSED")


def test_get_assignments():
    dist = AgentWorkDistributor()
    dist.register_agents("grp-1", ["agent-a", "agent-b"], strategy="round_robin")
    dist.distribute("grp-1", "task-1")
    dist.distribute("grp-1", "task-2")
    dist.distribute("grp-1", "task-3")
    a_items = dist.get_assignments("agent-a")
    b_items = dist.get_assignments("agent-b")
    assert a_items == ["task-1", "task-3"]
    assert b_items == ["task-2"]
    # unknown agent returns empty list
    assert dist.get_assignments("agent-z") == []
    print("  test_get_assignments PASSED")


def test_get_assignment_count():
    dist = AgentWorkDistributor()
    dist.register_agents("grp-1", ["agent-a", "agent-b"], strategy="round_robin")
    dist.distribute("grp-1", "task-1")
    dist.distribute("grp-1", "task-2")
    dist.distribute("grp-1", "task-3")
    assert dist.get_assignment_count("agent-a") == 2
    assert dist.get_assignment_count("agent-b") == 1
    assert dist.get_assignment_count("agent-z") == 0
    # total (no agent_id)
    assert dist.get_assignment_count() == 3
    print("  test_get_assignment_count PASSED")


def test_get_distributor():
    dist = AgentWorkDistributor()
    did = dist.register_agents("grp-1", ["agent-a"], strategy="least_loaded")
    info = dist.get_distributor("grp-1")
    assert info is not None
    assert info["distributor_id"] == did
    assert info["group_id"] == "grp-1"
    assert info["agent_ids"] == ["agent-a"]
    assert info["strategy"] == "least_loaded"
    # not found
    assert dist.get_distributor("grp-nope") is None
    print("  test_get_distributor PASSED")


def test_list_groups():
    dist = AgentWorkDistributor()
    dist.register_agents("grp-b", ["agent-1"])
    dist.register_agents("grp-a", ["agent-2"])
    groups = dist.list_groups()
    assert "grp-a" in groups
    assert "grp-b" in groups
    assert len(groups) == 2
    print("  test_list_groups PASSED")


def test_callbacks():
    dist = AgentWorkDistributor()
    events = []
    assert dist.on_change("listener", lambda action, detail: events.append((action, detail))) is True
    # duplicate name returns False
    assert dist.on_change("listener", lambda a, d: None) is False

    dist.register_agents("grp-1", ["agent-a"])
    dist.distribute("grp-1", "task-1")

    assert len(events) == 2
    assert events[0][0] == "register_agents"
    assert events[1][0] == "distribute"
    assert events[1][1]["agent_id"] == "agent-a"

    # remove_callback
    assert dist.remove_callback("listener") is True
    assert dist.remove_callback("listener") is False
    print("  test_callbacks PASSED")


def test_stats():
    dist = AgentWorkDistributor()
    dist.register_agents("grp-1", ["agent-a", "agent-b"])
    dist.distribute("grp-1", "task-1")
    dist.distribute("grp-1", "task-2")

    stats = dist.get_stats()
    assert stats["total_distributors"] == 1
    assert stats["total_registered"] == 1
    assert stats["total_distributed"] == 2
    assert stats["total_assignments"] == 2
    assert stats["total_agents"] == 2
    assert stats["max_entries"] == 10000
    print("  test_stats PASSED")


def test_reset():
    dist = AgentWorkDistributor()
    dist.register_agents("grp-1", ["agent-a"])
    dist.distribute("grp-1", "task-1")
    dist.on_change("cb", lambda a, d: None)
    dist.reset()
    assert dist.get_distributor_count() == 0
    assert dist.get_assignment_count() == 0
    assert dist.list_groups() == []
    stats = dist.get_stats()
    assert stats["total_registered"] == 0
    assert stats["total_distributed"] == 0
    assert stats["callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_register_agents()
    test_distribute_round_robin()
    test_distribute_least_loaded()
    test_get_assignments()
    test_get_assignment_count()
    test_get_distributor()
    test_list_groups()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
