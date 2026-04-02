"""Test pipeline telemetry collector."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_telemetry_collector import PipelineTelemetryCollector


def test_register():
    """Register and retrieve metric."""
    tc = PipelineTelemetryCollector()
    mid = tc.register_metric("requests", tags=["api"])
    assert mid.startswith("met-")

    m = tc.get_metric("requests")
    assert m is not None
    assert m["name"] == "requests"
    assert m["metric_type"] == "counter"
    assert m["value"] == 0.0

    assert tc.remove_metric("requests") is True
    assert tc.remove_metric("requests") is False
    print("OK: register")


def test_invalid_register():
    """Invalid register rejected."""
    tc = PipelineTelemetryCollector()
    assert tc.register_metric("") == ""
    assert tc.register_metric("x", metric_type="invalid") == ""
    print("OK: invalid register")


def test_duplicate():
    """Duplicate name rejected."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("m1")
    assert tc.register_metric("m1") == ""
    print("OK: duplicate")


def test_max_metrics():
    """Max metrics enforced."""
    tc = PipelineTelemetryCollector(max_metrics=2)
    tc.register_metric("a")
    tc.register_metric("b")
    assert tc.register_metric("c") == ""
    print("OK: max metrics")


def test_counter():
    """Counter metric records correctly."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("hits", metric_type="counter")

    assert tc.record("hits", 1.0) is True
    assert tc.get_value("hits") == 1.0

    tc.record("hits", 5.0)
    assert tc.get_value("hits") == 6.0

    assert tc.record("nonexistent") is False
    print("OK: counter")


def test_increment():
    """Increment counter shorthand."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("count", metric_type="counter")

    assert tc.increment("count") is True
    assert tc.increment("count", 3.0) is True
    assert tc.get_value("count") == 4.0

    # increment on non-counter fails
    tc.register_metric("g1", metric_type="gauge")
    assert tc.increment("g1") is False
    print("OK: increment")


def test_gauge():
    """Gauge metric replaces value."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("temp", metric_type="gauge")

    assert tc.set_gauge("temp", 42.0) is True
    assert tc.get_value("temp") == 42.0

    tc.set_gauge("temp", 38.0)
    assert tc.get_value("temp") == 38.0

    # set_gauge on non-gauge fails
    tc.register_metric("c1", metric_type="counter")
    assert tc.set_gauge("c1", 10.0) is False
    print("OK: gauge")


def test_histogram():
    """Histogram metric aggregates."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("latency", metric_type="histogram")

    assert tc.observe("latency", 10.0) is True
    tc.observe("latency", 20.0)
    tc.observe("latency", 30.0)

    m = tc.get_metric("latency")
    assert m["count"] == 3
    assert m["total"] == 60.0
    assert m["min"] == 10.0
    assert m["max"] == 30.0
    assert m["avg"] == 20.0

    # observe on non-histogram fails
    tc.register_metric("c1", metric_type="counter")
    assert tc.observe("c1", 5.0) is False
    print("OK: histogram")


def test_get_value():
    """Get value for metric."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("m1", metric_type="counter")
    tc.record("m1", 42.0)
    assert tc.get_value("m1") == 42.0
    assert tc.get_value("nonexistent") == 0.0
    print("OK: get value")


def test_reset_metric():
    """Reset individual metric."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("m1", metric_type="histogram")
    tc.observe("m1", 10.0)
    tc.observe("m1", 20.0)

    assert tc.reset_metric("m1") is True
    m = tc.get_metric("m1")
    assert m["value"] == 0.0
    assert m["count"] == 0
    assert m["total"] == 0.0

    assert tc.reset_metric("nonexistent") is False
    print("OK: reset metric")


def test_list_metrics():
    """List metrics with filters."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("c1", metric_type="counter", tags=["api"])
    tc.register_metric("g1", metric_type="gauge")

    all_m = tc.list_metrics()
    assert len(all_m) == 2

    by_type = tc.list_metrics(metric_type="counter")
    assert len(by_type) == 1

    by_tag = tc.list_metrics(tag="api")
    assert len(by_tag) == 1
    print("OK: list metrics")


def test_search():
    """Search metrics."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("api_requests", tags=["http"])
    tc.register_metric("db_queries")

    results = tc.search("api")
    assert len(results) == 1

    results = tc.search("http")
    assert len(results) == 1
    print("OK: search")


def test_history():
    """History tracking."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("m1", metric_type="counter")
    tc.record("m1", 1.0)
    tc.record("m1", 2.0)

    hist = tc.get_history()
    assert len(hist) == 2

    by_metric = tc.get_history(metric_name="m1")
    assert len(by_metric) == 2

    by_action = tc.get_history(action="recorded")
    assert len(by_action) == 2

    limited = tc.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    tc = PipelineTelemetryCollector()
    fired = []
    tc.on_change("mon", lambda a, d: fired.append(a))

    tc.register_metric("m1")
    assert "metric_registered" in fired

    tc.record("m1", 1.0)
    assert "metric_recorded" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    tc = PipelineTelemetryCollector()
    assert tc.on_change("mon", lambda a, d: None) is True
    assert tc.on_change("mon", lambda a, d: None) is False
    assert tc.remove_callback("mon") is True
    assert tc.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("c1", metric_type="counter")
    tc.register_metric("g1", metric_type="gauge")
    tc.register_metric("h1", metric_type="histogram")
    tc.record("c1", 1.0)

    stats = tc.get_stats()
    assert stats["current_metrics"] == 3
    assert stats["counters"] == 1
    assert stats["gauges"] == 1
    assert stats["histograms"] == 1
    assert stats["total_registered"] == 3
    assert stats["total_recordings"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    tc = PipelineTelemetryCollector()
    tc.register_metric("m1")

    tc.reset()
    assert tc.list_metrics() == []
    stats = tc.get_stats()
    assert stats["current_metrics"] == 0
    assert stats["total_registered"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Telemetry Collector Tests ===\n")
    test_register()
    test_invalid_register()
    test_duplicate()
    test_max_metrics()
    test_counter()
    test_increment()
    test_gauge()
    test_histogram()
    test_get_value()
    test_reset_metric()
    test_list_metrics()
    test_search()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
