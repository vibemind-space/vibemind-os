"""Test pipeline metric aggregator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_metric_aggregator import PipelineMetricAggregator


def test_record_metric():
    ma = PipelineMetricAggregator()
    eid = ma.record_metric("pipeline-1", "latency", 50.0)
    assert len(eid) > 0
    assert eid.startswith("pma-")
    print("OK: record metric")


def test_get_metric():
    ma = PipelineMetricAggregator()
    eid = ma.record_metric("pipeline-1", "latency", 50.0)
    metric = ma.get_metric(eid)
    assert metric is not None
    assert metric["pipeline_id"] == "pipeline-1"
    assert metric["metric_name"] == "latency"
    assert metric["value"] == 50.0
    assert ma.get_metric("nonexistent") is None
    print("OK: get metric")


def test_get_average():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    ma.record_metric("pipeline-1", "latency", 20.0)
    ma.record_metric("pipeline-1", "latency", 30.0)
    avg = ma.get_average("pipeline-1", "latency")
    assert avg == 20.0
    print("OK: get average")


def test_get_min_max():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    ma.record_metric("pipeline-1", "latency", 50.0)
    ma.record_metric("pipeline-1", "latency", 30.0)
    assert ma.get_min("pipeline-1", "latency") == 10.0
    assert ma.get_max("pipeline-1", "latency") == 50.0
    print("OK: get min max")


def test_get_count():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    ma.record_metric("pipeline-1", "latency", 20.0)
    assert ma.get_count("pipeline-1", "latency") == 2
    print("OK: get count")


def test_get_summary():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    ma.record_metric("pipeline-1", "latency", 20.0)
    ma.record_metric("pipeline-1", "latency", 30.0)
    summary = ma.get_summary("pipeline-1", "latency")
    assert summary["avg"] == 20.0
    assert summary["min"] == 10.0
    assert summary["max"] == 30.0
    assert summary["count"] == 3
    assert summary["sum"] == 60.0
    print("OK: get summary")


def test_list_pipelines():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    ma.record_metric("pipeline-2", "throughput", 100.0)
    pipelines = ma.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_list_metrics():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    ma.record_metric("pipeline-1", "throughput", 100.0)
    metrics = ma.list_metrics("pipeline-1")
    assert "latency" in metrics
    assert "throughput" in metrics
    print("OK: list metrics")


def test_callbacks():
    ma = PipelineMetricAggregator()
    fired = []
    ma.on_change("mon", lambda a, d: fired.append(a))
    ma.record_metric("pipeline-1", "latency", 10.0)
    assert len(fired) >= 1
    assert ma.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    stats = ma.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ma = PipelineMetricAggregator()
    ma.record_metric("pipeline-1", "latency", 10.0)
    ma.reset()
    assert ma.get_entry_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Metric Aggregator Tests ===\n")
    test_record_metric()
    test_get_metric()
    test_get_average()
    test_get_min_max()
    test_get_count()
    test_get_summary()
    test_list_pipelines()
    test_list_metrics()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
