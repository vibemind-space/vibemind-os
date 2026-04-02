"""Tests for AgentTaskTracker."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "services"))

from agent_task_tracker import AgentTaskTracker


def test_start_task():
    tracker = AgentTaskTracker()
    tid = tracker.start_task("agent-1", "build_index", total_steps=5)
    assert tid.startswith("att-"), f"Expected att- prefix, got {tid}"
    task = tracker.get_task(tid)
    assert task is not None
    assert task["agent_id"] == "agent-1"
    assert task["task_name"] == "build_index"
    assert task["status"] == "in_progress"
    assert task["current_step"] == 0
    assert task["total_steps"] == 5
    print("  test_start_task PASSED")


def test_update_progress():
    tracker = AgentTaskTracker()
    tid = tracker.start_task("agent-1", "scan", total_steps=10)
    result = tracker.update_progress(tid, 5)
    assert result is True
    task = tracker.get_task(tid)
    assert task["current_step"] == 5
    # not found
    result2 = tracker.update_progress("att-nonexistent", 1)
    assert result2 is False
    print("  test_update_progress PASSED")


def test_complete_task():
    tracker = AgentTaskTracker()
    tid = tracker.start_task("agent-1", "deploy", total_steps=3)
    result = tracker.complete_task(tid)
    assert result is True
    task = tracker.get_task(tid)
    assert task["status"] == "completed"
    assert task["current_step"] == task["total_steps"]
    # not found
    result2 = tracker.complete_task("att-nonexistent")
    assert result2 is False
    print("  test_complete_task PASSED")


def test_get_task():
    tracker = AgentTaskTracker()
    tid = tracker.start_task("agent-1", "analyze", total_steps=2)
    task = tracker.get_task(tid)
    assert task is not None
    assert task["task_id"] == tid
    # not found
    assert tracker.get_task("att-nope") is None
    print("  test_get_task PASSED")


def test_get_tasks_filtered():
    tracker = AgentTaskTracker()
    t1 = tracker.start_task("agent-1", "task_a", total_steps=1)
    t2 = tracker.start_task("agent-1", "task_b", total_steps=1)
    t3 = tracker.start_task("agent-2", "task_c", total_steps=1)
    tracker.complete_task(t1)

    # all tasks for agent-1
    tasks = tracker.get_tasks("agent-1")
    assert len(tasks) == 2

    # filtered by status
    completed = tracker.get_tasks("agent-1", status="completed")
    assert len(completed) == 1
    assert completed[0]["task_id"] == t1

    in_prog = tracker.get_tasks("agent-1", status="in_progress")
    assert len(in_prog) == 1
    assert in_prog[0]["task_id"] == t2

    # agent-2
    assert len(tracker.get_tasks("agent-2")) == 1
    print("  test_get_tasks_filtered PASSED")


def test_get_progress():
    tracker = AgentTaskTracker()
    tid = tracker.start_task("agent-1", "index", total_steps=4)
    assert tracker.get_progress(tid) == 0.0
    tracker.update_progress(tid, 2)
    assert tracker.get_progress(tid) == 0.5
    tracker.complete_task(tid)
    assert tracker.get_progress(tid) == 1.0
    # not found
    assert tracker.get_progress("att-missing") == 0.0
    print("  test_get_progress PASSED")


def test_get_task_count():
    tracker = AgentTaskTracker()
    tracker.start_task("agent-1", "a")
    tracker.start_task("agent-1", "b")
    tracker.start_task("agent-2", "c")
    assert tracker.get_task_count() == 3
    assert tracker.get_task_count("agent-1") == 2
    assert tracker.get_task_count("agent-2") == 1
    assert tracker.get_task_count("agent-3") == 0
    print("  test_get_task_count PASSED")


def test_list_agents():
    tracker = AgentTaskTracker()
    tracker.start_task("agent-b", "x")
    tracker.start_task("agent-a", "y")
    tracker.start_task("agent-b", "z")
    agents = tracker.list_agents()
    assert agents == ["agent-a", "agent-b"]
    print("  test_list_agents PASSED")


def test_callbacks():
    tracker = AgentTaskTracker()
    events = []
    tracker.on_change("listener", lambda action, detail: events.append((action, detail)))

    tid = tracker.start_task("agent-1", "job", total_steps=2)
    tracker.update_progress(tid, 1)
    tracker.complete_task(tid)

    assert len(events) == 3
    assert events[0][0] == "start_task"
    assert events[1][0] == "update_progress"
    assert events[2][0] == "complete_task"

    # remove_callback returns True/False
    assert tracker.remove_callback("listener") is True
    assert tracker.remove_callback("listener") is False
    print("  test_callbacks PASSED")


def test_stats():
    tracker = AgentTaskTracker()
    t1 = tracker.start_task("agent-1", "a")
    t2 = tracker.start_task("agent-2", "b")
    tracker.complete_task(t1)

    stats = tracker.get_stats()
    assert stats["total_tasks"] == 2
    assert stats["total_started"] == 2
    assert stats["total_completed"] == 1
    assert stats["unique_agents"] == 2
    assert stats["max_entries"] == 10_000
    print("  test_stats PASSED")


def test_reset():
    tracker = AgentTaskTracker()
    tracker.start_task("agent-1", "x")
    tracker.on_change("cb", lambda a, d: None)
    tracker.reset()
    assert tracker.get_task_count() == 0
    assert tracker.list_agents() == []
    stats = tracker.get_stats()
    assert stats["total_started"] == 0
    assert stats["callbacks_registered"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_start_task()
    test_update_progress()
    test_complete_task()
    test_get_task()
    test_get_tasks_filtered()
    test_get_progress()
    test_get_task_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")
