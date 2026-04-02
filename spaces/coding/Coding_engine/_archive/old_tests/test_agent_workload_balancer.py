"""Test agent workload balancer."""
import sys
sys.path.insert(0, ".")

from src.services.agent_workload_balancer import AgentWorkloadBalancer


def test_register_agent():
    """Register and remove agent."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker-1", capacity=10, tags=["python"])
    assert aid.startswith("wl-")

    a = wb.get_agent(aid)
    assert a is not None
    assert a["name"] == "worker-1"
    assert a["capacity"] == 10
    assert a["current_load"] == 0
    assert a["available_slots"] == 10
    assert a["status"] == "available"
    assert "python" in a["tags"]

    assert wb.remove_agent(aid) is True
    assert wb.remove_agent(aid) is False
    print("OK: register agent")


def test_invalid_register():
    """Invalid registration rejected."""
    wb = AgentWorkloadBalancer()
    assert wb.register_agent("") == ""
    assert wb.register_agent("x", capacity=0) == ""
    assert wb.register_agent("x", capacity=-1) == ""
    print("OK: invalid register")


def test_max_agents():
    """Max agents enforced."""
    wb = AgentWorkloadBalancer(max_agents=2)
    wb.register_agent("a")
    wb.register_agent("b")
    assert wb.register_agent("c") == ""
    print("OK: max agents")


def test_set_status():
    """Set agent status."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker")

    assert wb.set_status(aid, "busy") is True
    assert wb.get_agent(aid)["status"] == "busy"

    assert wb.set_status(aid, "offline") is True
    assert wb.set_status(aid, "draining") is True
    assert wb.set_status(aid, "available") is True

    assert wb.set_status(aid, "invalid") is False
    assert wb.set_status("nonexistent", "available") is False
    print("OK: set status")


def test_update_capacity():
    """Update agent capacity."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker", capacity=5)

    assert wb.update_capacity(aid, 20) is True
    assert wb.get_agent(aid)["capacity"] == 20

    assert wb.update_capacity(aid, 0) is False
    assert wb.update_capacity("nonexistent", 10) is False
    print("OK: update capacity")


def test_assign_task_least_loaded():
    """Assign task with least_loaded strategy."""
    wb = AgentWorkloadBalancer()
    a1 = wb.register_agent("heavy", capacity=10)
    a2 = wb.register_agent("light", capacity=10)

    # Load up heavy agent
    wb.assign_task("t1", strategy="least_loaded")
    wb.assign_task("t2", strategy="least_loaded")

    # Both should get one each initially (both at 0, then 1)
    report = wb.get_load_report()
    loads = {r["agent_id"]: r["current_load"] for r in report}
    assert loads[a1] + loads[a2] == 2
    print("OK: assign task least loaded")


def test_assign_task_round_robin():
    """Assign task with round_robin strategy."""
    wb = AgentWorkloadBalancer()
    a1 = wb.register_agent("a", capacity=10)
    a2 = wb.register_agent("b", capacity=10)

    ids = []
    for i in range(4):
        asid = wb.assign_task(f"task-{i}", strategy="round_robin")
        assert asid != ""
        info = wb.get_assignment(asid)
        ids.append(info["agent_id"])

    # Should alternate between agents
    assert len(set(ids)) == 2
    print("OK: assign task round robin")


def test_assign_task_weighted():
    """Assign task with weighted strategy (most available capacity)."""
    wb = AgentWorkloadBalancer()
    a1 = wb.register_agent("small", capacity=2)
    a2 = wb.register_agent("big", capacity=100)

    asid = wb.assign_task("heavy_task", strategy="weighted")
    info = wb.get_assignment(asid)
    assert info["agent_id"] == a2  # Big capacity preferred
    print("OK: assign task weighted")


def test_assign_task_random():
    """Assign task with random strategy."""
    wb = AgentWorkloadBalancer()
    wb.register_agent("a", capacity=10)
    wb.register_agent("b", capacity=10)

    asid = wb.assign_task("task", strategy="random")
    assert asid != ""
    print("OK: assign task random")


def test_assign_invalid():
    """Invalid assignment rejected."""
    wb = AgentWorkloadBalancer()
    assert wb.assign_task("") == ""
    assert wb.assign_task("x", strategy="invalid") == ""
    # No agents registered
    assert wb.assign_task("x") == ""
    print("OK: assign invalid")


def test_assign_with_tag():
    """Assign to agent with required tag."""
    wb = AgentWorkloadBalancer()
    a1 = wb.register_agent("py", capacity=10, tags=["python"])
    a2 = wb.register_agent("js", capacity=10, tags=["javascript"])

    asid = wb.assign_task("lint", required_tag="python")
    info = wb.get_assignment(asid)
    assert info["agent_id"] == a1

    asid2 = wb.assign_task("bundle", required_tag="javascript")
    info2 = wb.get_assignment(asid2)
    assert info2["agent_id"] == a2

    # No agent with tag
    assert wb.assign_task("x", required_tag="rust") == ""
    print("OK: assign with tag")


def test_complete_assignment():
    """Complete an assignment."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker", capacity=5)

    asid = wb.assign_task("job1")
    assert wb.get_agent(aid)["current_load"] == 1

    assert wb.complete_assignment(asid) is True
    assert wb.get_agent(aid)["current_load"] == 0
    assert wb.get_agent(aid)["total_completed"] == 1
    assert wb.get_assignment(asid)["status"] == "completed"

    # Can't complete again
    assert wb.complete_assignment(asid) is False
    assert wb.complete_assignment("nonexistent") is False
    print("OK: complete assignment")


def test_fail_assignment():
    """Fail an assignment."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker", capacity=5)

    asid = wb.assign_task("risky_job")
    assert wb.fail_assignment(asid) is True
    assert wb.get_agent(aid)["current_load"] == 0
    assert wb.get_agent(aid)["total_failed"] == 1
    assert wb.get_assignment(asid)["status"] == "failed"

    assert wb.fail_assignment(asid) is False
    print("OK: fail assignment")


def test_agent_assignments():
    """Get assignments for an agent."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker", capacity=10)

    as1 = wb.assign_task("job1")
    as2 = wb.assign_task("job2")
    wb.complete_assignment(as1)

    active = wb.get_agent_assignments(aid, active_only=True)
    assert len(active) == 1

    all_a = wb.get_agent_assignments(aid, active_only=False)
    assert len(all_a) == 2
    print("OK: agent assignments")


def test_capacity_limit():
    """Agent at capacity cannot receive tasks."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("tiny", capacity=1)

    as1 = wb.assign_task("first")
    assert as1 != ""

    # At capacity now
    as2 = wb.assign_task("second")
    assert as2 == ""  # No available agents
    print("OK: capacity limit")


def test_busy_agent_excluded():
    """Busy/offline/draining agents excluded from assignment."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker", capacity=10)

    wb.set_status(aid, "busy")
    assert wb.assign_task("task") == ""

    wb.set_status(aid, "offline")
    assert wb.assign_task("task") == ""

    wb.set_status(aid, "draining")
    assert wb.assign_task("task") == ""

    wb.set_status(aid, "available")
    assert wb.assign_task("task") != ""
    print("OK: busy agent excluded")


def test_remove_agent_with_load():
    """Cannot remove agent with active assignments."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker", capacity=10)
    asid = wb.assign_task("job")

    assert wb.remove_agent(aid) is False  # Has load

    wb.complete_assignment(asid)
    assert wb.remove_agent(aid) is True
    print("OK: remove agent with load")


def test_load_report():
    """Get load report."""
    wb = AgentWorkloadBalancer()
    a1 = wb.register_agent("heavy", capacity=2)
    a2 = wb.register_agent("light", capacity=10)

    wb.assign_task("t1")
    wb.assign_task("t2")

    report = wb.get_load_report()
    assert len(report) == 2
    # Sorted by utilization descending
    assert report[0]["utilization"] >= report[1]["utilization"]
    print("OK: load report")


def test_available_agents():
    """Get available agents."""
    wb = AgentWorkloadBalancer()
    a1 = wb.register_agent("a", capacity=1, tags=["py"])
    a2 = wb.register_agent("b", capacity=10)

    # Fill a1
    wb.assign_task("t1")
    wb.assign_task("t2")  # Goes to a2 since a1 might be full

    avail = wb.get_available_agents()
    # At least one should be available
    assert len(avail) >= 1

    # Filter by tag
    avail_py = wb.get_available_agents(required_tag="py")
    for a in avail_py:
        assert a["agent_id"] == a1
    print("OK: available agents")


def test_overloaded_agents():
    """Get overloaded agents."""
    wb = AgentWorkloadBalancer()
    a1 = wb.register_agent("worker", capacity=2)

    wb.assign_task("t1")
    wb.assign_task("t2")

    overloaded = wb.get_overloaded_agents(threshold=0.9)
    assert len(overloaded) == 1
    assert overloaded[0]["agent_id"] == a1

    empty = wb.get_overloaded_agents(threshold=1.1)
    assert len(empty) == 0
    print("OK: overloaded agents")


def test_list_agents():
    """List agents with filters."""
    wb = AgentWorkloadBalancer()
    wb.register_agent("a", tags=["python"])
    a2 = wb.register_agent("b")
    wb.set_status(a2, "offline")

    all_a = wb.list_agents()
    assert len(all_a) == 2

    by_status = wb.list_agents(status="offline")
    assert len(by_status) == 1

    by_tag = wb.list_agents(tag="python")
    assert len(by_tag) == 1
    print("OK: list agents")


def test_callback_on_assign():
    """Callback fires on assignment."""
    wb = AgentWorkloadBalancer()
    fired = []
    wb.on_change("mon", lambda a, d: fired.append(a))

    wb.register_agent("worker", capacity=10)
    wb.assign_task("job")
    assert "task_assigned" in fired
    print("OK: callback on assign")


def test_callbacks():
    """Callback registration."""
    wb = AgentWorkloadBalancer()
    assert wb.on_change("mon", lambda a, d: None) is True
    assert wb.on_change("mon", lambda a, d: None) is False
    assert wb.remove_callback("mon") is True
    assert wb.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    wb = AgentWorkloadBalancer()
    aid = wb.register_agent("worker", capacity=10)

    as1 = wb.assign_task("j1")
    as2 = wb.assign_task("j2")
    wb.complete_assignment(as1)
    wb.fail_assignment(as2)

    stats = wb.get_stats()
    assert stats["total_agents_registered"] == 1
    assert stats["total_assigned"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["current_agents"] == 1
    assert stats["available_agents"] == 1
    assert stats["active_assignments"] == 0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    wb = AgentWorkloadBalancer()
    wb.register_agent("worker")

    wb.reset()
    assert wb.list_agents() == []
    stats = wb.get_stats()
    assert stats["current_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Workload Balancer Tests ===\n")
    test_register_agent()
    test_invalid_register()
    test_max_agents()
    test_set_status()
    test_update_capacity()
    test_assign_task_least_loaded()
    test_assign_task_round_robin()
    test_assign_task_weighted()
    test_assign_task_random()
    test_assign_invalid()
    test_assign_with_tag()
    test_complete_assignment()
    test_fail_assignment()
    test_agent_assignments()
    test_capacity_limit()
    test_busy_agent_excluded()
    test_remove_agent_with_load()
    test_load_report()
    test_available_agents()
    test_overloaded_agents()
    test_list_agents()
    test_callback_on_assign()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 25 TESTS PASSED ===")


if __name__ == "__main__":
    main()
