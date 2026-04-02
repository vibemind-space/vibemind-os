"""Test agent goal tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_goal_tracker import AgentGoalTracker


def test_create_goal():
    gt = AgentGoalTracker()
    gid = gt.create_goal("agent-1", "complete deployment", priority=2)
    assert len(gid) > 0
    assert gid.startswith("agt-")
    print("OK: create goal")


def test_get_goal():
    gt = AgentGoalTracker()
    gid = gt.create_goal("agent-1", "complete deployment", priority=2)
    goal = gt.get_goal(gid)
    assert goal is not None
    assert goal["agent_id"] == "agent-1"
    assert goal["description"] == "complete deployment"
    assert goal["priority"] == 2
    assert goal["status"] == "active"
    assert gt.get_goal("nonexistent") is None
    print("OK: get goal")


def test_complete_goal():
    gt = AgentGoalTracker()
    gid = gt.create_goal("agent-1", "complete deployment")
    assert gt.complete_goal(gid) is True
    goal = gt.get_goal(gid)
    assert goal["status"] == "completed"
    assert gt.complete_goal(gid) is False
    print("OK: complete goal")


def test_fail_goal():
    gt = AgentGoalTracker()
    gid = gt.create_goal("agent-1", "complete deployment")
    assert gt.fail_goal(gid, reason="timeout") is True
    goal = gt.get_goal(gid)
    assert goal["status"] == "failed"
    assert gt.fail_goal(gid) is False
    print("OK: fail goal")


def test_get_agent_goals():
    gt = AgentGoalTracker()
    gt.create_goal("agent-1", "goal 1")
    gt.create_goal("agent-1", "goal 2")
    gt.create_goal("agent-2", "goal 3")
    goals = gt.get_agent_goals("agent-1")
    assert len(goals) == 2
    print("OK: get agent goals")


def test_get_active_goals():
    gt = AgentGoalTracker()
    g1 = gt.create_goal("agent-1", "goal 1")
    gt.create_goal("agent-1", "goal 2")
    gt.complete_goal(g1)
    active = gt.get_active_goals("agent-1")
    assert len(active) == 1
    print("OK: get active goals")


def test_get_completion_rate():
    gt = AgentGoalTracker()
    g1 = gt.create_goal("agent-1", "goal 1")
    g2 = gt.create_goal("agent-1", "goal 2")
    gt.complete_goal(g1)
    gt.fail_goal(g2, reason="timeout")
    rate = gt.get_completion_rate("agent-1")
    assert rate == 0.5  # 1 completed out of 2 resolved
    g3 = gt.create_goal("agent-1", "goal 3")
    gt.complete_goal(g3)
    assert gt.get_completion_rate("agent-1") > 0.5  # 2 completed out of 3 resolved
    print("OK: get completion rate")


def test_remove_goal():
    gt = AgentGoalTracker()
    gid = gt.create_goal("agent-1", "goal 1")
    assert gt.remove_goal(gid) is True
    assert gt.remove_goal(gid) is False
    print("OK: remove goal")


def test_list_agents():
    gt = AgentGoalTracker()
    gt.create_goal("agent-1", "goal 1")
    gt.create_goal("agent-2", "goal 2")
    agents = gt.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    gt = AgentGoalTracker()
    fired = []
    gt.on_change("mon", lambda a, d: fired.append(a))
    gt.create_goal("agent-1", "goal 1")
    assert len(fired) >= 1
    assert gt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    gt = AgentGoalTracker()
    gt.create_goal("agent-1", "goal 1")
    stats = gt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    gt = AgentGoalTracker()
    gt.create_goal("agent-1", "goal 1")
    gt.reset()
    assert gt.get_goal_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Goal Tracker Tests ===\n")
    test_create_goal()
    test_get_goal()
    test_complete_goal()
    test_fail_goal()
    test_get_agent_goals()
    test_get_active_goals()
    test_get_completion_rate()
    test_remove_goal()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
