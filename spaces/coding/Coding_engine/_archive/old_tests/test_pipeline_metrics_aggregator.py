"""Test pipeline metrics aggregator."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_metrics_aggregator import PipelineMetricsAggregator


def test_register():
    """Register and unregister metrics."""
    agg = PipelineMetricsAggregator()
    assert agg.register("cpu_usage", metric_type="gauge", namespace="system",
                         unit="percent", description="CPU usage") is True
    assert agg.register("cpu_usage", namespace="system") is False  # dup

    m = agg.get_metric("cpu_usage", namespace="system")
    assert m is not None
    assert m["metric_type"] == "gauge"
    assert m["unit"] == "percent"

    assert agg.unregister("cpu_usage", namespace="system") is True
    assert agg.unregister("cpu_usage", namespace="system") is False
    print("OK: register")


def test_record_gauge():
    """Record gauge values."""
    agg = PipelineMetricsAggregator()
    agg.register("temperature", metric_type="gauge")

    assert agg.record("temperature", 72.5) is True
    assert agg.get_current("temperature") == 72.5

    agg.record("temperature", 73.0)
    assert agg.get_current("temperature") == 73.0
    print("OK: record gauge")


def test_record_auto_register():
    """Auto-register on first record."""
    agg = PipelineMetricsAggregator()
    assert agg.record("new_metric", 42.0) is True
    assert agg.get_current("new_metric") == 42.0
    print("OK: record auto register")


def test_record_counter():
    """Counter only increments."""
    agg = PipelineMetricsAggregator()
    agg.register("requests", metric_type="counter")

    assert agg.record("requests", 5.0) is True
    assert agg.get_current("requests") == 5.0

    assert agg.record("requests", 3.0) is True
    assert agg.get_current("requests") == 8.0

    # Negative not allowed
    assert agg.record("requests", -1.0) is False
    print("OK: record counter")


def test_increment():
    """Increment counter."""
    agg = PipelineMetricsAggregator()
    agg.register("hits", metric_type="counter")

    assert agg.increment("hits") is True
    assert agg.get_current("hits") == 1.0

    assert agg.increment("hits", 5.0) is True
    assert agg.get_current("hits") == 6.0

    # Auto-register as counter
    assert agg.increment("new_counter") is True
    assert agg.get_current("new_counter") == 1.0

    # Can't increment non-counter
    agg.register("gauge_metric", metric_type="gauge")
    assert agg.increment("gauge_metric") is False
    print("OK: increment")


def test_timer():
    """Timer records duration."""
    agg = PipelineMetricsAggregator()

    tid = agg.time_start("build_time")
    assert tid.startswith("tmr-")

    time.sleep(0.02)
    duration = agg.time_stop(tid)
    assert duration is not None
    assert duration >= 0.01

    current = agg.get_current("build_time")
    assert current is not None
    assert current >= 0.01

    # Invalid timer
    assert agg.time_stop("fake") is None
    print("OK: timer")


def test_get_current_none():
    """Get current for nonexistent metric."""
    agg = PipelineMetricsAggregator()
    assert agg.get_current("nonexistent") is None
    print("OK: get current none")


def test_get_history():
    """Get metric history."""
    agg = PipelineMetricsAggregator()
    now = time.time()
    agg.register("cpu")

    agg.record("cpu", 50.0, timestamp=now - 10)
    agg.record("cpu", 60.0, timestamp=now - 5)
    agg.record("cpu", 70.0, timestamp=now)

    history = agg.get_history("cpu")
    assert len(history) == 3
    assert history[0]["value"] == 50.0

    # With since filter
    recent = agg.get_history("cpu", since=now - 6)
    assert len(recent) == 2

    # With limit
    limited = agg.get_history("cpu", limit=1)
    assert len(limited) == 1
    assert limited[0]["value"] == 70.0  # Last one

    # Nonexistent
    assert agg.get_history("fake") == []
    print("OK: get history")


def test_aggregate():
    """Aggregate over time window."""
    agg = PipelineMetricsAggregator()
    now = time.time()
    agg.register("latency")

    for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
        agg.record("latency", v, timestamp=now)

    result = agg.aggregate("latency", window_seconds=60.0)
    assert result is not None
    assert result["count"] == 5
    assert result["min"] == 10.0
    assert result["max"] == 50.0
    assert result["avg"] == 30.0
    assert result["sum"] == 150.0
    assert result["p50"] == 30.0

    # Nonexistent
    assert agg.aggregate("fake") is None
    print("OK: aggregate")


def test_aggregate_empty_window():
    """Aggregate with no data in window."""
    agg = PipelineMetricsAggregator()
    agg.register("old_metric")
    agg.record("old_metric", 100.0, timestamp=1.0)  # Very old timestamp

    result = agg.aggregate("old_metric", window_seconds=1.0)
    assert result["count"] == 0
    print("OK: aggregate empty window")


def test_list_metrics():
    """List metrics with filters."""
    agg = PipelineMetricsAggregator()
    agg.register("cpu", metric_type="gauge", namespace="system")
    agg.register("memory", metric_type="gauge", namespace="system")
    agg.register("requests", metric_type="counter", namespace="api")

    all_m = agg.list_metrics()
    assert len(all_m) == 3

    system = agg.list_metrics(namespace="system")
    assert len(system) == 2

    counters = agg.list_metrics(metric_type="counter")
    assert len(counters) == 1

    limited = agg.list_metrics(limit=1)
    assert len(limited) == 1
    print("OK: list metrics")


def test_list_namespaces():
    """List namespaces."""
    agg = PipelineMetricsAggregator()
    agg.register("a", namespace="system")
    agg.register("b", namespace="api")
    agg.register("c", namespace="system")

    ns = agg.list_namespaces()
    assert ns["system"] == 2
    assert ns["api"] == 1
    print("OK: list namespaces")


def test_snapshot():
    """Snapshot of current values."""
    agg = PipelineMetricsAggregator()
    agg.register("cpu", namespace="system")
    agg.register("memory", namespace="system")
    agg.register("requests", namespace="api")

    agg.record("cpu", 75.0, namespace="system")
    agg.record("memory", 4096.0, namespace="system")
    agg.record("requests", 100.0, namespace="api")

    snap = agg.snapshot()
    assert len(snap) == 3
    assert snap["system:cpu"]["value"] == 75.0

    system_snap = agg.snapshot(namespace="system")
    assert len(system_snap) == 2
    print("OK: snapshot")


def test_alert_trigger():
    """Alert triggers on threshold."""
    triggered = []

    def on_alert(rule_id, name, ns, value):
        triggered.append({"rule_id": rule_id, "name": name, "value": value})

    agg = PipelineMetricsAggregator()
    agg.register("cpu", namespace="system")
    rid = agg.add_alert("cpu", "gt", 80.0, namespace="system",
                         window_seconds=60.0, cooldown_seconds=0.0,
                         callback=on_alert)
    assert rid.startswith("alrt-")

    # Below threshold — only this value, avg = 50
    agg.record("cpu", 50.0, namespace="system")
    assert len(triggered) == 0

    # Above threshold — record enough high values to push avg above 80
    agg.record("cpu", 95.0, namespace="system")
    agg.record("cpu", 95.0, namespace="system")
    agg.record("cpu", 95.0, namespace="system")
    assert len(triggered) == 1
    assert triggered[0]["name"] == "cpu"
    print("OK: alert trigger")


def test_alert_cooldown():
    """Alert respects cooldown."""
    triggered = []

    def on_alert(rule_id, name, ns, value):
        triggered.append(True)

    agg = PipelineMetricsAggregator()
    agg.register("cpu")
    agg.add_alert("cpu", "gt", 50.0, cooldown_seconds=999.0, callback=on_alert)

    agg.record("cpu", 90.0)
    agg.record("cpu", 95.0)  # Should be cooldown
    assert len(triggered) == 1
    print("OK: alert cooldown")


def test_alert_crud():
    """Alert CRUD operations."""
    agg = PipelineMetricsAggregator()
    rid = agg.add_alert("cpu", "gt", 80.0)

    alerts = agg.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["condition"] == "gt"

    assert agg.disable_alert(rid) is True
    assert agg.list_alerts()[0]["enabled"] is False
    assert agg.enable_alert(rid) is True
    assert agg.list_alerts()[0]["enabled"] is True

    assert agg.remove_alert(rid) is True
    assert agg.remove_alert(rid) is False
    assert len(agg.list_alerts()) == 0

    assert agg.enable_alert("fake") is False
    assert agg.disable_alert("fake") is False
    print("OK: alert crud")


def test_namespaced_metrics():
    """Same name, different namespace."""
    agg = PipelineMetricsAggregator()
    agg.register("latency", namespace="api")
    agg.register("latency", namespace="db")

    agg.record("latency", 10.0, namespace="api")
    agg.record("latency", 50.0, namespace="db")

    assert agg.get_current("latency", namespace="api") == 10.0
    assert agg.get_current("latency", namespace="db") == 50.0
    print("OK: namespaced metrics")


def test_percentiles():
    """Percentile calculation."""
    agg = PipelineMetricsAggregator()
    now = time.time()
    agg.register("response_time")

    # Record 100 values 1..100
    for i in range(1, 101):
        agg.record("response_time", float(i), timestamp=now)

    result = agg.aggregate("response_time", window_seconds=60.0)
    assert result["p50"] == 50.5
    assert result["p95"] >= 95.0
    assert result["p99"] >= 99.0
    print("OK: percentiles")


def test_stats():
    """Stats are accurate."""
    agg = PipelineMetricsAggregator()
    agg.register("a", namespace="x")
    agg.register("b", namespace="y")
    agg.record("a", 1.0, namespace="x")
    agg.record("b", 2.0, namespace="y")

    rid = agg.add_alert("a", "gt", 0.0, namespace="x", cooldown_seconds=0.0)

    # Trigger alert
    agg.record("a", 5.0, namespace="x")

    stats = agg.get_stats()
    assert stats["total_metrics"] == 2
    assert stats["total_recorded"] == 3
    assert stats["total_alerts"] == 1
    assert stats["total_alerts_triggered"] >= 1
    assert stats["total_namespaces"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    agg = PipelineMetricsAggregator()
    agg.register("cpu")
    agg.record("cpu", 50.0)
    agg.add_alert("cpu", "gt", 80.0)

    agg.reset()
    assert agg.list_metrics() == []
    assert agg.list_alerts() == []
    stats = agg.get_stats()
    assert stats["total_metrics"] == 0
    assert stats["total_recorded"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Metrics Aggregator Tests ===\n")
    test_register()
    test_record_gauge()
    test_record_auto_register()
    test_record_counter()
    test_increment()
    test_timer()
    test_get_current_none()
    test_get_history()
    test_aggregate()
    test_aggregate_empty_window()
    test_list_metrics()
    test_list_namespaces()
    test_snapshot()
    test_alert_trigger()
    test_alert_cooldown()
    test_alert_crud()
    test_namespaced_metrics()
    test_percentiles()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
