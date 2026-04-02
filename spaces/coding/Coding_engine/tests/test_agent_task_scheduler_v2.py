"""Tests for AgentTaskSchedulerV2."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_scheduler_v2 import AgentTaskSchedulerV2


def test_schedule_task():
    s = AgentTaskSchedulerV2()
    tid = s.schedule_task("a1", "build")
    assert tid.startswith("ats2-")
    assert len(tid) == 5 + 16


def test_get_task():
    s = AgentTaskSchedulerV2()
    tid = s.schedule_task("a1", "build", priority=3)
    t = s.get_task(tid)
    assert t["agent_id"] == "a1"
    assert t["task_name"] == "build"
    assert t["priority"] == 3
    assert t["status"] == "queued"
    assert t["started_at"] is None
    assert t["completed_at"] is None


def test_get_task_not_found():
    s = AgentTaskSchedulerV2()
    assert s.get_task("ats2-nonexistent") is None


def test_start_task():
    s = AgentTaskSchedulerV2()
    tid = s.schedule_task("a1", "deploy")
    assert s.start_task(tid) is True
    t = s.get_task(tid)
    assert t["status"] == "running"
    assert t["started_at"] is not None


def test_start_task_not_found():
    s = AgentTaskSchedulerV2()
    assert s.start_task("ats2-fake") is False


def test_complete_task():
    s = AgentTaskSchedulerV2()
    tid = s.schedule_task("a1", "test")
    s.start_task(tid)
    assert s.complete_task(tid, result="ok") is True
    t = s.get_task(tid)
    assert t["status"] == "completed"
    assert t["completed_at"] is not None
    assert t["result"] == "ok"


def test_complete_task_not_found():
    s = AgentTaskSchedulerV2()
    assert s.complete_task("ats2-fake") is False


def test_fail_task():
    s = AgentTaskSchedulerV2()
    tid = s.schedule_task("a1", "lint")
    s.start_task(tid)
    assert s.fail_task(tid, error="timeout") is True
    t = s.get_task(tid)
    assert t["status"] == "failed"
    assert t["error"] == "timeout"


def test_fail_task_not_found():
    s = AgentTaskSchedulerV2()
    assert s.fail_task("ats2-nope") is False


def test_get_tasks_by_agent():
    s = AgentTaskSchedulerV2()
    s.schedule_task("a1", "t1")
    s.schedule_task("a1", "t2")
    s.schedule_task("a2", "t3")
    assert len(s.get_tasks("a1")) == 2
    assert len(s.get_tasks("a2")) == 1


def test_get_tasks_by_status():
    s = AgentTaskSchedulerV2()
    t1 = s.schedule_task("a1", "t1")
    s.schedule_task("a1", "t2")
    s.start_task(t1)
    assert len(s.get_tasks("a1", status="queued")) == 1
    assert len(s.get_tasks("a1", status="running")) == 1


def test_get_next_task_priority():
    s = AgentTaskSchedulerV2()
    s.schedule_task("a1", "low", priority=8)
    s.schedule_task("a1", "high", priority=2)
    s.schedule_task("a1", "mid", priority=5)
    nxt = s.get_next_task("a1")
    assert nxt["task_name"] == "high"
    assert nxt["priority"] == 2


def test_get_next_task_none():
    s = AgentTaskSchedulerV2()
    assert s.get_next_task("a1") is None


def test_get_overdue_tasks():
    s = AgentTaskSchedulerV2()
    past = time.time() - 100
    future = time.time() + 1000
    t1 = s.schedule_task("a1", "overdue1", deadline=past)
    s.schedule_task("a1", "not_overdue", deadline=future)
    s.schedule_task("a1", "no_deadline", deadline=0)
    overdue = s.get_overdue_tasks()
    assert len(overdue) == 1
    assert overdue[0]["task_id"] == t1


def test_get_task_count():
    s = AgentTaskSchedulerV2()
    s.schedule_task("a1", "t1")
    s.schedule_task("a1", "t2")
    s.schedule_task("a2", "t3")
    assert s.get_task_count() == 3
    assert s.get_task_count(agent_id="a1") == 2
    assert s.get_task_count(status="queued") == 3


def test_get_stats():
    s = AgentTaskSchedulerV2()
    t1 = s.schedule_task("a1", "t1")
    t2 = s.schedule_task("a1", "t2")
    t3 = s.schedule_task("a1", "t3")
    s.start_task(t1)
    s.complete_task(t2)
    s.fail_task(t3)
    stats = s.get_stats()
    assert stats["total_tasks"] == 3
    assert stats["running"] == 1
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["queued"] == 0


def test_reset():
    s = AgentTaskSchedulerV2()
    s.schedule_task("a1", "t1")
    s.reset()
    assert s.get_task_count() == 0
    assert s.get_stats()["total_tasks"] == 0


def test_on_change_callback():
    events = []
    s = AgentTaskSchedulerV2()
    s.on_change = lambda evt, data: events.append(evt)
    s.schedule_task("a1", "t1")
    assert "task_scheduled" in events


def test_remove_callback():
    s = AgentTaskSchedulerV2()
    s._callbacks["mycb"] = lambda e, d: None
    assert s.remove_callback("mycb") is True
    assert s.remove_callback("mycb") is False


def test_callback_error_handled():
    s = AgentTaskSchedulerV2()
    s.on_change = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
    # Should not raise
    s.schedule_task("a1", "t1")


def test_metadata():
    s = AgentTaskSchedulerV2()
    tid = s.schedule_task("a1", "t1", metadata={"key": "val"})
    t = s.get_task(tid)
    assert t["metadata"] == {"key": "val"}


def test_default_priority_and_deadline():
    s = AgentTaskSchedulerV2()
    tid = s.schedule_task("a1", "t1")
    t = s.get_task(tid)
    assert t["priority"] == 5
    assert t["deadline"] == 0


def test_unique_ids():
    s = AgentTaskSchedulerV2()
    ids = set()
    for i in range(50):
        ids.add(s.schedule_task("a1", f"task_{i}"))
    assert len(ids) == 50


if __name__ == "__main__":
    tests = [
        test_schedule_task,
        test_get_task,
        test_get_task_not_found,
        test_start_task,
        test_start_task_not_found,
        test_complete_task,
        test_complete_task_not_found,
        test_fail_task,
        test_fail_task_not_found,
        test_get_tasks_by_agent,
        test_get_tasks_by_status,
        test_get_next_task_priority,
        test_get_next_task_none,
        test_get_overdue_tasks,
        test_get_task_count,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_callback_error_handled,
        test_metadata,
        test_default_priority_and_deadline,
        test_unique_ids,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
