"""Test pipeline metric dashboard -- unit tests."""
import sys, time
sys.path.insert(0, ".")

from src.services.pipeline_metric_dashboard import PipelineMetricDashboard


def test_record_metric():
    d = PipelineMetricDashboard()
    mid = d.record_metric("deploy", "latency", 42.5, tags=["prod"])
    assert len(mid) > 0
    assert mid.startswith("pmd-")
    m = d.get_metric(mid)
    assert m is not None
    assert m["pipeline_name"] == "deploy"
    assert m["metric_name"] == "latency"
    assert m["value"] == 42.5
    print("OK: record metric")


def test_get_pipeline_metrics():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 42.0)
    d.record_metric("deploy", "throughput", 100.0)
    d.record_metric("test", "latency", 10.0)
    all_m = d.get_pipeline_metrics("deploy")
    assert len(all_m) == 2
    lat_only = d.get_pipeline_metrics("deploy", metric_name="latency")
    assert len(lat_only) == 1
    print("OK: get pipeline metrics")


def test_get_latest_metric():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 10.0)
    d.record_metric("deploy", "latency", 20.0)
    latest = d.get_latest_metric("deploy", "latency")
    assert latest is not None
    assert latest["value"] == 20.0
    assert d.get_latest_metric("nonexistent", "x") is None
    print("OK: get latest metric")


def test_get_average():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 10.0)
    d.record_metric("deploy", "latency", 20.0)
    d.record_metric("deploy", "latency", 30.0)
    avg = d.get_average("deploy", "latency")
    assert avg == 20.0
    assert d.get_average("nonexistent", "x") == 0.0
    print("OK: get average")


def test_get_min_max():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 10.0)
    d.record_metric("deploy", "latency", 50.0)
    d.record_metric("deploy", "latency", 30.0)
    mm = d.get_min_max("deploy", "latency")
    assert mm["min"] == 10.0
    assert mm["max"] == 50.0
    print("OK: get min/max")


def test_get_dashboard_summary():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 42.0)
    d.record_metric("deploy", "throughput", 100.0)
    summary = d.get_dashboard_summary("deploy")
    assert summary is not None
    assert len(summary) > 0
    print("OK: get dashboard summary")


def test_list_metric_names():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 42.0)
    d.record_metric("deploy", "throughput", 100.0)
    names = d.list_metric_names("deploy")
    assert "latency" in names
    assert "throughput" in names
    print("OK: list metric names")


def test_purge():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 42.0)
    time.sleep(0.01)
    count = d.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    d = PipelineMetricDashboard()
    fired = []
    d.on_change("mon", lambda a, dt: fired.append(a))
    d.record_metric("deploy", "latency", 42.0)
    assert len(fired) >= 1
    assert d.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 42.0)
    stats = d.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    d = PipelineMetricDashboard()
    d.record_metric("deploy", "latency", 42.0)
    d.reset()
    assert d.list_metric_names() == []
    print("OK: reset")


def main():
    print("=== Pipeline Metric Dashboard Tests ===\n")
    test_record_metric()
    test_get_pipeline_metrics()
    test_get_latest_metric()
    test_get_average()
    test_get_min_max()
    test_get_dashboard_summary()
    test_list_metric_names()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
