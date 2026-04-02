"""Test agent performance monitor."""
import sys
sys.path.insert(0, ".")

from src.services.agent_performance_monitor import AgentPerformanceMonitor


def test_record_metric():
    """Record and retrieve metric."""
    pm = AgentPerformanceMonitor()
    mid = pm.record_metric("agent-1", "latency", 150.0,
                           unit="ms", operation="build",
                           tags=["ci"])
    assert mid.startswith("pm-")

    m = pm.get_metric(mid)
    assert m is not None
    assert m["agent"] == "agent-1"
    assert m["metric_type"] == "latency"
    assert m["value"] == 150.0
    assert m["unit"] == "ms"
    assert m["operation"] == "build"

    assert pm.remove_metric(mid) is True
    assert pm.remove_metric(mid) is False
    print("OK: record metric")


def test_invalid_metric():
    """Invalid metric rejected."""
    pm = AgentPerformanceMonitor()
    assert pm.record_metric("", "latency", 1.0) == ""
    assert pm.record_metric("a", "", 1.0) == ""
    assert pm.record_metric("a", "invalid", 1.0) == ""
    print("OK: invalid metric")


def test_create_benchmark():
    """Create and manage benchmark."""
    pm = AgentPerformanceMonitor()
    bid = pm.create_benchmark("build_speed", "latency",
                              target_value=100.0, threshold_value=500.0,
                              agent="agent-1", unit="ms", tags=["ci"])
    assert bid.startswith("bm-")

    b = pm.get_benchmark(bid)
    assert b is not None
    assert b["name"] == "build_speed"
    assert b["metric_type"] == "latency"
    assert b["target_value"] == 100.0
    assert b["threshold_value"] == 500.0
    assert b["status"] == "active"

    assert pm.remove_benchmark(bid) is True
    assert pm.remove_benchmark(bid) is False
    print("OK: create benchmark")


def test_invalid_benchmark():
    """Invalid benchmark rejected."""
    pm = AgentPerformanceMonitor()
    assert pm.create_benchmark("", "latency", 1, 2) == ""
    assert pm.create_benchmark("n", "", 1, 2) == ""
    assert pm.create_benchmark("n", "invalid", 1, 2) == ""
    print("OK: invalid benchmark")


def test_max_benchmarks():
    """Max benchmarks enforced."""
    pm = AgentPerformanceMonitor(max_benchmarks=2)
    pm.create_benchmark("a", "latency", 1, 2)
    pm.create_benchmark("b", "latency", 1, 2)
    assert pm.create_benchmark("c", "latency", 1, 2) == ""
    print("OK: max benchmarks")


def test_disable_enable_benchmark():
    """Disable and enable benchmark."""
    pm = AgentPerformanceMonitor()
    bid = pm.create_benchmark("t", "latency", 1, 2)

    assert pm.disable_benchmark(bid) is True
    assert pm.get_benchmark(bid)["status"] == "disabled"
    assert pm.disable_benchmark(bid) is False

    assert pm.enable_benchmark(bid) is True
    assert pm.get_benchmark(bid)["status"] == "active"
    assert pm.enable_benchmark(bid) is False
    print("OK: disable enable benchmark")


def test_threshold_violation():
    """Benchmark threshold violation detected."""
    pm = AgentPerformanceMonitor()
    fired = []
    pm.on_change("mon", lambda a, d: fired.append(a))

    pm.create_benchmark("speed", "latency",
                         target_value=100, threshold_value=500)

    pm.record_metric("agent-1", "latency", 200)  # under threshold
    assert "threshold_violated" not in fired

    pm.record_metric("agent-1", "latency", 600)  # over threshold
    assert "threshold_violated" in fired
    print("OK: threshold violation")


def test_disabled_benchmark_no_violation():
    """Disabled benchmark doesn't trigger violations."""
    pm = AgentPerformanceMonitor()
    bid = pm.create_benchmark("speed", "latency",
                               target_value=100, threshold_value=500)
    pm.disable_benchmark(bid)

    pm.record_metric("agent-1", "latency", 600)
    assert pm.get_stats()["total_threshold_violations"] == 0
    print("OK: disabled benchmark no violation")


def test_search_metrics():
    """Search metrics with filters."""
    pm = AgentPerformanceMonitor()
    pm.record_metric("alice", "latency", 100, operation="build", tags=["ci"])
    pm.record_metric("bob", "throughput", 50, operation="test")
    pm.record_metric("alice", "memory", 256, operation="build")

    by_agent = pm.search_metrics(agent="alice")
    assert len(by_agent) == 2

    by_type = pm.search_metrics(metric_type="throughput")
    assert len(by_type) == 1

    by_op = pm.search_metrics(operation="build")
    assert len(by_op) == 2

    by_tag = pm.search_metrics(tag="ci")
    assert len(by_tag) == 1
    print("OK: search metrics")


def test_search_limit():
    """Search respects limit."""
    pm = AgentPerformanceMonitor()
    for i in range(20):
        pm.record_metric("a", "latency", float(i))

    results = pm.search_metrics(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_agent_summary():
    """Get agent performance summary."""
    pm = AgentPerformanceMonitor()
    pm.record_metric("alice", "latency", 100)
    pm.record_metric("alice", "latency", 200)
    pm.record_metric("alice", "memory", 512)

    summary = pm.get_agent_summary("alice")
    assert summary["agent"] == "alice"
    assert summary["metrics"]["latency"]["count"] == 2
    assert summary["metrics"]["latency"]["min"] == 100
    assert summary["metrics"]["latency"]["max"] == 200
    assert summary["metrics"]["latency"]["avg"] == 150.0
    assert summary["metrics"]["memory"]["count"] == 1
    print("OK: agent summary")


def test_metric_averages():
    """Get metric averages per agent."""
    pm = AgentPerformanceMonitor()
    pm.record_metric("alice", "latency", 100)
    pm.record_metric("alice", "latency", 200)
    pm.record_metric("bob", "latency", 50)

    avgs = pm.get_metric_averages("latency")
    assert len(avgs) == 2
    # Sorted by avg ascending
    assert avgs[0]["agent"] == "bob"
    assert avgs[0]["avg"] == 50.0
    assert avgs[1]["agent"] == "alice"
    assert avgs[1]["avg"] == 150.0
    print("OK: metric averages")


def test_list_benchmarks():
    """List benchmarks with filters."""
    pm = AgentPerformanceMonitor()
    pm.create_benchmark("a", "latency", 1, 2, tags=["ci"])
    b2 = pm.create_benchmark("b", "memory", 1, 2)
    pm.disable_benchmark(b2)

    all_b = pm.list_benchmarks()
    assert len(all_b) == 2

    active = pm.list_benchmarks(status="active")
    assert len(active) == 1

    by_tag = pm.list_benchmarks(tag="ci")
    assert len(by_tag) == 1
    print("OK: list benchmarks")


def test_metric_callback():
    """Callback fires on metric record."""
    pm = AgentPerformanceMonitor()
    fired = []
    pm.on_change("mon", lambda a, d: fired.append(a))

    pm.record_metric("a", "latency", 1.0)
    assert "metric_recorded" in fired
    print("OK: metric callback")


def test_callbacks():
    """Callback registration."""
    pm = AgentPerformanceMonitor()
    assert pm.on_change("mon", lambda a, d: None) is True
    assert pm.on_change("mon", lambda a, d: None) is False
    assert pm.remove_callback("mon") is True
    assert pm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    pm = AgentPerformanceMonitor()
    pm.record_metric("a", "latency", 1.0)
    pm.record_metric("a", "latency", 2.0)
    pm.create_benchmark("b", "latency", 1, 1.5)
    pm.record_metric("a", "latency", 2.0)  # violates threshold

    stats = pm.get_stats()
    assert stats["total_metrics_recorded"] == 3
    assert stats["total_benchmarks_created"] == 1
    assert stats["total_threshold_violations"] == 1
    assert stats["current_metrics"] == 3
    assert stats["current_benchmarks"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    pm = AgentPerformanceMonitor()
    pm.record_metric("a", "latency", 1.0)
    pm.create_benchmark("b", "latency", 1, 2)

    pm.reset()
    assert pm.search_metrics() == []
    assert pm.list_benchmarks() == []
    stats = pm.get_stats()
    assert stats["current_metrics"] == 0
    print("OK: reset")


def main():
    print("=== Agent Performance Monitor Tests ===\n")
    test_record_metric()
    test_invalid_metric()
    test_create_benchmark()
    test_invalid_benchmark()
    test_max_benchmarks()
    test_disable_enable_benchmark()
    test_threshold_violation()
    test_disabled_benchmark_no_violation()
    test_search_metrics()
    test_search_limit()
    test_agent_summary()
    test_metric_averages()
    test_list_benchmarks()
    test_metric_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
