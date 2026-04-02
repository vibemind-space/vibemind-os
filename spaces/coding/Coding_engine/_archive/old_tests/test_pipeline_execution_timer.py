"""Test pipeline execution timer."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_execution_timer import PipelineExecutionTimer


def test_start_stop():
    """Start and stop a timer."""
    et = PipelineExecutionTimer()
    tid = et.start_timer("build", category="build", owner="agent-1")
    assert tid.startswith("timer-")

    t = et.get_timer(tid)
    assert t is not None
    assert t["name"] == "build"
    assert t["status"] == "running"
    assert t["duration_ms"] >= 0  # Running timer has elapsed time

    duration = et.stop_timer(tid)
    assert duration >= 0
    t = et.get_timer(tid)
    assert t["status"] == "completed"
    print("OK: start stop")


def test_invalid_timer():
    """Invalid timer params rejected."""
    et = PipelineExecutionTimer()
    assert et.start_timer("") == ""
    assert et.start_timer("x", category="invalid") == ""
    print("OK: invalid timer")


def test_max_timers():
    """Max timers enforced."""
    et = PipelineExecutionTimer(max_timers=2)
    et.start_timer("a")
    et.start_timer("b")
    assert et.start_timer("c") == ""
    print("OK: max timers")


def test_stop_with_status():
    """Stop with different statuses."""
    et = PipelineExecutionTimer()
    t1 = et.start_timer("a")
    t2 = et.start_timer("b")
    t3 = et.start_timer("c")

    et.stop_timer(t1, status="completed")
    et.stop_timer(t2, status="failed")
    et.stop_timer(t3, status="cancelled")

    assert et.get_timer(t1)["status"] == "completed"
    assert et.get_timer(t2)["status"] == "failed"
    assert et.get_timer(t3)["status"] == "cancelled"
    print("OK: stop with status")


def test_stop_invalid():
    """Stop invalid timer fails."""
    et = PipelineExecutionTimer()
    assert et.stop_timer("nonexistent") == -1.0

    tid = et.start_timer("x")
    et.stop_timer(tid)
    assert et.stop_timer(tid) == -1.0  # Already stopped
    print("OK: stop invalid")


def test_remove_timer():
    """Remove a timer."""
    et = PipelineExecutionTimer()
    tid = et.start_timer("x")

    assert et.remove_timer(tid) is True
    assert et.remove_timer(tid) is False
    print("OK: remove timer")


def test_list_timers():
    """List timers with filters."""
    et = PipelineExecutionTimer()
    t1 = et.start_timer("a", category="build", owner="agent-1", tags=["ci"])
    t2 = et.start_timer("b", category="test", owner="agent-2")
    et.stop_timer(t1)

    all_t = et.list_timers()
    assert len(all_t) == 2

    by_status = et.list_timers(status="completed")
    assert len(by_status) == 1

    by_cat = et.list_timers(category="build")
    assert len(by_cat) == 1

    by_owner = et.list_timers(owner="agent-1")
    assert len(by_owner) == 1

    by_tag = et.list_timers(tag="ci")
    assert len(by_tag) == 1
    print("OK: list timers")


def test_running_timers():
    """Get running timers."""
    et = PipelineExecutionTimer()
    t1 = et.start_timer("a")
    t2 = et.start_timer("b")
    et.stop_timer(t1)

    running = et.get_running_timers()
    assert len(running) == 1
    assert running[0]["timer_id"] == t2
    print("OK: running timers")


def test_slow_executions():
    """Detect slow executions."""
    et = PipelineExecutionTimer(slow_threshold_ms=10.0)
    t1 = et.start_timer("fast")
    et.stop_timer(t1)  # Very fast

    t2 = et.start_timer("slow")
    time.sleep(0.02)  # 20ms
    et.stop_timer(t2)

    slow = et.get_slow_executions()
    assert len(slow) == 1
    assert slow[0]["name"] == "slow"
    print("OK: slow executions")


def test_slow_callback():
    """Slow execution callback fires."""
    et = PipelineExecutionTimer(slow_threshold_ms=5.0)

    fired = []
    et.on_change("mon", lambda a, d: fired.append(a))

    t1 = et.start_timer("slow")
    time.sleep(0.01)
    et.stop_timer(t1)

    assert "slow_execution" in fired
    print("OK: slow callback")


def test_average_duration():
    """Average duration calculation."""
    et = PipelineExecutionTimer()
    t1 = et.start_timer("a", category="build")
    t2 = et.start_timer("b", category="build")

    time.sleep(0.01)
    et.stop_timer(t1)
    et.stop_timer(t2)

    avg = et.get_average_duration(category="build")
    assert avg > 0
    print("OK: average duration")


def test_percentiles():
    """Percentile calculation."""
    et = PipelineExecutionTimer()
    for i in range(10):
        tid = et.start_timer(f"task-{i}")
        et.stop_timer(tid)

    p = et.get_percentiles()
    assert p["count"] == 10
    assert p["p50"] >= 0
    assert p["p90"] >= p["p50"]
    assert p["p99"] >= p["p90"]
    print("OK: percentiles")


def test_category_summary():
    """Category summary."""
    et = PipelineExecutionTimer()
    for cat in ["build", "build", "test"]:
        tid = et.start_timer(f"{cat}_task", category=cat)
        et.stop_timer(tid)

    summary = et.get_category_summary()
    assert len(summary) == 2
    build_sum = next(s for s in summary if s["category"] == "build")
    assert build_sum["count"] == 2
    print("OK: category summary")


def test_owner_summary():
    """Owner summary."""
    et = PipelineExecutionTimer()
    for i in range(3):
        tid = et.start_timer(f"task-{i}", owner="agent-1")
        et.stop_timer(tid)

    summary = et.get_owner_summary("agent-1")
    assert summary["count"] == 3
    assert summary["total_ms"] >= 0

    assert et.get_owner_summary("nonexistent") == {}
    print("OK: owner summary")


def test_callbacks():
    """Callbacks fire on events."""
    et = PipelineExecutionTimer()

    fired = []
    assert et.on_change("mon", lambda a, d: fired.append(a)) is True
    assert et.on_change("mon", lambda a, d: None) is False

    tid = et.start_timer("task")
    et.stop_timer(tid)
    assert "timer_stopped" in fired

    assert et.remove_callback("mon") is True
    assert et.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    et = PipelineExecutionTimer(slow_threshold_ms=5.0)
    t1 = et.start_timer("a")
    t2 = et.start_timer("b")
    t3 = et.start_timer("c")

    et.stop_timer(t1)
    et.stop_timer(t2, status="failed")

    stats = et.get_stats()
    assert stats["total_started"] == 3
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["running_timers"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    et = PipelineExecutionTimer()
    et.start_timer("a")

    et.reset()
    assert et.list_timers() == []
    stats = et.get_stats()
    assert stats["current_timers"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Execution Timer Tests ===\n")
    test_start_stop()
    test_invalid_timer()
    test_max_timers()
    test_stop_with_status()
    test_stop_invalid()
    test_remove_timer()
    test_list_timers()
    test_running_timers()
    test_slow_executions()
    test_slow_callback()
    test_average_duration()
    test_percentiles()
    test_category_summary()
    test_owner_summary()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
