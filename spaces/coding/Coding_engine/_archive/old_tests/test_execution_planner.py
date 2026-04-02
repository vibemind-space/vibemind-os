"""Test execution planner."""
import sys
sys.path.insert(0, ".")

from src.services.execution_planner import ExecutionPlanner


def test_register_agent():
    """Register and unregister agents."""
    ep = ExecutionPlanner()
    assert ep.register_agent("Builder", capacity=3, capabilities={"build", "compile"}) is True
    assert ep.register_agent("Builder") is False  # Duplicate

    agents = ep.list_agents()
    assert len(agents) == 1
    assert agents[0]["agent_name"] == "Builder"
    assert agents[0]["capacity"] == 3
    assert agents[0]["available"] is True

    assert ep.unregister_agent("Builder") is True
    assert ep.unregister_agent("Builder") is False
    print("OK: register agent")


def test_create_plan():
    """Create a plan."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Deploy v2", constraints={"max_time": 300},
                          metadata={"env": "prod"})
    assert pid.startswith("plan-")

    plan = ep.get_plan(pid)
    assert plan is not None
    assert plan["name"] == "Deploy v2"
    assert plan["version"] == 1
    assert plan["status"] == "draft"
    assert plan["constraints"]["max_time"] == 300
    print("OK: create plan")


def test_plan_versioning():
    """Same name bumps version."""
    ep = ExecutionPlanner()
    p1 = ep.create_plan("Deploy")
    p2 = ep.create_plan("Deploy")

    assert ep.get_plan(p1)["version"] == 1
    assert ep.get_plan(p2)["version"] == 2
    print("OK: plan versioning")


def test_list_plans():
    """List plans with filters."""
    ep = ExecutionPlanner()
    p1 = ep.create_plan("Alpha")
    p2 = ep.create_plan("Beta")
    ep.start_plan(p1)

    all_plans = ep.list_plans()
    assert len(all_plans) == 2

    executing = ep.list_plans(status="executing")
    assert len(executing) == 1
    assert executing[0]["plan_id"] == p1

    by_name = ep.list_plans(name="Beta")
    assert len(by_name) == 1

    limited = ep.list_plans(limit=1)
    assert len(limited) == 1
    print("OK: list plans")


def test_delete_plan():
    """Delete a plan."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Temp")
    assert ep.delete_plan(pid) is True
    assert ep.get_plan(pid) is None
    assert ep.delete_plan(pid) is False
    print("OK: delete plan")


def test_add_task():
    """Add tasks to a plan."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")

    t1 = ep.add_task(pid, "Compile", duration_estimate=10.0, tags={"build"})
    assert t1 is not None and t1.startswith("ptask-")

    t2 = ep.add_task(pid, "Test", duration_estimate=5.0, dependencies={t1})
    assert t2 is not None

    task = ep.get_task(pid, t2)
    assert task["name"] == "Test"
    assert t1 in task["dependencies"]

    # Can't add to nonexistent plan
    assert ep.add_task("fake", "X") is None
    print("OK: add task")


def test_remove_task():
    """Remove a task and clean up dependencies."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")
    t1 = ep.add_task(pid, "A")
    t2 = ep.add_task(pid, "B", dependencies={t1})

    assert ep.remove_task(pid, t1) is True
    # t2's dependency on t1 should be cleaned
    task_b = ep.get_task(pid, t2)
    assert t1 not in task_b["dependencies"]

    assert ep.remove_task(pid, "fake") is False
    print("OK: remove task")


def test_validate_plan():
    """Validate plan completeness."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")

    # Empty plan
    result = ep.validate_plan(pid)
    assert result["valid"] is False
    assert any("no tasks" in e for e in result["errors"])

    # Valid plan with unassigned warning
    t1 = ep.add_task(pid, "A")
    t2 = ep.add_task(pid, "B", dependencies={t1})
    result = ep.validate_plan(pid)
    assert result["valid"] is True
    assert len(result["warnings"]) > 0  # Unassigned warning

    # Missing dependency
    pid2 = ep.create_plan("Bad")
    ep.add_task(pid2, "Broken", dependencies={"nonexistent"})
    result = ep.validate_plan(pid2)
    assert result["valid"] is False
    assert any("missing" in e.lower() for e in result["errors"])

    # Nonexistent plan
    result = ep.validate_plan("fake")
    assert result["valid"] is False
    print("OK: validate plan")


def test_validate_cycle():
    """Detect circular dependencies."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Cycle")
    t1 = ep.add_task(pid, "A")
    t2 = ep.add_task(pid, "B", dependencies={t1})
    # Manually create cycle
    ep._plans[pid].tasks[t1].dependencies.add(t2)

    result = ep.validate_plan(pid)
    assert result["valid"] is False
    assert any("circular" in e.lower() for e in result["errors"])
    print("OK: validate cycle")


def test_compute_schedule():
    """Compute parallel execution groups."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")
    t1 = ep.add_task(pid, "Compile")
    t2 = ep.add_task(pid, "Lint")
    t3 = ep.add_task(pid, "Test", dependencies={t1, t2})
    t4 = ep.add_task(pid, "Deploy", dependencies={t3})

    layers = ep.compute_schedule(pid)
    assert layers is not None
    assert len(layers) == 3
    # Layer 0: Compile + Lint (no deps)
    assert len(layers[0]) == 2
    # Layer 1: Test
    assert len(layers[1]) == 1
    assert layers[1][0]["name"] == "Test"
    # Layer 2: Deploy
    assert len(layers[2]) == 1
    assert layers[2][0]["name"] == "Deploy"

    # Cycle returns None
    ep._plans[pid].tasks[t1].dependencies.add(t4)
    assert ep.compute_schedule(pid) is None
    print("OK: compute schedule")


def test_estimate_duration():
    """Estimate plan duration via critical path."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")
    t1 = ep.add_task(pid, "Compile", duration_estimate=10.0)
    t2 = ep.add_task(pid, "Lint", duration_estimate=5.0)
    t3 = ep.add_task(pid, "Test", duration_estimate=8.0, dependencies={t1, t2})

    est = ep.estimate_duration(pid)
    assert est is not None
    # Layer 0: max(10, 5) = 10, Layer 1: 8 => total = 18
    assert est["estimated_total_seconds"] == 18.0
    assert est["num_layers"] == 2
    assert est["total_tasks"] == 3

    assert ep.estimate_duration("fake") is None
    print("OK: estimate duration")


def test_auto_assign():
    """Auto-assign tasks to agents."""
    ep = ExecutionPlanner()
    ep.register_agent("Builder", capacity=2, capabilities={"build"})
    ep.register_agent("Tester", capacity=1, capabilities={"test"})

    pid = ep.create_plan("Build")
    ep.add_task(pid, "Compile", tags={"build"})
    ep.add_task(pid, "Unit tests", tags={"test"})
    ep.add_task(pid, "Generic work")  # No tags, matches any

    count = ep.auto_assign(pid)
    assert count == 3

    assert ep.auto_assign("fake") == 0
    print("OK: auto assign")


def test_start_plan():
    """Start plan execution."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")
    ep.add_task(pid, "A")

    assert ep.start_plan(pid) is True
    assert ep.get_plan(pid)["status"] == "executing"
    assert ep.start_plan(pid) is False  # Already executing
    print("OK: start plan")


def test_complete_task():
    """Complete tasks and auto-complete plan."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")
    t1 = ep.add_task(pid, "A")
    t2 = ep.add_task(pid, "B")
    ep.start_plan(pid)

    assert ep.complete_task(pid, t1) is True
    assert ep.complete_task(pid, t1) is False  # Already completed
    assert ep.get_plan(pid)["status"] == "executing"

    assert ep.complete_task(pid, t2) is True
    assert ep.get_plan(pid)["status"] == "completed"
    print("OK: complete task")


def test_fail_task():
    """Fail a task and mark plan as failed."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")
    t1 = ep.add_task(pid, "A")
    ep.start_plan(pid)

    assert ep.fail_task(pid, t1, error="OOM") is True
    assert ep.get_plan(pid)["status"] == "failed"

    task = ep.get_task(pid, t1)
    assert task["status"] == "failed"
    assert task["metadata"]["error"] == "OOM"
    print("OK: fail task")


def test_get_ready_tasks():
    """Get tasks whose dependencies are met."""
    ep = ExecutionPlanner()
    pid = ep.create_plan("Build")
    t1 = ep.add_task(pid, "Compile")
    t2 = ep.add_task(pid, "Lint")
    t3 = ep.add_task(pid, "Test", dependencies={t1, t2})
    ep.start_plan(pid)

    ready = ep.get_ready_tasks(pid)
    assert len(ready) == 2  # Compile + Lint
    names = {r["name"] for r in ready}
    assert names == {"Compile", "Lint"}

    # Complete one dep
    ep.complete_task(pid, t1)
    ready = ep.get_ready_tasks(pid)
    assert len(ready) == 1
    assert ready[0]["name"] == "Lint"

    # Complete both deps
    ep.complete_task(pid, t2)
    ready = ep.get_ready_tasks(pid)
    assert len(ready) == 1
    assert ready[0]["name"] == "Test"

    assert ep.get_ready_tasks("fake") == []
    print("OK: get ready tasks")


def test_prune_plans():
    """Old completed plans are pruned."""
    ep = ExecutionPlanner(max_plans=3)
    for i in range(6):
        pid = ep.create_plan(f"Plan-{i}")
        t = ep.add_task(pid, "task")
        ep.start_plan(pid)
        ep.complete_task(pid, t)

    assert len(ep._plans) <= 3
    print("OK: prune plans")


def test_stats():
    """Stats are accurate."""
    ep = ExecutionPlanner()
    ep.register_agent("Builder")

    pid = ep.create_plan("Build")
    ep.add_task(pid, "A")
    ep.add_task(pid, "B")

    stats = ep.get_stats()
    assert stats["total_plans_created"] == 1
    assert stats["total_tasks_planned"] == 2
    assert stats["total_plans"] == 1
    assert stats["total_agents"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ep = ExecutionPlanner()
    ep.register_agent("Builder")
    pid = ep.create_plan("Build")
    ep.add_task(pid, "A")

    ep.reset()
    assert ep.list_plans() == []
    assert ep.list_agents() == []
    stats = ep.get_stats()
    assert stats["total_plans"] == 0
    assert stats["total_agents"] == 0
    print("OK: reset")


def main():
    print("=== Execution Planner Tests ===\n")
    test_register_agent()
    test_create_plan()
    test_plan_versioning()
    test_list_plans()
    test_delete_plan()
    test_add_task()
    test_remove_task()
    test_validate_plan()
    test_validate_cycle()
    test_compute_schedule()
    test_estimate_duration()
    test_auto_assign()
    test_start_plan()
    test_complete_task()
    test_fail_task()
    test_get_ready_tasks()
    test_prune_plans()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
