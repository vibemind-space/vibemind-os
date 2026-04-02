"""Test pipeline execution planner."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_execution_planner import PipelineExecutionPlanner


def test_create_plan():
    """Create and remove plan."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("deploy_v2", description="Deploy version 2",
                         strategy="sequential", tags=["prod"])
    assert pid.startswith("plan-")

    p = ep.get_plan(pid)
    assert p is not None
    assert p["name"] == "deploy_v2"
    assert p["strategy"] == "sequential"
    assert p["status"] == "draft"
    assert "prod" in p["tags"]

    assert ep.remove_plan(pid) is True
    assert ep.remove_plan(pid) is False
    print("OK: create plan")


def test_invalid_plan():
    """Invalid plan rejected."""
    ep = PipelineExecutionPlanner()
    assert ep.create_plan("") == ""
    assert ep.create_plan("x", strategy="invalid") == ""
    print("OK: invalid plan")


def test_max_plans():
    """Max plans enforced."""
    ep = PipelineExecutionPlanner(max_plans=2)
    ep.create_plan("a")
    ep.create_plan("b")
    assert ep.create_plan("c") == ""
    print("OK: max plans")


def test_cancel_plan():
    """Cancel a plan."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    assert ep.cancel_plan(pid) is True
    assert ep.get_plan(pid)["status"] == "cancelled"
    assert ep.cancel_plan(pid) is False
    print("OK: cancel plan")


def test_add_step():
    """Add and remove steps."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    sid = ep.add_step(pid, "compile", action="make build",
                      priority=5, estimated_duration=10.0, tags=["build"])
    assert sid.startswith("step-")

    s = ep.get_step(pid, sid)
    assert s is not None
    assert s["name"] == "compile"
    assert s["action"] == "make build"
    assert s["priority"] == 5
    assert s["status"] == "pending"

    assert ep.remove_step(pid, sid) is True
    assert ep.remove_step(pid, sid) is False
    print("OK: add step")


def test_invalid_step():
    """Invalid step rejected."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    assert ep.add_step(pid, "") == ""
    assert ep.add_step("nonexistent", "x") == ""
    print("OK: invalid step")


def test_max_steps():
    """Max steps per plan enforced."""
    ep = PipelineExecutionPlanner(max_steps_per_plan=2)
    pid = ep.create_plan("test")
    ep.add_step(pid, "a")
    ep.add_step(pid, "b")
    assert ep.add_step(pid, "c") == ""
    print("OK: max steps")


def test_assign_step():
    """Assign step to agent."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    sid = ep.add_step(pid, "build")

    assert ep.assign_step(pid, sid, "agent-1") is True
    assert ep.get_step(pid, sid)["assigned_agent"] == "agent-1"

    assert ep.assign_step(pid, sid, "") is False
    print("OK: assign step")


def test_finalize_plan():
    """Finalize a plan."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    ep.add_step(pid, "build")

    assert ep.finalize_plan(pid) is True
    assert ep.get_plan(pid)["status"] == "ready"
    assert ep.finalize_plan(pid) is False  # Already finalized
    print("OK: finalize plan")


def test_finalize_empty_plan():
    """Can't finalize empty plan."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    assert ep.finalize_plan(pid) is False
    print("OK: finalize empty plan")


def test_cant_add_step_after_finalize():
    """Can't add steps to finalized plan."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    ep.add_step(pid, "a")
    ep.finalize_plan(pid)
    assert ep.add_step(pid, "b") == ""
    print("OK: cant add step after finalize")


def test_start_plan():
    """Start plan execution."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "first")
    s2 = ep.add_step(pid, "second", dependencies=[s1])
    ep.finalize_plan(pid)

    assert ep.start_plan(pid) is True
    assert ep.get_plan(pid)["status"] == "running"
    assert ep.get_step(pid, s1)["status"] == "ready"
    assert ep.get_step(pid, s2)["status"] == "pending"

    assert ep.start_plan(pid) is False
    print("OK: start plan")


def test_execution_flow():
    """Full execution flow."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("deploy")
    s1 = ep.add_step(pid, "build")
    s2 = ep.add_step(pid, "test", dependencies=[s1])
    s3 = ep.add_step(pid, "deploy", dependencies=[s2])
    ep.finalize_plan(pid)
    ep.start_plan(pid)

    # Execute s1
    assert ep.start_step(pid, s1) is True
    assert ep.complete_step(pid, s1, result="built") is True
    assert ep.get_step(pid, s2)["status"] == "ready"

    # Execute s2
    ep.start_step(pid, s2)
    ep.complete_step(pid, s2)
    assert ep.get_step(pid, s3)["status"] == "ready"

    # Execute s3
    ep.start_step(pid, s3)
    ep.complete_step(pid, s3)

    assert ep.get_plan(pid)["status"] == "completed"
    print("OK: execution flow")


def test_fail_step():
    """Failing a step fails the plan."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "risky")
    ep.finalize_plan(pid)
    ep.start_plan(pid)
    ep.start_step(pid, s1)

    assert ep.fail_step(pid, s1, reason="crash") is True
    assert ep.get_step(pid, s1)["status"] == "failed"
    assert ep.get_plan(pid)["status"] == "failed"
    print("OK: fail step")


def test_skip_step():
    """Skip a step."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "optional")
    s2 = ep.add_step(pid, "next", dependencies=[s1])
    ep.finalize_plan(pid)
    ep.start_plan(pid)

    assert ep.skip_step(pid, s1) is True
    assert ep.get_step(pid, s1)["status"] == "skipped"
    assert ep.get_step(pid, s2)["status"] == "ready"
    print("OK: skip step")


def test_ready_steps():
    """Get ready steps sorted by priority."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "low", priority=1)
    s2 = ep.add_step(pid, "high", priority=10)
    ep.finalize_plan(pid)
    ep.start_plan(pid)

    ready = ep.get_ready_steps(pid)
    assert len(ready) == 2
    assert ready[0]["step_id"] == s2  # High priority first
    print("OK: ready steps")


def test_plan_progress():
    """Get plan progress."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "a")
    s2 = ep.add_step(pid, "b")
    ep.finalize_plan(pid)
    ep.start_plan(pid)

    ep.start_step(pid, s1)
    ep.complete_step(pid, s1)

    prog = ep.get_plan_progress(pid)
    assert prog["total"] == 2
    assert prog["completed"] == 1
    assert prog["ready"] == 1
    assert prog["percent"] == 50.0
    print("OK: plan progress")


def test_estimated_duration():
    """Get estimated duration."""
    ep = PipelineExecutionPlanner()
    # Sequential: sum of all
    pid_seq = ep.create_plan("seq", strategy="sequential")
    ep.add_step(pid_seq, "a", estimated_duration=10.0)
    ep.add_step(pid_seq, "b", estimated_duration=20.0)
    assert ep.get_estimated_duration(pid_seq) == 30.0

    # Parallel: max
    pid_par = ep.create_plan("par", strategy="parallel")
    ep.add_step(pid_par, "a", estimated_duration=10.0)
    ep.add_step(pid_par, "b", estimated_duration=20.0)
    assert ep.get_estimated_duration(pid_par) == 20.0
    print("OK: estimated duration")


def test_list_plans():
    """List plans with filters."""
    ep = PipelineExecutionPlanner()
    ep.create_plan("a", tags=["prod"])
    pid2 = ep.create_plan("b")
    ep.add_step(pid2, "x")
    ep.finalize_plan(pid2)

    all_p = ep.list_plans()
    assert len(all_p) == 2

    by_status = ep.list_plans(status="draft")
    assert len(by_status) == 1

    by_tag = ep.list_plans(tag="prod")
    assert len(by_tag) == 1
    print("OK: list plans")


def test_plan_steps():
    """Get steps in order."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "first")
    s2 = ep.add_step(pid, "second")

    steps = ep.get_plan_steps(pid)
    assert len(steps) == 2
    assert steps[0]["step_id"] == s1
    assert steps[1]["step_id"] == s2
    print("OK: plan steps")


def test_cant_remove_running_plan():
    """Can't remove running plan."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    ep.add_step(pid, "x")
    ep.finalize_plan(pid)
    ep.start_plan(pid)

    assert ep.remove_plan(pid) is False
    print("OK: cant remove running plan")


def test_plan_created_callback():
    """Callback fires on plan creation."""
    ep = PipelineExecutionPlanner()
    fired = []
    ep.on_change("mon", lambda a, d: fired.append(a))

    ep.create_plan("test")
    assert "plan_created" in fired
    print("OK: plan created callback")


def test_plan_completed_callback():
    """Callback fires on plan completion."""
    ep = PipelineExecutionPlanner()
    fired = []
    ep.on_change("mon", lambda a, d: fired.append(a))

    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "only")
    ep.finalize_plan(pid)
    ep.start_plan(pid)
    ep.start_step(pid, s1)
    ep.complete_step(pid, s1)

    assert "plan_completed" in fired
    print("OK: plan completed callback")


def test_callbacks():
    """Callback registration."""
    ep = PipelineExecutionPlanner()
    assert ep.on_change("mon", lambda a, d: None) is True
    assert ep.on_change("mon", lambda a, d: None) is False
    assert ep.remove_callback("mon") is True
    assert ep.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ep = PipelineExecutionPlanner()
    pid = ep.create_plan("test")
    s1 = ep.add_step(pid, "a")
    s2 = ep.add_step(pid, "b")
    ep.finalize_plan(pid)
    ep.start_plan(pid)
    ep.start_step(pid, s1)
    ep.complete_step(pid, s1)
    ep.start_step(pid, s2)
    ep.fail_step(pid, s2)

    stats = ep.get_stats()
    assert stats["total_plans_created"] == 1
    assert stats["total_steps_added"] == 2
    assert stats["total_steps_completed"] == 1
    assert stats["total_steps_failed"] == 1
    assert stats["total_plans_failed"] == 1
    assert stats["current_plans"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ep = PipelineExecutionPlanner()
    ep.create_plan("test")

    ep.reset()
    assert ep.list_plans() == []
    stats = ep.get_stats()
    assert stats["current_plans"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Execution Planner Tests ===\n")
    test_create_plan()
    test_invalid_plan()
    test_max_plans()
    test_cancel_plan()
    test_add_step()
    test_invalid_step()
    test_max_steps()
    test_assign_step()
    test_finalize_plan()
    test_finalize_empty_plan()
    test_cant_add_step_after_finalize()
    test_start_plan()
    test_execution_flow()
    test_fail_step()
    test_skip_step()
    test_ready_steps()
    test_plan_progress()
    test_estimated_duration()
    test_list_plans()
    test_plan_steps()
    test_cant_remove_running_plan()
    test_plan_created_callback()
    test_plan_completed_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 26 TESTS PASSED ===")


if __name__ == "__main__":
    main()
