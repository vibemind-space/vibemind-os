"""Test pipeline execution logger."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_execution_logger import PipelineExecutionLogger


def test_create_run():
    """Create and retrieve run."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build_v2", tags=["ci"])
    assert rid.startswith("run-")

    r = el.get_run(rid)
    assert r is not None
    assert r["name"] == "build_v2"
    assert r["status"] == "running"
    assert r["log_count"] == 0

    assert el.remove_run(rid) is True
    assert el.remove_run(rid) is False
    print("OK: create run")


def test_invalid_run():
    """Invalid run rejected."""
    el = PipelineExecutionLogger()
    assert el.create_run("") == ""
    print("OK: invalid run")


def test_complete_run():
    """Complete a run."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")

    assert el.complete_run(rid) is True
    assert el.get_run(rid)["status"] == "completed"
    assert el.complete_run(rid) is False
    print("OK: complete run")


def test_fail_run():
    """Fail a run."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")

    assert el.fail_run(rid) is True
    assert el.get_run(rid)["status"] == "failed"
    assert el.fail_run(rid) is False
    print("OK: fail run")


def test_cancel_run():
    """Cancel a run."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")

    assert el.cancel_run(rid) is True
    assert el.get_run(rid)["status"] == "cancelled"
    assert el.cancel_run(rid) is False
    print("OK: cancel run")


def test_log_entry():
    """Write and retrieve log entry."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    lid = el.log(rid, "Starting build", stage="compile",
                 agent="agent-1", action="start", level="info",
                 duration_ms=150.0, tags=["build"])
    assert lid.startswith("log-")

    l = el.get_log(lid)
    assert l is not None
    assert l["run_id"] == rid
    assert l["stage"] == "compile"
    assert l["agent"] == "agent-1"
    assert l["level"] == "info"
    assert l["duration_ms"] == 150.0

    assert el.get_run(rid)["log_count"] == 1

    assert el.remove_log(lid) is True
    assert el.remove_log(lid) is False
    assert el.get_run(rid)["log_count"] == 0
    print("OK: log entry")


def test_invalid_log():
    """Invalid log rejected."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    assert el.log("", "msg") == ""
    assert el.log(rid, "") == ""
    assert el.log(rid, "msg", level="invalid") == ""
    assert el.log("nonexistent", "msg") == ""
    print("OK: invalid log")


def test_get_run_logs():
    """Get logs for a run."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    el.log(rid, "step1", stage="compile", level="info")
    el.log(rid, "step2", stage="test", level="warning")
    el.log(rid, "step3", stage="compile", level="error")

    all_logs = el.get_run_logs(rid)
    assert len(all_logs) == 3
    # Ordered by seq ascending
    assert all_logs[0]["message"] == "step1"

    by_level = el.get_run_logs(rid, level="error")
    assert len(by_level) == 1

    by_stage = el.get_run_logs(rid, stage="compile")
    assert len(by_stage) == 2
    print("OK: get run logs")


def test_search_logs():
    """Search all logs."""
    el = PipelineExecutionLogger()
    r1 = el.create_run("build1")
    r2 = el.create_run("build2")
    el.log(r1, "m1", agent="alice", level="info", stage="compile",
           action="start", tags=["ci"])
    el.log(r1, "m2", agent="bob", level="error")
    el.log(r2, "m3", agent="alice", level="info")

    by_agent = el.search_logs(agent="alice")
    assert len(by_agent) == 2

    by_level = el.search_logs(level="error")
    assert len(by_level) == 1

    by_stage = el.search_logs(stage="compile")
    assert len(by_stage) == 1

    by_action = el.search_logs(action="start")
    assert len(by_action) == 1

    by_tag = el.search_logs(tag="ci")
    assert len(by_tag) == 1
    print("OK: search logs")


def test_search_limit():
    """Search respects limit."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    for i in range(20):
        el.log(rid, f"m{i}")

    results = el.search_logs(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_list_runs():
    """List runs with filters."""
    el = PipelineExecutionLogger()
    r1 = el.create_run("a", tags=["ci"])
    r2 = el.create_run("b")
    el.complete_run(r2)

    all_r = el.list_runs()
    assert len(all_r) == 2

    by_status = el.list_runs(status="completed")
    assert len(by_status) == 1

    by_tag = el.list_runs(tag="ci")
    assert len(by_tag) == 1
    print("OK: list runs")


def test_level_counts():
    """Get log counts by level."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    el.log(rid, "m1", level="info")
    el.log(rid, "m2", level="info")
    el.log(rid, "m3", level="error")

    counts = el.get_level_counts(run_id=rid)
    assert counts["info"] == 2
    assert counts["error"] == 1
    assert counts["warning"] == 0

    counts_all = el.get_level_counts()
    assert counts_all["info"] == 2
    print("OK: level counts")


def test_stage_timing():
    """Get stage timing."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    el.log(rid, "m1", stage="compile", duration_ms=100)
    el.log(rid, "m2", stage="compile", duration_ms=200)
    el.log(rid, "m3", stage="test", duration_ms=50)

    timing = el.get_stage_timing(rid)
    assert len(timing) == 2
    # Sorted by total duration desc
    assert timing[0]["stage"] == "compile"
    assert timing[0]["total_duration_ms"] == 300.0
    assert timing[0]["log_count"] == 2
    assert timing[1]["stage"] == "test"
    print("OK: stage timing")


def test_remove_run_cascades():
    """Removing run removes its logs."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    el.log(rid, "m1")
    el.log(rid, "m2")

    el.remove_run(rid)
    assert el.search_logs() == []
    print("OK: remove run cascades")


def test_run_callback():
    """Callback fires on run create."""
    el = PipelineExecutionLogger()
    fired = []
    el.on_change("mon", lambda a, d: fired.append(a))

    el.create_run("build")
    assert "run_created" in fired
    print("OK: run callback")


def test_callbacks():
    """Callback registration."""
    el = PipelineExecutionLogger()
    assert el.on_change("mon", lambda a, d: None) is True
    assert el.on_change("mon", lambda a, d: None) is False
    assert el.remove_callback("mon") is True
    assert el.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    el = PipelineExecutionLogger()
    r1 = el.create_run("a")
    r2 = el.create_run("b")
    el.log(r1, "m1")
    el.log(r1, "m2")
    el.complete_run(r1)
    el.fail_run(r2)

    stats = el.get_stats()
    assert stats["total_runs_created"] == 2
    assert stats["total_runs_completed"] == 1
    assert stats["total_runs_failed"] == 1
    assert stats["total_logs_written"] == 2
    assert stats["current_logs"] == 2
    assert stats["current_runs"] == 2
    assert stats["running_runs"] == 0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    el = PipelineExecutionLogger()
    rid = el.create_run("build")
    el.log(rid, "m")

    el.reset()
    assert el.list_runs() == []
    assert el.search_logs() == []
    stats = el.get_stats()
    assert stats["current_runs"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Execution Logger Tests ===\n")
    test_create_run()
    test_invalid_run()
    test_complete_run()
    test_fail_run()
    test_cancel_run()
    test_log_entry()
    test_invalid_log()
    test_get_run_logs()
    test_search_logs()
    test_search_limit()
    test_list_runs()
    test_level_counts()
    test_stage_timing()
    test_remove_run_cascades()
    test_run_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
