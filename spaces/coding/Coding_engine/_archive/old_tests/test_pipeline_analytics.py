"""Test pipeline analytics."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_analytics import PipelineAnalytics, RunStatus


def test_start_run():
    """Start a pipeline run."""
    analytics = PipelineAnalytics()
    rid = analytics.start_run("myproject", tags={"nightly"}, metadata={"branch": "main"})
    assert rid.startswith("run-")

    run = analytics.get_run(rid)
    assert run is not None
    assert run["project"] == "myproject"
    assert run["status"] == "running"
    assert "nightly" in run["tags"]
    assert run["metrics"]["branch"] == "main"
    print("OK: start run")


def test_end_run_completed():
    """End a run as completed."""
    analytics = PipelineAnalytics()
    rid = analytics.start_run("proj")
    assert analytics.end_run(rid, status="completed") is True

    run = analytics.get_run(rid)
    assert run["status"] == "completed"
    assert run["ended_at"] > 0
    assert run["duration_seconds"] >= 0
    print("OK: end run completed")


def test_end_run_failed():
    """End a run as failed."""
    analytics = PipelineAnalytics()
    rid = analytics.start_run("proj")
    assert analytics.end_run(rid, status="failed", error="OOM") is True

    run = analytics.get_run(rid)
    assert run["status"] == "failed"
    assert run["error"] == "OOM"
    print("OK: end run failed")


def test_end_run_invalid():
    """End run with invalid id or already ended."""
    analytics = PipelineAnalytics()
    assert analytics.end_run("fake-id") is False

    rid = analytics.start_run("proj")
    analytics.end_run(rid)
    assert analytics.end_run(rid) is False  # Already ended
    print("OK: end run invalid")


def test_list_runs():
    """List runs with filters."""
    analytics = PipelineAnalytics()
    r1 = analytics.start_run("alpha")
    r2 = analytics.start_run("beta")
    r3 = analytics.start_run("alpha")
    analytics.end_run(r1, status="completed")
    analytics.end_run(r2, status="failed")

    all_runs = analytics.list_runs()
    assert len(all_runs) == 3

    alpha_runs = analytics.list_runs(project="alpha")
    assert len(alpha_runs) == 2

    completed = analytics.list_runs(status="completed")
    assert len(completed) == 1
    assert completed[0]["run_id"] == r1

    limited = analytics.list_runs(limit=2)
    assert len(limited) == 2
    print("OK: list runs")


def test_record_phase():
    """Record phase within a run."""
    analytics = PipelineAnalytics()
    rid = analytics.start_run("proj")

    assert analytics.record_phase(rid, "build", 12.5, status="completed") is True
    assert analytics.record_phase(rid, "test", 8.3, status="failed",
                                   metadata={"failures": 2}) is True
    assert analytics.record_phase("fake", "x", 1.0) is False

    run = analytics.get_run(rid)
    assert "build" in run["phases"]
    assert run["phases"]["build"]["duration_seconds"] == 12.5
    assert run["phases"]["test"]["status"] == "failed"
    print("OK: record phase")


def test_record_agent_time():
    """Record agent contribution time."""
    analytics = PipelineAnalytics()
    rid = analytics.start_run("proj")

    assert analytics.record_agent_time(rid, "Builder", 5.0) is True
    assert analytics.record_agent_time(rid, "Builder", 3.0) is True  # Accumulates
    assert analytics.record_agent_time(rid, "Tester", 2.0) is True
    assert analytics.record_agent_time("fake", "X", 1.0) is False

    run = analytics.get_run(rid)
    assert run["agent_times"]["Builder"] == 8.0
    assert run["agent_times"]["Tester"] == 2.0
    print("OK: record agent time")


def test_record_metric():
    """Record custom metrics."""
    analytics = PipelineAnalytics()
    analytics.record_metric("build_time", 12.5, labels={"project": "alpha"})
    analytics.record_metric("build_time", 14.2, labels={"project": "alpha"})
    analytics.record_metric("test_coverage", 85.0)

    series = analytics.get_metric_series("build_time")
    assert len(series) == 2
    assert series[0]["value"] == 12.5
    assert series[1]["value"] == 14.2
    print("OK: record metric")


def test_get_metric_series_filters():
    """Get metric series with filters."""
    analytics = PipelineAnalytics()
    now = time.time()

    analytics.record_metric("m", 1.0, labels={"env": "dev"}, timestamp=now - 100)
    analytics.record_metric("m", 2.0, labels={"env": "prod"}, timestamp=now - 50)
    analytics.record_metric("m", 3.0, labels={"env": "dev"}, timestamp=now)

    # Filter by label
    dev = analytics.get_metric_series("m", labels={"env": "dev"})
    assert len(dev) == 2

    # Filter by time
    recent = analytics.get_metric_series("m", since=now - 60)
    assert len(recent) == 2

    # Limit
    limited = analytics.get_metric_series("m", limit=1)
    assert len(limited) == 1
    print("OK: get metric series filters")


def test_counters():
    """Increment and get counters."""
    analytics = PipelineAnalytics()
    assert analytics.increment_counter("builds") == 1
    assert analytics.increment_counter("builds") == 2
    assert analytics.increment_counter("builds", 5) == 7
    assert analytics.get_counter("builds") == 7
    assert analytics.get_counter("nonexistent") == 0

    counters = analytics.list_counters()
    assert counters["builds"] == 7
    print("OK: counters")


def test_project_summary():
    """Get project summary."""
    analytics = PipelineAnalytics()

    # Empty project
    empty = analytics.get_project_summary("empty")
    assert empty["total_runs"] == 0

    # With data
    r1 = analytics.start_run("proj")
    time.sleep(0.01)
    analytics.end_run(r1, status="completed")

    r2 = analytics.start_run("proj")
    time.sleep(0.01)
    analytics.end_run(r2, status="completed")

    r3 = analytics.start_run("proj")
    analytics.end_run(r3, status="failed", error="boom")

    summary = analytics.get_project_summary("proj")
    assert summary["total_runs"] == 3
    assert summary["completed"] == 2
    assert summary["failed"] == 1
    assert summary["success_rate"] > 0
    assert summary["avg_duration_seconds"] >= 0
    print("OK: project summary")


def test_agent_performance():
    """Get aggregate agent performance."""
    analytics = PipelineAnalytics()

    r1 = analytics.start_run("proj")
    analytics.record_agent_time(r1, "Builder", 10.0)
    analytics.record_agent_time(r1, "Tester", 5.0)

    r2 = analytics.start_run("proj")
    analytics.record_agent_time(r2, "Builder", 8.0)

    perf = analytics.get_agent_performance()
    assert len(perf) == 2
    assert perf[0]["agent_name"] == "Builder"  # Most total time
    assert perf[0]["total_time_seconds"] == 18.0
    assert perf[0]["run_count"] == 2
    assert perf[0]["avg_time_seconds"] == 9.0
    print("OK: agent performance")


def test_phase_performance():
    """Get aggregate phase performance."""
    analytics = PipelineAnalytics()

    r1 = analytics.start_run("proj")
    analytics.record_phase(r1, "build", 10.0)
    analytics.record_phase(r1, "test", 5.0, status="failed")

    r2 = analytics.start_run("proj")
    analytics.record_phase(r2, "build", 12.0)
    analytics.record_phase(r2, "test", 6.0)

    perf = analytics.get_phase_performance()
    assert len(perf) == 2

    build = [p for p in perf if p["phase"] == "build"][0]
    assert build["total_time_seconds"] == 22.0
    assert build["count"] == 2
    assert build["failure_rate"] == 0.0

    test = [p for p in perf if p["phase"] == "test"][0]
    assert test["failure_rate"] == 50.0
    print("OK: phase performance")


def test_throughput():
    """Get pipeline throughput."""
    analytics = PipelineAnalytics()

    r1 = analytics.start_run("proj")
    analytics.end_run(r1, status="completed")
    r2 = analytics.start_run("proj")
    analytics.end_run(r2, status="failed")
    analytics.start_run("proj")  # Still running

    tp = analytics.get_throughput(window_seconds=3600.0)
    assert tp["total_runs"] == 3
    assert tp["completed"] == 1
    assert tp["failed"] == 1
    assert tp["runs_per_hour"] > 0
    print("OK: throughput")


def test_get_trend():
    """Get metric trend over buckets."""
    analytics = PipelineAnalytics()
    now = time.time()

    # Add metrics in different time buckets
    # Bucket layout (2 buckets of 3600s): [now-7200..now-3600] [now-3600..now]
    analytics.record_metric("latency", 100.0, timestamp=now - 5000)
    analytics.record_metric("latency", 120.0, timestamp=now - 4500)
    analytics.record_metric("latency", 80.0, timestamp=now - 100)

    trend = analytics.get_trend("latency", bucket_seconds=3600.0, num_buckets=2)
    assert len(trend) == 2
    # First bucket (older) should have 2 points
    assert trend[0]["count"] == 2
    # Second bucket (recent) should have 1 point
    assert trend[1]["count"] == 1
    print("OK: get trend")


def test_list_projects():
    """List all projects."""
    analytics = PipelineAnalytics()
    analytics.start_run("beta")
    analytics.start_run("alpha")
    analytics.start_run("beta")

    projects = analytics.list_projects()
    assert projects == ["alpha", "beta"]
    print("OK: list projects")


def test_prune_runs():
    """Runs are pruned when over limit."""
    analytics = PipelineAnalytics(max_runs=5)
    for i in range(10):
        rid = analytics.start_run(f"proj-{i}")
        analytics.end_run(rid, status="completed")

    assert len(analytics._runs) <= 5
    print("OK: prune runs")


def test_prune_metrics():
    """Metrics are pruned when over limit."""
    analytics = PipelineAnalytics(max_metrics=10)
    for i in range(20):
        analytics.record_metric("m", float(i))

    assert len(analytics._metrics) <= 10
    print("OK: prune metrics")


def test_stats():
    """Stats are accurate."""
    analytics = PipelineAnalytics()
    r1 = analytics.start_run("proj")
    analytics.end_run(r1, status="completed")
    r2 = analytics.start_run("proj")
    analytics.end_run(r2, status="failed")
    analytics.record_metric("x", 1.0)

    stats = analytics.get_stats()
    assert stats["total_runs_started"] == 2
    assert stats["total_runs_completed"] == 1
    assert stats["total_runs_failed"] == 1
    assert stats["total_metrics_recorded"] == 1
    assert stats["total_runs"] == 2
    assert stats["total_metrics"] == 1
    assert stats["total_projects"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    analytics = PipelineAnalytics()
    analytics.start_run("proj")
    analytics.record_metric("x", 1.0)
    analytics.increment_counter("builds")

    analytics.reset()
    assert analytics.list_runs() == []
    assert analytics.list_counters() == {}
    stats = analytics.get_stats()
    assert stats["total_runs"] == 0
    assert stats["total_metrics"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Analytics Tests ===\n")
    test_start_run()
    test_end_run_completed()
    test_end_run_failed()
    test_end_run_invalid()
    test_list_runs()
    test_record_phase()
    test_record_agent_time()
    test_record_metric()
    test_get_metric_series_filters()
    test_counters()
    test_project_summary()
    test_agent_performance()
    test_phase_performance()
    test_throughput()
    test_get_trend()
    test_list_projects()
    test_prune_runs()
    test_prune_metrics()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
