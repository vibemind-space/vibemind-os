"""Test agent metric collector."""
import sys
sys.path.insert(0, ".")

from src.services.agent_metric_collector import AgentMetricCollector


def test_register_metric():
    """Register and retrieve metric."""
    mc = AgentMetricCollector()
    mid = mc.register_metric("latency", agent="worker", unit="ms", tags=["perf"])
    assert mid.startswith("met-")

    m = mc.get_metric(mid)
    assert m is not None
    assert m["name"] == "latency"
    assert m["agent"] == "worker"
    assert m["unit"] == "ms"

    assert mc.remove_metric(mid) is True
    assert mc.remove_metric(mid) is False
    print("OK: register metric")


def test_invalid_metric():
    """Invalid metric rejected."""
    mc = AgentMetricCollector()
    assert mc.register_metric("") == ""
    print("OK: invalid metric")


def test_duplicate():
    """Duplicate name+agent rejected."""
    mc = AgentMetricCollector()
    mc.register_metric("latency", agent="worker")
    assert mc.register_metric("latency", agent="worker") == ""
    print("OK: duplicate")


def test_max_metrics():
    """Max metrics enforced."""
    mc = AgentMetricCollector(max_metrics=2)
    mc.register_metric("a")
    mc.register_metric("b")
    assert mc.register_metric("c") == ""
    print("OK: max metrics")


def test_record():
    """Record samples."""
    mc = AgentMetricCollector()
    mid = mc.register_metric("latency")
    assert mc.record(mid, 10.5) is True
    assert mc.record(mid, 20.3) is True
    assert mc.get_metric(mid)["sample_count"] == 2
    assert mc.record("nonexistent", 1.0) is False
    print("OK: record")


def test_record_by_name():
    """Record by name."""
    mc = AgentMetricCollector()
    mc.register_metric("latency", agent="w1")
    assert mc.record_by_name("latency", 5.0, agent="w1") is True
    assert mc.record_by_name("nonexistent", 5.0) is False
    print("OK: record by name")


def test_aggregate():
    """Aggregate samples."""
    mc = AgentMetricCollector()
    mid = mc.register_metric("latency")
    mc.record(mid, 10.0)
    mc.record(mid, 20.0)
    mc.record(mid, 30.0)

    agg = mc.aggregate(mid)
    assert agg is not None
    assert agg["count"] == 3
    assert agg["min"] == 10.0
    assert agg["max"] == 30.0
    assert agg["sum"] == 60.0
    assert agg["avg"] == 20.0
    print("OK: aggregate")


def test_aggregate_empty():
    """Aggregate with no samples."""
    mc = AgentMetricCollector()
    mid = mc.register_metric("latency")
    assert mc.aggregate(mid) is None
    assert mc.aggregate("nonexistent") is None
    print("OK: aggregate empty")


def test_aggregate_window():
    """Aggregate with time window."""
    mc = AgentMetricCollector()
    mid = mc.register_metric("latency")
    mc.record(mid, 10.0)
    mc.record(mid, 20.0)

    # window large enough to include all
    agg = mc.aggregate(mid, window_ms=60000)
    assert agg is not None
    assert agg["count"] == 2
    print("OK: aggregate window")


def test_get_latest():
    """Get latest samples."""
    mc = AgentMetricCollector()
    mid = mc.register_metric("latency")
    mc.record(mid, 1.0)
    mc.record(mid, 2.0)
    mc.record(mid, 3.0)

    latest = mc.get_latest(mid, count=2)
    assert len(latest) == 2
    assert latest[0]["value"] == 2.0
    assert latest[1]["value"] == 3.0

    assert mc.get_latest("nonexistent") == []
    print("OK: get latest")


def test_get_by_name():
    """Get metric by name."""
    mc = AgentMetricCollector()
    mc.register_metric("latency", agent="w1")

    m = mc.get_metric_by_name("latency", agent="w1")
    assert m is not None
    assert m["name"] == "latency"
    assert mc.get_metric_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_metrics():
    """List metrics with filters."""
    mc = AgentMetricCollector()
    mc.register_metric("latency", agent="w1", tags=["perf"])
    mc.register_metric("throughput", agent="w2")

    all_m = mc.list_metrics()
    assert len(all_m) == 2

    by_agent = mc.list_metrics(agent="w1")
    assert len(by_agent) == 1

    by_tag = mc.list_metrics(tag="perf")
    assert len(by_tag) == 1

    by_name = mc.list_metrics(name="throughput")
    assert len(by_name) == 1
    print("OK: list metrics")


def test_sample_eviction():
    """Samples evict oldest when full."""
    mc = AgentMetricCollector(max_samples_per_metric=10)
    mid = mc.register_metric("latency")
    for i in range(15):
        mc.record(mid, float(i))
    assert mc.get_metric(mid)["sample_count"] <= 10
    print("OK: sample eviction")


def test_callback():
    """Callback fires on events."""
    mc = AgentMetricCollector()
    fired = []
    mc.on_change("mon", lambda a, d: fired.append(a))

    mid = mc.register_metric("latency")
    assert "metric_registered" in fired

    mc.record(mid, 10.0)
    assert "sample_recorded" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    mc = AgentMetricCollector()
    assert mc.on_change("mon", lambda a, d: None) is True
    assert mc.on_change("mon", lambda a, d: None) is False
    assert mc.remove_callback("mon") is True
    assert mc.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    mc = AgentMetricCollector()
    mid = mc.register_metric("latency")
    mc.record(mid, 10.0)
    mc.record(mid, 20.0)

    stats = mc.get_stats()
    assert stats["total_metrics"] == 1
    assert stats["total_samples"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mc = AgentMetricCollector()
    mc.register_metric("latency")

    mc.reset()
    assert mc.list_metrics() == []
    stats = mc.get_stats()
    assert stats["current_metrics"] == 0
    print("OK: reset")


def main():
    print("=== Agent Metric Collector Tests ===\n")
    test_register_metric()
    test_invalid_metric()
    test_duplicate()
    test_max_metrics()
    test_record()
    test_record_by_name()
    test_aggregate()
    test_aggregate_empty()
    test_aggregate_window()
    test_get_latest()
    test_get_by_name()
    test_list_metrics()
    test_sample_eviction()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
