"""Test pipeline metric collector -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_metric_collector import PipelineMetricCollector


def test_register_metric():
    mc = PipelineMetricCollector()
    mid = mc.register_metric("requests_total", metric_type="counter", tags=["api"])
    assert mid.startswith("pmc-")
    m = mc.get_metric("requests_total")
    assert m is not None
    assert m["name"] == "requests_total"
    assert mc.register_metric("requests_total") == ""  # dup
    print("OK: register metric")


def test_counter():
    mc = PipelineMetricCollector()
    mc.register_metric("hits", metric_type="counter")
    assert mc.increment("hits") is True
    assert mc.increment("hits", value=5.0) is True
    m = mc.get_metric("hits")
    assert m["value"] == 6.0
    print("OK: counter")


def test_gauge():
    mc = PipelineMetricCollector()
    mc.register_metric("cpu_usage", metric_type="gauge")
    assert mc.set_gauge("cpu_usage", 75.5) is True
    m = mc.get_metric("cpu_usage")
    assert m["value"] == 75.5
    mc.set_gauge("cpu_usage", 60.0)
    m2 = mc.get_metric("cpu_usage")
    assert m2["value"] == 60.0
    print("OK: gauge")


def test_histogram():
    mc = PipelineMetricCollector()
    mc.register_metric("latency", metric_type="histogram")
    for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        mc.record("latency", float(v))
    p50 = mc.get_percentile("latency", 50)
    assert 45 <= p50 <= 60
    p99 = mc.get_percentile("latency", 99)
    assert p99 >= 90
    print("OK: histogram")


def test_summary():
    mc = PipelineMetricCollector()
    mc.register_metric("duration", metric_type="histogram")
    for v in [1, 2, 3, 4, 5]:
        mc.record("duration", float(v))
    s = mc.get_summary("duration")
    assert s["min"] == 1.0
    assert s["max"] == 5.0
    assert s["count"] == 5
    assert s["avg"] == 3.0
    print("OK: summary")


def test_list_metrics():
    mc = PipelineMetricCollector()
    mc.register_metric("m1", metric_type="counter", tags=["api"])
    mc.register_metric("m2", metric_type="gauge")
    assert len(mc.list_metrics()) == 2
    assert len(mc.list_metrics(metric_type="counter")) == 1
    assert len(mc.list_metrics(tag="api")) == 1
    print("OK: list metrics")


def test_remove_metric():
    mc = PipelineMetricCollector()
    mc.register_metric("m1")
    assert mc.remove_metric("m1") is True
    assert mc.remove_metric("m1") is False
    print("OK: remove metric")


def test_snapshot():
    mc = PipelineMetricCollector()
    mc.register_metric("c1", metric_type="counter")
    mc.register_metric("g1", metric_type="gauge")
    mc.increment("c1", 5)
    mc.set_gauge("g1", 42)
    snap = mc.snapshot()
    assert len(snap) >= 2
    print("OK: snapshot")


def test_history():
    mc = PipelineMetricCollector()
    mc.register_metric("m1")
    hist = mc.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    mc = PipelineMetricCollector()
    fired = []
    mc.on_change("mon", lambda a, d: fired.append(a))
    mc.register_metric("m1")
    assert len(fired) >= 1
    assert mc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    mc = PipelineMetricCollector()
    mc.register_metric("m1")
    stats = mc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    mc = PipelineMetricCollector()
    mc.register_metric("m1")
    mc.reset()
    assert mc.list_metrics() == []
    print("OK: reset")


def main():
    print("=== Pipeline Metric Collector Tests ===\n")
    test_register_metric()
    test_counter()
    test_gauge()
    test_histogram()
    test_summary()
    test_list_metrics()
    test_remove_metric()
    test_snapshot()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
