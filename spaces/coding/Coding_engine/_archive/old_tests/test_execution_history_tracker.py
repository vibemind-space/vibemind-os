"""Test execution history tracker."""
import sys
import time
sys.path.insert(0, ".")

from src.services.execution_history_tracker import ExecutionHistoryTracker


def test_start_complete_run():
    """Start and complete a run."""
    t = ExecutionHistoryTracker()
    rid = t.start_run("Build", trigger="ci", category="build", tags={"core"})
    assert rid.startswith("run-")

    run = t.get_run(rid)
    assert run is not None
    assert run["status"] == "running"
    assert run["trigger"] == "ci"
    assert "core" in run["tags"]

    time.sleep(0.01)
    assert t.complete_run(rid) is True
    run = t.get_run(rid)
    assert run["status"] == "completed"
    assert run["duration"] > 0
    print("OK: start complete run")


def test_fail_run():
    """Fail a run."""
    t = ExecutionHistoryTracker()
    rid = t.start_run("Build")

    assert t.fail_run(rid, error="compile error") is True
    run = t.get_run(rid)
    assert run["status"] == "failed"
    assert run["error"] == "compile error"

    assert t.fail_run(rid) is False  # Already failed
    print("OK: fail run")


def test_cancel_run():
    """Cancel a run."""
    t = ExecutionHistoryTracker()
    rid = t.start_run("Build")

    assert t.cancel_run(rid) is True
    assert t.get_run(rid)["status"] == "cancelled"
    assert t.cancel_run(rid) is False
    print("OK: cancel run")


def test_add_steps():
    """Add steps to a run."""
    t = ExecutionHistoryTracker()
    rid = t.start_run("Build")

    sid1 = t.add_step(rid, "compile", duration=1.5)
    sid2 = t.add_step(rid, "link", duration=0.3, status="failed", error="link error")
    assert sid1 is not None
    assert sid2 is not None

    steps = t.get_steps(rid)
    assert len(steps) == 2
    assert steps[0]["name"] == "compile"
    assert steps[1]["status"] == "failed"

    assert t.add_step("fake", "x") is None
    print("OK: add steps")


def test_list_runs():
    """List runs with filters."""
    t = ExecutionHistoryTracker()
    r1 = t.start_run("Build", category="build")
    r2 = t.start_run("Test", category="test")
    t.complete_run(r1)

    all_runs = t.list_runs()
    assert len(all_runs) == 2

    completed = t.list_runs(status="completed")
    assert len(completed) == 1

    by_cat = t.list_runs(category="build")
    assert len(by_cat) == 1

    limited = t.list_runs(limit=1)
    assert len(limited) == 1
    print("OK: list runs")


def test_get_latest():
    """Get most recent run."""
    t = ExecutionHistoryTracker()
    t.start_run("First")
    time.sleep(0.01)
    t.start_run("Second")

    latest = t.get_latest()
    assert latest is not None
    assert latest["name"] == "Second"

    by_name = t.get_latest(name="First")
    assert by_name["name"] == "First"
    print("OK: get latest")


def test_search():
    """Search runs."""
    t = ExecutionHistoryTracker()
    r1 = t.start_run("Build project")
    r2 = t.start_run("Test suite")
    t.fail_run(r2, error="assertion failed")

    results = t.search("build")
    assert len(results) == 1

    results = t.search("assertion")
    assert len(results) == 1
    print("OK: search")


def test_duration_stats():
    """Duration statistics."""
    t = ExecutionHistoryTracker()
    r1 = t.start_run("Build")
    time.sleep(0.01)
    t.complete_run(r1)

    r2 = t.start_run("Build")
    time.sleep(0.02)
    t.complete_run(r2)

    stats = t.get_duration_stats(name="Build")
    assert stats["count"] == 2
    assert stats["min"] > 0
    assert stats["avg"] > 0
    print("OK: duration stats")


def test_success_rate():
    """Success rate calculation."""
    t = ExecutionHistoryTracker()
    for _ in range(3):
        rid = t.start_run("Build")
        t.complete_run(rid)

    rid = t.start_run("Build")
    t.fail_run(rid)

    rate = t.get_success_rate(name="Build")
    assert rate["completed"] == 3
    assert rate["failed"] == 1
    assert rate["success_rate"] == 75.0
    print("OK: success rate")


def test_compare_runs():
    """Compare two runs."""
    t = ExecutionHistoryTracker()
    r1 = t.start_run("Build")
    t.add_step(r1, "compile", duration=1.0)
    t.complete_run(r1)

    r2 = t.start_run("Build")
    t.add_step(r2, "compile", duration=0.8)
    t.add_step(r2, "link", duration=0.2)
    t.complete_run(r2)

    comp = t.compare_runs(r1, r2)
    assert comp is not None
    assert comp["steps_a"] == 1
    assert comp["steps_b"] == 2
    assert comp["step_diff"] == 1

    assert t.compare_runs(r1, "fake") is None
    print("OK: compare runs")


def test_list_categories():
    """List categories."""
    t = ExecutionHistoryTracker()
    t.start_run("A", category="build")
    t.start_run("B", category="test")
    t.start_run("C", category="build")

    cats = t.list_categories()
    assert cats["build"] == 2
    assert cats["test"] == 1
    print("OK: list categories")


def test_list_tags():
    """List tags."""
    t = ExecutionHistoryTracker()
    t.start_run("A", tags={"core", "ci"})
    t.start_run("B", tags={"ci"})

    tags = t.list_tags()
    assert tags["ci"] == 2
    assert tags["core"] == 1
    print("OK: list tags")


def test_list_triggers():
    """List triggers."""
    t = ExecutionHistoryTracker()
    t.start_run("A", trigger="ci")
    t.start_run("B", trigger="manual")
    t.start_run("C", trigger="ci")

    triggers = t.list_triggers()
    assert triggers["ci"] == 2
    assert triggers["manual"] == 1
    print("OK: list triggers")


def test_delete_run():
    """Delete a run."""
    t = ExecutionHistoryTracker()
    rid = t.start_run("Build")

    assert t.delete_run(rid) is True
    assert t.delete_run(rid) is False
    assert t.get_run(rid) is None
    print("OK: delete run")


def test_cleanup():
    """Cleanup finished runs."""
    t = ExecutionHistoryTracker()
    r1 = t.start_run("A")
    r2 = t.start_run("B")
    r3 = t.start_run("C")

    t.complete_run(r1)
    t.fail_run(r2)

    count = t.cleanup(status="completed")
    assert count == 1
    assert t.get_run(r1) is None
    assert t.get_run(r2) is not None  # Failed, not completed
    assert t.get_run(r3) is not None  # Still running
    print("OK: cleanup")


def test_stats():
    """Stats are accurate."""
    t = ExecutionHistoryTracker()
    r1 = t.start_run("A")
    r2 = t.start_run("B")
    t.add_step(r1, "s1")
    t.complete_run(r1)
    t.fail_run(r2)

    stats = t.get_stats()
    assert stats["total_runs"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_steps"] == 1
    assert stats["stored_runs"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    t = ExecutionHistoryTracker()
    t.start_run("A")

    t.reset()
    assert t.list_runs() == []
    stats = t.get_stats()
    assert stats["stored_runs"] == 0
    print("OK: reset")


def main():
    print("=== Execution History Tracker Tests ===\n")
    test_start_complete_run()
    test_fail_run()
    test_cancel_run()
    test_add_steps()
    test_list_runs()
    test_get_latest()
    test_search()
    test_duration_stats()
    test_success_rate()
    test_compare_runs()
    test_list_categories()
    test_list_tags()
    test_list_triggers()
    test_delete_run()
    test_cleanup()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
