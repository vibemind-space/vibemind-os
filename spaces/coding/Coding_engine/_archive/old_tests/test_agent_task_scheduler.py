"""Test agent task scheduler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_task_scheduler import AgentTaskScheduler


def test_schedule_task():
    ts = AgentTaskScheduler()
    tid = ts.schedule_task("agent-1", "backup", schedule_type="once", delay=10.0)
    assert len(tid) > 0
    assert tid.startswith("ats-")
    print("OK: schedule task")


def test_get_task():
    ts = AgentTaskScheduler()
    tid = ts.schedule_task("agent-1", "backup", schedule_type="recurring", interval=60.0)
    task = ts.get_task(tid)
    assert task is not None
    assert task["agent_id"] == "agent-1"
    assert task["task_name"] == "backup"
    assert task["schedule_type"] == "recurring"
    assert ts.get_task("nonexistent") is None
    print("OK: get task")


def test_cancel_task():
    ts = AgentTaskScheduler()
    tid = ts.schedule_task("agent-1", "cleanup")
    assert ts.cancel_task(tid) is True
    assert ts.cancel_task(tid) is False
    print("OK: cancel task")


def test_get_agent_tasks():
    ts = AgentTaskScheduler()
    ts.schedule_task("agent-1", "t1")
    ts.schedule_task("agent-1", "t2")
    ts.schedule_task("agent-2", "t3")
    tasks = ts.get_agent_tasks("agent-1")
    assert len(tasks) == 2
    print("OK: get agent tasks")


def test_get_pending_tasks():
    ts = AgentTaskScheduler()
    t1 = ts.schedule_task("agent-1", "t1")
    t2 = ts.schedule_task("agent-1", "t2")
    ts.mark_running(t1)
    pending = ts.get_pending_tasks()
    assert len(pending) == 1
    print("OK: get pending tasks")


def test_mark_running():
    ts = AgentTaskScheduler()
    tid = ts.schedule_task("agent-1", "job")
    assert ts.mark_running(tid) is True
    task = ts.get_task(tid)
    assert task is not None
    print("OK: mark running")


def test_mark_completed():
    ts = AgentTaskScheduler()
    tid = ts.schedule_task("agent-1", "job", schedule_type="once")
    ts.mark_running(tid)
    assert ts.mark_completed(tid) is True
    print("OK: mark completed")


def test_mark_completed_recurring():
    ts = AgentTaskScheduler()
    tid = ts.schedule_task("agent-1", "job", schedule_type="recurring", interval=60.0)
    ts.mark_running(tid)
    assert ts.mark_completed(tid) is True
    task = ts.get_task(tid)
    assert task is not None  # recurring tasks stay in the system
    print("OK: mark completed recurring")


def test_mark_failed():
    ts = AgentTaskScheduler()
    tid = ts.schedule_task("agent-1", "job")
    ts.mark_running(tid)
    assert ts.mark_failed(tid, reason="timeout") is True
    print("OK: mark failed")


def test_list_agents():
    ts = AgentTaskScheduler()
    ts.schedule_task("agent-1", "t1")
    ts.schedule_task("agent-2", "t2")
    agents = ts.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ts = AgentTaskScheduler()
    fired = []
    ts.on_change("mon", lambda a, d: fired.append(a))
    ts.schedule_task("agent-1", "t1")
    assert len(fired) >= 1
    assert ts.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ts = AgentTaskScheduler()
    ts.schedule_task("agent-1", "t1")
    stats = ts.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ts = AgentTaskScheduler()
    ts.schedule_task("agent-1", "t1")
    ts.reset()
    assert ts.get_task_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Task Scheduler Tests ===\n")
    test_schedule_task()
    test_get_task()
    test_cancel_task()
    test_get_agent_tasks()
    test_get_pending_tasks()
    test_mark_running()
    test_mark_completed()
    test_mark_completed_recurring()
    test_mark_failed()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
