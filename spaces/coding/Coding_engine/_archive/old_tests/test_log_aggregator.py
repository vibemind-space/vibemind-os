"""Test log aggregator."""
import sys
import time
sys.path.insert(0, ".")

from src.services.log_aggregator import LogAggregator


def test_basic_log():
    """Log and retrieve entries."""
    logs = LogAggregator()
    eid = logs.log("Builder", "info", "Started building", run_id="run-1")

    assert eid.startswith("log-")
    recent = logs.get_recent()
    assert len(recent) == 1
    assert recent[0]["source"] == "Builder"
    assert recent[0]["level"] == "info"
    assert recent[0]["message"] == "Started building"
    print("OK: basic log")


def test_convenience_methods():
    """Debug/info/warning/error/critical shortcuts."""
    logs = LogAggregator()
    logs.debug("Agent", "debug msg")
    logs.info("Agent", "info msg")
    logs.warning("Agent", "warning msg")
    logs.error("Agent", "error msg")
    logs.critical("Agent", "critical msg")

    all_logs = logs.get_recent(limit=10)
    assert len(all_logs) == 5
    levels = [e["level"] for e in all_logs]
    assert levels == ["debug", "info", "warning", "error", "critical"]
    print("OK: convenience methods")


def test_get_run_logs():
    """Get logs for a specific run."""
    logs = LogAggregator()
    logs.info("A", "Run 1 msg", run_id="run-1")
    logs.info("B", "Run 2 msg", run_id="run-2")
    logs.error("A", "Run 1 error", run_id="run-1")

    run1 = logs.get_run_logs("run-1")
    assert len(run1) == 2
    assert all(e["run_id"] == "run-1" for e in run1)
    print("OK: get run logs")


def test_get_run_logs_filtered():
    """Get run logs filtered by level."""
    logs = LogAggregator()
    logs.info("A", "Info", run_id="run-1")
    logs.error("A", "Error", run_id="run-1")
    logs.debug("A", "Debug", run_id="run-1")

    errors = logs.get_run_logs("run-1", level="error")
    assert len(errors) == 1
    assert errors[0]["level"] == "error"
    print("OK: get run logs filtered")


def test_get_source_logs():
    """Get logs from a specific source."""
    logs = LogAggregator()
    logs.info("Builder", "Msg 1")
    logs.info("Tester", "Msg 2")
    logs.error("Builder", "Msg 3")

    builder = logs.get_source_logs("Builder")
    assert len(builder) == 2
    assert all(e["source"] == "Builder" for e in builder)
    print("OK: get source logs")


def test_get_recent_by_level():
    """Get recent logs filtered by minimum level."""
    logs = LogAggregator()
    logs.debug("A", "Debug")
    logs.info("A", "Info")
    logs.warning("A", "Warning")
    logs.error("A", "Error")

    warnings_up = logs.get_recent(level="warning")
    assert len(warnings_up) == 2
    assert all(e["level"] in ("warning", "error", "critical") for e in warnings_up)
    print("OK: get recent by level")


def test_get_errors():
    """Get error entries."""
    logs = LogAggregator()
    logs.info("A", "Fine")
    logs.error("A", "Bad thing")
    logs.critical("A", "Very bad thing")

    errors = logs.get_errors()
    assert len(errors) == 2
    print("OK: get errors")


def test_search():
    """Full-text search across logs."""
    logs = LogAggregator()
    logs.info("Builder", "Generating Python code for API")
    logs.info("Tester", "Running pytest suite")
    logs.error("Builder", "Failed to generate code: syntax error")
    logs.info("Deployer", "Deploying to staging")

    results = logs.search("code")
    assert len(results) == 2
    assert all("code" in r["message"].lower() for r in results)
    print("OK: search")


def test_search_by_source():
    """Search scoped to a source."""
    logs = LogAggregator()
    logs.info("Builder", "Code ready")
    logs.info("Tester", "Code tested")

    results = logs.search("Code", source="Builder")
    assert len(results) == 1
    assert results[0]["source"] == "Builder"
    print("OK: search by source")


def test_search_by_level():
    """Search filtered by minimum level."""
    logs = LogAggregator()
    logs.info("A", "Found issue")
    logs.error("A", "Found critical issue")

    results = logs.search("issue", level="error")
    assert len(results) == 1
    assert results[0]["level"] == "error"
    print("OK: search by level")


def test_search_by_run():
    """Search within a specific run."""
    logs = LogAggregator()
    logs.info("A", "Processing data", run_id="run-1")
    logs.info("A", "Processing data", run_id="run-2")

    results = logs.search("data", run_id="run-1")
    assert len(results) == 1
    assert results[0]["run_id"] == "run-1"
    print("OK: search by run")


def test_time_range_query():
    """Query logs within a time range."""
    logs = LogAggregator()
    t1 = time.time()
    logs.info("A", "Before")
    time.sleep(0.02)
    t2 = time.time()
    logs.info("A", "After")

    results = logs.get_logs_in_range(t2)
    assert len(results) == 1
    assert results[0]["message"] == "After"
    print("OK: time range query")


def test_run_summary():
    """Get summary of a pipeline run."""
    logs = LogAggregator()
    logs.info("Builder", "Started", run_id="run-1")
    logs.info("Tester", "Testing", run_id="run-1")
    logs.error("Builder", "Build failed", run_id="run-1")
    logs.warning("Tester", "Flaky test", run_id="run-1")

    summary = logs.get_run_summary("run-1")
    assert summary["total_entries"] == 4
    assert summary["error_count"] == 1
    assert "Builder" in summary["sources"]
    assert "Tester" in summary["sources"]
    assert summary["level_counts"]["info"] == 2
    assert summary["level_counts"]["error"] == 1
    print("OK: run summary")


def test_empty_run_summary():
    """Summary for non-existent run."""
    logs = LogAggregator()
    summary = logs.get_run_summary("nope")
    assert summary["total_entries"] == 0
    print("OK: empty run summary")


def test_list_runs():
    """List all run IDs."""
    logs = LogAggregator()
    logs.info("A", "msg", run_id="run-1")
    logs.info("A", "msg", run_id="run-2")
    logs.info("A", "msg", run_id="run-1")

    runs = logs.list_runs()
    assert runs == ["run-1", "run-2"]
    print("OK: list runs")


def test_list_sources():
    """List all sources."""
    logs = LogAggregator()
    logs.info("Builder", "msg")
    logs.info("Tester", "msg")
    logs.info("Deployer", "msg")

    sources = logs.list_sources()
    assert sources == ["Builder", "Deployer", "Tester"]
    print("OK: list sources")


def test_max_entries_pruning():
    """Logs are pruned when over limit."""
    logs = LogAggregator(max_entries=10)

    for i in range(20):
        logs.info("Agent", f"Entry {i}", run_id="run-1")

    recent = logs.get_recent(limit=100)
    assert len(recent) <= 10

    stats = logs.get_stats()
    assert stats["total_pruned"] >= 10
    print("OK: max entries pruning")


def test_export_run():
    """Export all logs for a run."""
    logs = LogAggregator()
    logs.info("A", "First", run_id="run-1")
    logs.error("A", "Second", run_id="run-1")

    exported = logs.export_run("run-1")
    assert len(exported) == 2
    print("OK: export run")


def test_metadata():
    """Log entries can carry metadata."""
    logs = LogAggregator()
    logs.log("Builder", "info", "Built module",
             metadata={"module": "auth", "lines": 150})

    recent = logs.get_recent()
    assert recent[0]["metadata"]["module"] == "auth"
    assert recent[0]["metadata"]["lines"] == 150
    print("OK: metadata")


def test_stats():
    """Stats are accurate."""
    logs = LogAggregator()
    logs.info("A", "msg", run_id="run-1")
    logs.error("B", "err", run_id="run-1")
    logs.info("A", "msg")

    stats = logs.get_stats()
    assert stats["total_entries"] == 3
    assert stats["total_logged"] == 3
    assert stats["level_counts"]["info"] == 2
    assert stats["level_counts"]["error"] == 1
    assert stats["run_count"] == 1
    assert stats["source_count"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    logs = LogAggregator()
    logs.info("A", "msg")
    logs.reset()

    assert logs.get_recent() == []
    stats = logs.get_stats()
    assert stats["total_entries"] == 0
    assert stats["total_logged"] == 0
    print("OK: reset")


def main():
    print("=== Log Aggregator Tests ===\n")
    test_basic_log()
    test_convenience_methods()
    test_get_run_logs()
    test_get_run_logs_filtered()
    test_get_source_logs()
    test_get_recent_by_level()
    test_get_errors()
    test_search()
    test_search_by_source()
    test_search_by_level()
    test_search_by_run()
    test_time_range_query()
    test_run_summary()
    test_empty_run_summary()
    test_list_runs()
    test_list_sources()
    test_max_entries_pruning()
    test_export_run()
    test_metadata()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
