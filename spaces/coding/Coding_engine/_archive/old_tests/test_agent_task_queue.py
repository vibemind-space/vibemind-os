"""Test agent task queue with priority scheduling."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_task_queue import (
    AgentTaskQueue,
    TaskPriority,
    TaskStatus,
)


def test_submit_and_get():
    """Basic task submission and retrieval."""
    q = AgentTaskQueue()
    tid = q.submit("Build login page", agent_type="frontend", priority=TaskPriority.NORMAL)

    task = q.get_task(tid)
    assert task is not None
    assert task["description"] == "Build login page"
    assert task["agent_type"] == "frontend"
    assert task["status"] == "queued"
    assert task["priority"] == TaskPriority.NORMAL
    print("OK: submit and get")


def test_priority_ordering():
    """Higher priority tasks are assigned first."""
    q = AgentTaskQueue()
    low = q.submit("Low task", agent_type="general", priority=TaskPriority.LOW)
    high = q.submit("High task", agent_type="general", priority=TaskPriority.HIGH)
    critical = q.submit("Critical task", agent_type="general", priority=TaskPriority.CRITICAL)

    # First assignment should be critical
    t1 = q.assign_next("agent1", agent_type="general")
    assert t1.task_id == critical

    t2 = q.assign_next("agent2", agent_type="general")
    assert t2.task_id == high

    t3 = q.assign_next("agent3", agent_type="general")
    assert t3.task_id == low

    print("OK: priority ordering")


def test_agent_type_routing():
    """Tasks are routed to correct agent types."""
    q = AgentTaskQueue()
    fe_task = q.submit("React component", agent_type="frontend")
    be_task = q.submit("API endpoint", agent_type="backend")

    # Frontend agent gets frontend task
    t = q.assign_next("fe-agent", agent_type="frontend")
    assert t.task_id == fe_task

    # Backend agent gets backend task
    t = q.assign_next("be-agent", agent_type="backend")
    assert t.task_id == be_task

    # No more frontend tasks
    t = q.assign_next("fe-agent2", agent_type="frontend")
    assert t is None

    print("OK: agent type routing")


def test_task_lifecycle():
    """Task goes through full lifecycle: queued -> assigned -> running -> completed."""
    q = AgentTaskQueue()
    tid = q.submit("Build feature", agent_type="general")

    task = q.assign_next("agent1", agent_type="general")
    assert task.status == TaskStatus.ASSIGNED
    assert task.assigned_to == "agent1"

    q.start(tid)
    info = q.get_task(tid)
    assert info["status"] == "running"

    q.complete(tid, result={"files": ["feature.py"]})
    info = q.get_task(tid)
    assert info["status"] == "completed"
    assert info["execution_time_ms"] is not None

    print("OK: task lifecycle")


def test_task_failure_retry():
    """Failed tasks are retried up to max_retries."""
    q = AgentTaskQueue(max_retries=2)
    tid = q.submit("Flaky task", agent_type="general")

    # First attempt fails
    t = q.assign_next("agent1", agent_type="general")
    q.start(tid)
    q.fail(tid, error="network error")

    info = q.get_task(tid)
    assert info["status"] == "queued"  # Re-queued

    # Second attempt fails
    t = q.assign_next("agent1", agent_type="general")
    q.start(tid)
    q.fail(tid, error="network error again")

    info = q.get_task(tid)
    assert info["status"] == "dead_letter"  # Max retries reached

    dlq = q.get_dead_letter_queue()
    assert len(dlq) == 1
    assert dlq[0]["task_id"] == tid

    print("OK: task failure retry")


def test_concurrency_limits():
    """Agent concurrency limits are enforced."""
    q = AgentTaskQueue()
    q.set_agent_limit("busy_agent", 2)

    q.submit("Task 1", agent_type="general")
    q.submit("Task 2", agent_type="general")
    q.submit("Task 3", agent_type="general")

    t1 = q.assign_next("busy_agent", agent_type="general")
    assert t1 is not None
    t2 = q.assign_next("busy_agent", agent_type="general")
    assert t2 is not None
    t3 = q.assign_next("busy_agent", agent_type="general")
    assert t3 is None  # Limit reached

    # Complete one, then should be able to get another
    q.complete(t1.task_id)
    t3 = q.assign_next("busy_agent", agent_type="general")
    assert t3 is not None

    print("OK: concurrency limits")


def test_task_dependencies():
    """Tasks with dependencies wait until deps are completed."""
    q = AgentTaskQueue()
    base_task = q.submit("Build core", agent_type="general", task_id="core")
    dep_task = q.submit("Build API", agent_type="general", task_id="api", depends_on=["core"])

    # API should not be assignable yet
    t = q.assign_next("agent1", agent_type="general")
    assert t.task_id == "core"  # Gets core first (API is blocked)

    # Complete core
    q.start("core")
    q.complete("core")

    # Now API should be assignable
    t = q.assign_next("agent2", agent_type="general")
    assert t is not None
    assert t.task_id == "api"

    print("OK: task dependencies")


def test_cancel_task():
    """Tasks can be cancelled."""
    q = AgentTaskQueue()
    tid = q.submit("Cancelled task", agent_type="general")

    assert q.cancel(tid) is True
    info = q.get_task(tid)
    assert info["status"] == "cancelled"

    # Can't assign cancelled task
    t = q.assign_next("agent1", agent_type="general")
    assert t is None

    # Can't cancel completed task
    tid2 = q.submit("Done task", agent_type="general")
    t = q.assign_next("agent1", agent_type="general")
    q.start(tid2)
    q.complete(tid2)
    assert q.cancel(tid2) is False

    print("OK: cancel task")


def test_queue_depth():
    """Queue depth tracking works correctly."""
    q = AgentTaskQueue()
    q.submit("T1", agent_type="frontend")
    q.submit("T2", agent_type="frontend")
    q.submit("T3", agent_type="backend")

    assert q.get_queue_depth() == 3
    assert q.get_queue_depth("frontend") == 2
    assert q.get_queue_depth("backend") == 1
    assert q.get_queue_depth("unknown") == 0

    # Assign one
    q.assign_next("agent1", agent_type="frontend")
    assert q.get_queue_depth("frontend") == 1
    assert q.get_queue_depth() == 2

    print("OK: queue depth")


def test_agent_tasks():
    """Get tasks assigned to an agent."""
    q = AgentTaskQueue()
    q.submit("T1", agent_type="general")
    q.submit("T2", agent_type="general")

    q.assign_next("worker1", agent_type="general")
    q.assign_next("worker1", agent_type="general")

    tasks = q.get_agent_tasks("worker1")
    assert len(tasks) == 2

    tasks2 = q.get_agent_tasks("worker2")
    assert len(tasks2) == 0

    print("OK: agent tasks")


def test_pending_by_type():
    """Pending tasks grouped by agent type."""
    q = AgentTaskQueue()
    q.submit("FE1", agent_type="frontend")
    q.submit("FE2", agent_type="frontend")
    q.submit("BE1", agent_type="backend")

    pending = q.get_pending_by_type()
    assert pending["frontend"] == 2
    assert pending["backend"] == 1

    print("OK: pending by type")


def test_starvation_prevention():
    """Older tasks get priority boost via aging."""
    q = AgentTaskQueue()

    # Submit old task with low priority
    old_id = q.submit("Old task", agent_type="general", priority=TaskPriority.LOW)
    old_task = q._tasks[old_id]
    old_task.created_at = time.time() - 300  # 5 minutes ago

    # Submit new task with normal priority
    new_id = q.submit("New task", agent_type="general", priority=TaskPriority.NORMAL)

    # Old task should have better effective priority due to aging
    assert old_task.effective_priority < q._tasks[new_id].effective_priority

    # Old task should be assigned first despite lower base priority
    t = q.assign_next("agent1", agent_type="general")
    assert t.task_id == old_id

    print("OK: starvation prevention")


def test_preferred_types():
    """Agent can handle multiple task types."""
    q = AgentTaskQueue()
    q.submit("FE task", agent_type="frontend")
    q.submit("BE task", agent_type="backend", priority=TaskPriority.HIGH)

    # Full-stack agent handles both
    t = q.assign_next("fullstack", preferred_types=["frontend", "backend"])
    assert t is not None
    assert t.task_id  # Should get the highest priority across both queues

    print("OK: preferred types")


def test_completion_callback():
    """Callbacks fire on task completion."""
    q = AgentTaskQueue()
    tid = q.submit("Callback task", agent_type="general")

    results = []
    q.on_complete(tid, lambda task: results.append(task.task_id))

    t = q.assign_next("agent1", agent_type="general")
    q.start(tid)
    q.complete(tid, result="done")

    assert len(results) == 1
    assert results[0] == tid

    print("OK: completion callback")


def test_overdue_detection():
    """Overdue tasks are detected."""
    q = AgentTaskQueue()
    tid = q.submit(
        "Urgent task", agent_type="general",
        deadline=time.time() - 10,  # Already past deadline
    )

    overdue = q.get_overdue_tasks()
    assert len(overdue) == 1
    assert overdue[0]["task_id"] == tid
    assert overdue[0]["is_overdue"] is True

    print("OK: overdue detection")


def test_stats():
    """Queue stats are accurate."""
    q = AgentTaskQueue()
    q.submit("T1", agent_type="general")
    q.submit("T2", agent_type="general")
    t = q.assign_next("agent1", agent_type="general")
    q.start(t.task_id)
    q.complete(t.task_id)

    stats = q.get_stats()
    assert stats["total_tasks"] == 2
    assert stats["queue_depth"] == 1
    assert stats["status_counts"]["completed"] == 1
    assert stats["status_counts"]["queued"] == 1
    assert stats["dead_letter_count"] == 0

    print("OK: stats")


def test_clear_completed():
    """Clear completed tasks older than threshold."""
    q = AgentTaskQueue()
    tid = q.submit("Old task", agent_type="general")
    t = q.assign_next("agent1", agent_type="general")
    q.start(tid)
    q.complete(tid)

    # Backdate completion
    q._tasks[tid].completed_at = time.time() - 7200  # 2 hours ago

    removed = q.clear_completed(older_than_seconds=3600)
    assert removed == 1
    assert q.get_task(tid) is None

    print("OK: clear completed")


def test_multi_dependency_chain():
    """Chain of dependencies: A -> B -> C."""
    q = AgentTaskQueue()
    q.submit("Step A", agent_type="general", task_id="a")
    q.submit("Step B", agent_type="general", task_id="b", depends_on=["a"])
    q.submit("Step C", agent_type="general", task_id="c", depends_on=["b"])

    # Only A should be assignable
    t = q.assign_next("w1", agent_type="general")
    assert t.task_id == "a"

    # B and C blocked
    t2 = q.assign_next("w2", agent_type="general")
    assert t2 is None

    # Complete A -> B becomes available
    q.start("a")
    q.complete("a")
    t2 = q.assign_next("w2", agent_type="general")
    assert t2.task_id == "b"

    # C still blocked
    t3 = q.assign_next("w3", agent_type="general")
    assert t3 is None

    # Complete B -> C becomes available
    q.start("b")
    q.complete("b")
    t3 = q.assign_next("w3", agent_type="general")
    assert t3.task_id == "c"

    print("OK: multi dependency chain")


def main():
    print("=== Agent Task Queue Tests ===\n")
    test_submit_and_get()
    test_priority_ordering()
    test_agent_type_routing()
    test_task_lifecycle()
    test_task_failure_retry()
    test_concurrency_limits()
    test_task_dependencies()
    test_cancel_task()
    test_queue_depth()
    test_agent_tasks()
    test_pending_by_type()
    test_starvation_prevention()
    test_preferred_types()
    test_completion_callback()
    test_overdue_detection()
    test_stats()
    test_clear_completed()
    test_multi_dependency_chain()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
