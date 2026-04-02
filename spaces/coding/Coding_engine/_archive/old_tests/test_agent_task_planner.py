"""Test agent task planner."""
import sys
sys.path.insert(0, ".")

from src.services.agent_task_planner import AgentTaskPlanner


def test_create_plan():
    """Create and retrieve plan."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("worker1", "build app", tags=["sprint1"])
    assert pid.startswith("pln-")

    p = tp.get_plan(pid)
    assert p is not None
    assert p["agent"] == "worker1"
    assert p["goal"] == "build app"
    assert p["status"] == "draft"

    assert tp.remove_plan(pid) is True
    assert tp.remove_plan(pid) is False
    print("OK: create plan")


def test_invalid_create():
    """Invalid creation rejected."""
    tp = AgentTaskPlanner()
    assert tp.create_plan("", "goal") == ""
    assert tp.create_plan("agent", "") == ""
    print("OK: invalid create")


def test_max_plans():
    """Max plans enforced."""
    tp = AgentTaskPlanner(max_plans=2)
    tp.create_plan("a", "g1")
    tp.create_plan("b", "g2")
    assert tp.create_plan("c", "g3") == ""
    print("OK: max plans")


def test_create_with_steps():
    """Create plan with initial steps."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[
        {"description": "setup"},
        {"description": "code", "depends_on": [0]},
        {"description": "test", "depends_on": [1]},
    ])
    p = tp.get_plan(pid)
    assert len(p["steps"]) == 3
    assert p["steps"][1]["depends_on"] == [0]
    print("OK: create with steps")


def test_add_step():
    """Add steps to draft plan."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build")

    idx = tp.add_step(pid, "setup")
    assert idx == 0
    idx = tp.add_step(pid, "code", depends_on=[0])
    assert idx == 1

    p = tp.get_plan(pid)
    assert len(p["steps"]) == 2
    print("OK: add step")


def test_add_step_not_draft():
    """Can't add steps to non-draft plan."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[{"description": "s1"}])
    tp.activate(pid)
    assert tp.add_step(pid, "s2") == -1
    print("OK: add step not draft")


def test_activate():
    """Activate a draft plan."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[{"description": "s1"}])

    assert tp.activate(pid) is True
    assert tp.get_plan(pid)["status"] == "active"
    assert tp.activate(pid) is False  # not draft anymore
    print("OK: activate")


def test_activate_no_steps():
    """Can't activate plan with no steps."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build")
    assert tp.activate(pid) is False
    print("OK: activate no steps")


def test_step_lifecycle():
    """Start and complete steps."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[
        {"description": "setup"},
        {"description": "code", "depends_on": [0]},
    ])
    tp.activate(pid)

    assert tp.start_step(pid, 0) is True
    assert tp.get_plan(pid)["steps"][0]["status"] == "running"

    assert tp.complete_step(pid, 0, result="done") is True
    assert tp.get_plan(pid)["steps"][0]["status"] == "completed"
    assert tp.get_plan(pid)["steps"][0]["result"] == "done"
    print("OK: step lifecycle")


def test_step_dependencies():
    """Steps respect dependencies."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[
        {"description": "setup"},
        {"description": "code", "depends_on": [0]},
    ])
    tp.activate(pid)

    # can't start step 1 before step 0 is completed
    assert tp.start_step(pid, 1) is False

    tp.start_step(pid, 0)
    tp.complete_step(pid, 0)

    assert tp.start_step(pid, 1) is True
    print("OK: step dependencies")


def test_fail_step():
    """Fail a step fails the plan."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[{"description": "s1"}])
    tp.activate(pid)
    tp.start_step(pid, 0)

    assert tp.fail_step(pid, 0, error="crash") is True
    p = tp.get_plan(pid)
    assert p["steps"][0]["status"] == "failed"
    assert p["status"] == "failed"
    print("OK: fail step")


def test_skip_step():
    """Skip a pending step."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[
        {"description": "s1"},
        {"description": "s2"},
    ])
    tp.activate(pid)

    assert tp.skip_step(pid, 1) is True
    assert tp.get_plan(pid)["steps"][1]["status"] == "skipped"
    print("OK: skip step")


def test_plan_auto_complete():
    """Plan auto-completes when all steps done."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[
        {"description": "s1"},
        {"description": "s2"},
    ])
    tp.activate(pid)

    tp.start_step(pid, 0)
    tp.complete_step(pid, 0)
    tp.start_step(pid, 1)
    tp.complete_step(pid, 1)

    assert tp.get_plan(pid)["status"] == "completed"
    print("OK: plan auto complete")


def test_cancel():
    """Cancel a plan."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[{"description": "s1"}])
    tp.activate(pid)

    assert tp.cancel(pid) is True
    assert tp.get_plan(pid)["status"] == "cancelled"
    assert tp.cancel(pid) is False  # already cancelled
    print("OK: cancel")


def test_get_progress():
    """Get plan progress."""
    tp = AgentTaskPlanner()
    pid = tp.create_plan("w1", "build", steps=[
        {"description": "s1"},
        {"description": "s2"},
        {"description": "s3"},
    ])
    tp.activate(pid)
    tp.start_step(pid, 0)
    tp.complete_step(pid, 0)

    prog = tp.get_progress(pid)
    assert prog["total_steps"] == 3
    assert prog["completed"] == 1
    assert prog["pending"] == 2
    assert abs(prog["pct"] - 33.33) < 1.0

    assert tp.get_progress("nonexistent") is None
    print("OK: get progress")


def test_list_plans():
    """List plans with filters."""
    tp = AgentTaskPlanner()
    tp.create_plan("w1", "build", tags=["ci"])
    pid2 = tp.create_plan("w2", "test", steps=[{"description": "s1"}])
    tp.activate(pid2)

    all_p = tp.list_plans()
    assert len(all_p) == 2

    by_agent = tp.list_plans(agent="w1")
    assert len(by_agent) == 1

    by_status = tp.list_plans(status="active")
    assert len(by_status) == 1

    by_tag = tp.list_plans(tag="ci")
    assert len(by_tag) == 1
    print("OK: list plans")


def test_get_plans_for_agent():
    """Get plans for specific agent."""
    tp = AgentTaskPlanner()
    tp.create_plan("w1", "g1")
    tp.create_plan("w1", "g2")
    tp.create_plan("w2", "g3")

    w1_plans = tp.get_plans_for_agent("w1")
    assert len(w1_plans) == 2
    assert tp.get_plans_for_agent("nonexistent") == []
    print("OK: get plans for agent")


def test_callback():
    """Callback fires on events."""
    tp = AgentTaskPlanner()
    fired = []
    tp.on_change("mon", lambda a, d: fired.append(a))

    pid = tp.create_plan("w1", "build", steps=[{"description": "s1"}])
    assert "plan_created" in fired

    tp.activate(pid)
    assert "plan_activated" in fired

    tp.start_step(pid, 0)
    assert "step_started" in fired

    tp.complete_step(pid, 0)
    assert "step_completed" in fired
    assert "plan_completed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    tp = AgentTaskPlanner()
    assert tp.on_change("mon", lambda a, d: None) is True
    assert tp.on_change("mon", lambda a, d: None) is False
    assert tp.remove_callback("mon") is True
    assert tp.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    tp = AgentTaskPlanner()
    pid1 = tp.create_plan("w1", "g1", steps=[{"description": "s1"}])
    tp.activate(pid1)
    tp.start_step(pid1, 0)
    tp.complete_step(pid1, 0)

    pid2 = tp.create_plan("w2", "g2", steps=[{"description": "s1"}])
    tp.activate(pid2)
    tp.start_step(pid2, 0)
    tp.fail_step(pid2, 0)

    stats = tp.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    tp = AgentTaskPlanner()
    tp.create_plan("w1", "build")

    tp.reset()
    assert tp.list_plans() == []
    stats = tp.get_stats()
    assert stats["current_plans"] == 0
    print("OK: reset")


def main():
    print("=== Agent Task Planner Tests ===\n")
    test_create_plan()
    test_invalid_create()
    test_max_plans()
    test_create_with_steps()
    test_add_step()
    test_add_step_not_draft()
    test_activate()
    test_activate_no_steps()
    test_step_lifecycle()
    test_step_dependencies()
    test_fail_step()
    test_skip_step()
    test_plan_auto_complete()
    test_cancel()
    test_get_progress()
    test_list_plans()
    test_get_plans_for_agent()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
