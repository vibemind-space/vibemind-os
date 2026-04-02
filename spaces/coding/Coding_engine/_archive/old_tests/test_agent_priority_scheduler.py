"""Test agent priority scheduler."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_priority_scheduler import AgentPriorityScheduler


def test_schedule_task():
    """Schedule and retrieve a task."""
    ps = AgentPriorityScheduler()
    tid = ps.schedule("build_app", priority=7, agent="agent-1", tags=["build"])
    assert tid.startswith("sched-")

    t = ps.get_task(tid)
    assert t is not None
    assert t["name"] == "build_app"
    assert t["priority"] == 7
    assert t["agent"] == "agent-1"
    assert t["status"] == "pending"
    assert "build" in t["tags"]

    assert ps.remove_task(tid) is True
    assert ps.remove_task(tid) is False
    print("OK: schedule task")


def test_invalid_schedule():
    """Invalid scheduling rejected."""
    ps = AgentPriorityScheduler()
    assert ps.schedule("") == ""
    assert ps.schedule("x", priority=-1) == ""
    assert ps.schedule("x", priority=11) == ""
    assert ps.schedule("x", dependencies=["nonexistent"]) == ""
    print("OK: invalid schedule")


def test_max_tasks():
    """Max tasks enforced."""
    ps = AgentPriorityScheduler(max_tasks=2)
    ps.schedule("a")
    ps.schedule("b")
    assert ps.schedule("c") == ""
    print("OK: max tasks")


def test_start_complete():
    """Start and complete a task."""
    ps = AgentPriorityScheduler()
    tid = ps.schedule("task1")

    assert ps.start_task(tid, agent="agent-1") is True
    assert ps.get_task(tid)["status"] == "running"
    assert ps.get_task(tid)["agent"] == "agent-1"

    assert ps.start_task(tid) is False  # Already running

    assert ps.complete_task(tid, result="success") is True
    assert ps.get_task(tid)["status"] == "completed"
    assert ps.get_task(tid)["result"] == "success"
    assert ps.complete_task(tid) is False  # Already completed
    print("OK: start complete")


def test_fail_task():
    """Fail a running task."""
    ps = AgentPriorityScheduler()
    tid = ps.schedule("task1")
    ps.start_task(tid)

    assert ps.fail_task(tid, "error occurred") is True
    assert ps.get_task(tid)["status"] == "failed"
    assert ps.fail_task(tid) is False
    print("OK: fail task")


def test_cancel_task():
    """Cancel a pending task."""
    ps = AgentPriorityScheduler()
    tid = ps.schedule("task1")

    assert ps.cancel_task(tid) is True
    assert ps.get_task(tid)["status"] == "cancelled"
    assert ps.cancel_task(tid) is False
    print("OK: cancel task")


def test_set_priority():
    """Change task priority."""
    ps = AgentPriorityScheduler()
    tid = ps.schedule("task1", priority=3)

    assert ps.set_priority(tid, 8) is True
    assert ps.get_task(tid)["priority"] == 8
    assert ps.set_priority(tid, -1) is False
    assert ps.set_priority(tid, 11) is False
    print("OK: set priority")


def test_max_running():
    """Max running tasks enforced."""
    ps = AgentPriorityScheduler(max_running=1)
    t1 = ps.schedule("a")
    t2 = ps.schedule("b")

    assert ps.start_task(t1) is True
    assert ps.start_task(t2) is False  # Max running reached
    print("OK: max running")


def test_priority_ordering():
    """Higher priority tasks come first in queue."""
    ps = AgentPriorityScheduler()
    ps.schedule("low", priority=1)
    ps.schedule("high", priority=9)
    ps.schedule("medium", priority=5)

    q = ps.get_queue()
    assert q[0]["name"] == "high"
    assert q[1]["name"] == "medium"
    assert q[2]["name"] == "low"
    print("OK: priority ordering")


def test_get_next():
    """Get highest priority pending task."""
    ps = AgentPriorityScheduler()
    ps.schedule("low", priority=1)
    ps.schedule("high", priority=9, agent="agent-1")
    ps.schedule("medium", priority=5)

    nxt = ps.get_next()
    assert nxt["name"] == "high"

    # Filter by agent
    nxt2 = ps.get_next(agent="agent-1")
    assert nxt2["name"] == "high"
    print("OK: get next")


def test_queue_with_tag():
    """Queue filtered by tag."""
    ps = AgentPriorityScheduler()
    ps.schedule("a", tags=["build"])
    ps.schedule("b", tags=["test"])
    ps.schedule("c", tags=["build"])

    q = ps.get_queue(tag="build")
    assert len(q) == 2
    print("OK: queue with tag")


def test_list_tasks():
    """List tasks with filters."""
    ps = AgentPriorityScheduler()
    t1 = ps.schedule("a", agent="agent-1", tags=["build"])
    t2 = ps.schedule("b", agent="agent-2")
    ps.start_task(t2)

    by_status = ps.list_tasks(status="pending")
    assert len(by_status) == 1

    by_agent = ps.list_tasks(agent="agent-1")
    assert len(by_agent) == 1

    by_tag = ps.list_tasks(tag="build")
    assert len(by_tag) == 1
    print("OK: list tasks")


def test_running_tasks():
    """Get running tasks."""
    ps = AgentPriorityScheduler()
    t1 = ps.schedule("a")
    t2 = ps.schedule("b")
    ps.start_task(t1)

    running = ps.get_running_tasks()
    assert len(running) == 1
    assert running[0]["task_id"] == t1
    print("OK: running tasks")


def test_dependencies():
    """Task blocks on unfinished dependencies."""
    ps = AgentPriorityScheduler()
    t1 = ps.schedule("prereq")
    t2 = ps.schedule("dependent", dependencies=[t1])

    assert ps.get_task(t2)["status"] == "blocked"

    # Complete prerequisite
    ps.start_task(t1)
    ps.complete_task(t1)

    # Dependent should now be pending
    assert ps.get_task(t2)["status"] == "pending"
    print("OK: dependencies")


def test_blocked_tasks():
    """Get blocked tasks."""
    ps = AgentPriorityScheduler()
    t1 = ps.schedule("prereq")
    t2 = ps.schedule("dependent", dependencies=[t1])

    blocked = ps.get_blocked_tasks()
    assert len(blocked) == 1
    assert blocked[0]["task_id"] == t2
    print("OK: blocked tasks")


def test_deadline_overdue():
    """Detect overdue tasks."""
    ps = AgentPriorityScheduler()
    ps.schedule("urgent", deadline=time.time() - 1)  # Already past

    overdue = ps.get_overdue_tasks()
    assert len(overdue) == 1
    print("OK: deadline overdue")


def test_agent_tasks():
    """Get agent task summary."""
    ps = AgentPriorityScheduler()
    t1 = ps.schedule("a", agent="agent-1")
    t2 = ps.schedule("b", agent="agent-1")
    ps.start_task(t2)

    summary = ps.get_agent_tasks("agent-1")
    assert summary["total"] == 2
    assert summary["by_status"]["pending"] == 1
    assert summary["by_status"]["running"] == 1

    assert ps.get_agent_tasks("nonexistent") == {}
    print("OK: agent tasks")


def test_priority_distribution():
    """Priority distribution."""
    ps = AgentPriorityScheduler()
    ps.schedule("a", priority=5)
    ps.schedule("b", priority=5)
    ps.schedule("c", priority=9)

    dist = ps.get_priority_distribution()
    assert dist[5] == 2
    assert dist[9] == 1
    print("OK: priority distribution")


def test_callbacks():
    """Callbacks fire on events."""
    ps = AgentPriorityScheduler()

    fired = []
    assert ps.on_change("mon", lambda a, d: fired.append(a)) is True
    assert ps.on_change("mon", lambda a, d: None) is False

    tid = ps.schedule("task1")
    assert "task_scheduled" in fired

    ps.start_task(tid)
    assert "task_started" in fired

    ps.complete_task(tid)
    assert "task_completed" in fired

    assert ps.remove_callback("mon") is True
    assert ps.remove_callback("mon") is False
    print("OK: callbacks")


def test_unblock_callback():
    """Unblock callback fires when dependency completed."""
    ps = AgentPriorityScheduler()

    fired = []
    ps.on_change("mon", lambda a, d: fired.append(a))

    t1 = ps.schedule("prereq")
    t2 = ps.schedule("dependent", dependencies=[t1])

    ps.start_task(t1)
    ps.complete_task(t1)
    assert "task_unblocked" in fired
    print("OK: unblock callback")


def test_stats():
    """Stats are accurate."""
    ps = AgentPriorityScheduler()
    t1 = ps.schedule("a")
    t2 = ps.schedule("b")
    t3 = ps.schedule("c")

    ps.start_task(t1)
    ps.complete_task(t1)
    ps.start_task(t2)
    ps.fail_task(t2)
    ps.cancel_task(t3)

    stats = ps.get_stats()
    assert stats["total_scheduled"] == 3
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_cancelled"] == 1
    assert stats["total_tasks"] == 3
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ps = AgentPriorityScheduler()
    ps.schedule("a")

    ps.reset()
    assert ps.list_tasks() == []
    stats = ps.get_stats()
    assert stats["total_tasks"] == 0
    print("OK: reset")


def main():
    print("=== Agent Priority Scheduler Tests ===\n")
    test_schedule_task()
    test_invalid_schedule()
    test_max_tasks()
    test_start_complete()
    test_fail_task()
    test_cancel_task()
    test_set_priority()
    test_max_running()
    test_priority_ordering()
    test_get_next()
    test_queue_with_tag()
    test_list_tasks()
    test_running_tasks()
    test_dependencies()
    test_blocked_tasks()
    test_deadline_overdue()
    test_agent_tasks()
    test_priority_distribution()
    test_callbacks()
    test_unblock_callback()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
