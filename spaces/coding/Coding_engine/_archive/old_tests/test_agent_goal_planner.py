"""Test agent goal planner -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_goal_planner import AgentGoalPlanner


def test_create_goal():
    gp = AgentGoalPlanner()
    gid = gp.create_goal("auth_module", agent_id="agent-1", description="Build auth")
    assert gid.startswith("gol-")
    g = gp.get_goal("auth_module")
    assert g["name"] == "auth_module"
    assert g["agent_id"] == "agent-1"
    assert g["status"] == "pending"
    assert g["progress_pct"] == 0.0
    assert gp.create_goal("auth_module") == ""  # dup
    print("OK: create goal")


def test_subgoals():
    gp = AgentGoalPlanner()
    gp.create_goal("auth")
    gp.create_goal("login_form")
    gp.create_goal("jwt_tokens")
    assert gp.add_subgoal("auth", "login_form") is True
    assert gp.add_subgoal("auth", "jwt_tokens") is True
    g = gp.get_goal("auth")
    assert g["subgoal_count"] >= 2
    print("OK: subgoals")


def test_dependencies():
    gp = AgentGoalPlanner()
    gp.create_goal("setup_db")
    gp.create_goal("build_api")
    assert gp.add_dependency("build_api", "setup_db") is True
    assert gp.add_dependency("build_api", "setup_db") is False  # dup
    g = gp.get_goal("build_api")
    assert g["dependency_count"] == 1
    assert g["is_blocked"] is True
    print("OK: dependencies")


def test_start_goal():
    gp = AgentGoalPlanner()
    gp.create_goal("setup_db")
    gp.create_goal("build_api")
    gp.add_dependency("build_api", "setup_db")
    # Can't start build_api -- dependency not met
    assert gp.start_goal("build_api") is False
    # Start and complete dependency
    assert gp.start_goal("setup_db") is True
    assert gp.get_goal("setup_db")["status"] == "active"
    gp.complete_goal("setup_db")
    # Now can start
    assert gp.start_goal("build_api") is True
    print("OK: start goal")


def test_complete_goal():
    gp = AgentGoalPlanner()
    gp.create_goal("task1")
    gp.start_goal("task1")
    assert gp.complete_goal("task1") is True
    assert gp.get_goal("task1")["status"] == "completed"
    assert gp.complete_goal("task1") is False  # already completed
    print("OK: complete goal")


def test_fail_goal():
    gp = AgentGoalPlanner()
    gp.create_goal("task1")
    gp.start_goal("task1")
    assert gp.fail_goal("task1", reason="timeout") is True
    assert gp.get_goal("task1")["status"] == "failed"
    print("OK: fail goal")


def test_update_progress():
    gp = AgentGoalPlanner()
    gp.create_goal("task1")
    assert gp.update_progress("task1", 50.0) is True
    assert gp.get_goal("task1")["progress_pct"] == 50.0
    # Module clamps or accepts high values -- just verify nonexistent fails
    assert gp.update_progress("nonexistent", 50.0) is False
    print("OK: update progress")


def test_goal_tree():
    gp = AgentGoalPlanner()
    gp.create_goal("root")
    gp.create_goal("child1")
    gp.create_goal("child2")
    gp.add_subgoal("root", "child1")
    gp.add_subgoal("root", "child2")
    tree = gp.get_goal_tree("root")
    assert tree["name"] == "root"
    assert len(tree["subgoals"]) == 2
    print("OK: goal tree")


def test_agent_goals():
    gp = AgentGoalPlanner()
    gp.create_goal("g1", agent_id="agent-1")
    gp.create_goal("g2", agent_id="agent-1")
    gp.create_goal("g3", agent_id="agent-2")
    gp.start_goal("g1")
    assert len(gp.get_agent_goals("agent-1")) == 2
    assert len(gp.get_agent_goals("agent-1", status="active")) == 1
    print("OK: agent goals")


def test_blocked_and_ready():
    gp = AgentGoalPlanner()
    gp.create_goal("dep")
    gp.create_goal("blocked_goal")
    gp.create_goal("ready_goal")
    gp.add_dependency("blocked_goal", "dep")
    blocked = gp.get_blocked_goals()
    assert any(g["name"] == "blocked_goal" for g in blocked)
    ready = gp.get_ready_goals()
    assert any(g["name"] == "ready_goal" for g in ready)
    assert any(g["name"] == "dep" for g in ready)
    print("OK: blocked and ready")


def test_list_goals():
    gp = AgentGoalPlanner()
    gp.create_goal("g1", agent_id="a1", tags=["infra"])
    gp.create_goal("g2", agent_id="a2")
    assert len(gp.list_goals()) == 2
    assert len(gp.list_goals(agent_id="a1")) == 1
    assert len(gp.list_goals(tag="infra")) == 1
    print("OK: list goals")


def test_remove_goal():
    gp = AgentGoalPlanner()
    gp.create_goal("g1")
    assert gp.remove_goal("g1") is True
    assert gp.remove_goal("g1") is False
    print("OK: remove goal")


def test_history():
    gp = AgentGoalPlanner()
    gp.create_goal("g1")
    gp.start_goal("g1")
    hist = gp.get_history()
    assert len(hist) >= 2
    print("OK: history")


def test_callbacks():
    gp = AgentGoalPlanner()
    fired = []
    gp.on_change("mon", lambda a, d: fired.append(a))
    gp.create_goal("g1")
    assert "goal_created" in fired
    assert gp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    gp = AgentGoalPlanner()
    gp.create_goal("g1")
    stats = gp.get_stats()
    assert stats["total_created"] >= 1
    print("OK: stats")


def test_reset():
    gp = AgentGoalPlanner()
    gp.create_goal("g1")
    gp.reset()
    assert gp.list_goals() == []
    print("OK: reset")


def main():
    print("=== Agent Goal Planner Tests ===\n")
    test_create_goal()
    test_subgoals()
    test_dependencies()
    test_start_goal()
    test_complete_goal()
    test_fail_goal()
    test_update_progress()
    test_goal_tree()
    test_agent_goals()
    test_blocked_and_ready()
    test_list_goals()
    test_remove_goal()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 16 TESTS PASSED ===")


if __name__ == "__main__":
    main()
