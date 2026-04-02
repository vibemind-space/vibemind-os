"""Tests for PipelineStepMetric service."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_metric import PipelineStepMetric


def test_record_metric():
    svc = PipelineStepMetric()
    mid = svc.record_metric("p1", "step_a", 120.5)
    assert mid.startswith("psm-"), f"Expected psm- prefix, got {mid}"
    mid2 = svc.record_metric("p1", "step_b", 80.0, success=False)
    assert mid2.startswith("psm-")
    assert mid != mid2, "IDs must be unique"
    print("  test_record_metric PASSED")


def test_get_metrics():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0)
    svc.record_metric("p1", "step_b", 200.0)
    metrics = svc.get_metrics("p1")
    assert len(metrics) == 2, f"Expected 2, got {len(metrics)}"
    assert metrics[0]["step_name"] == "step_a"
    assert metrics[1]["step_name"] == "step_b"
    empty = svc.get_metrics("nonexistent")
    assert empty == [], f"Expected [], got {empty}"
    print("  test_get_metrics PASSED")


def test_get_metrics_filtered():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0)
    svc.record_metric("p1", "step_b", 200.0)
    svc.record_metric("p1", "step_a", 150.0)
    filtered = svc.get_metrics("p1", step_name="step_a")
    assert len(filtered) == 2, f"Expected 2, got {len(filtered)}"
    for m in filtered:
        assert m["step_name"] == "step_a"
    print("  test_get_metrics_filtered PASSED")


def test_get_average_duration():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0)
    svc.record_metric("p1", "step_a", 200.0)
    svc.record_metric("p1", "step_a", 300.0)
    avg = svc.get_average_duration("p1", "step_a")
    assert avg == 200.0, f"Expected 200.0, got {avg}"
    zero = svc.get_average_duration("p1", "no_such_step")
    assert zero == 0.0, f"Expected 0.0, got {zero}"
    print("  test_get_average_duration PASSED")


def test_get_success_rate():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0, success=True)
    svc.record_metric("p1", "step_a", 100.0, success=True)
    svc.record_metric("p1", "step_a", 100.0, success=False)
    svc.record_metric("p1", "step_a", 100.0, success=False)
    rate = svc.get_success_rate("p1", "step_a")
    assert rate == 0.5, f"Expected 0.5, got {rate}"
    zero = svc.get_success_rate("p2", "no_step")
    assert zero == 0.0, f"Expected 0.0, got {zero}"
    print("  test_get_success_rate PASSED")


def test_get_execution_count():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0)
    svc.record_metric("p1", "step_a", 200.0)
    svc.record_metric("p1", "step_b", 300.0)
    assert svc.get_execution_count("p1") == 3
    assert svc.get_execution_count("p1", "step_a") == 2
    assert svc.get_execution_count("p1", "step_b") == 1
    assert svc.get_execution_count("p2") == 0
    print("  test_get_execution_count PASSED")


def test_get_metric_count():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0)
    svc.record_metric("p1", "step_b", 200.0)
    svc.record_metric("p2", "step_c", 300.0)
    assert svc.get_metric_count() == 3
    assert svc.get_metric_count("p1") == 2
    assert svc.get_metric_count("p2") == 1
    assert svc.get_metric_count("p3") == 0
    print("  test_get_metric_count PASSED")


def test_list_pipelines():
    svc = PipelineStepMetric()
    assert svc.list_pipelines() == []
    svc.record_metric("p1", "step_a", 100.0)
    svc.record_metric("p2", "step_b", 200.0)
    pipelines = svc.list_pipelines()
    assert "p1" in pipelines
    assert "p2" in pipelines
    assert len(pipelines) == 2
    print("  test_list_pipelines PASSED")


def test_callbacks():
    svc = PipelineStepMetric()
    events = []
    svc.on_change("cb1", lambda action, detail: events.append((action, detail)))
    svc.record_metric("p1", "step_a", 100.0)
    assert len(events) == 1
    assert events[0][0] == "metric_recorded"
    assert events[0][1]["pipeline_id"] == "p1"
    removed = svc.remove_callback("cb1")
    assert removed is True
    svc.record_metric("p1", "step_b", 200.0)
    assert len(events) == 1, "Callback should not fire after removal"
    not_removed = svc.remove_callback("nonexistent")
    assert not_removed is False
    print("  test_callbacks PASSED")


def test_stats():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0, success=True)
    svc.record_metric("p1", "step_b", 200.0, success=False)
    svc.on_change("cb1", lambda a, d: None)
    stats = svc.get_stats()
    assert stats["total_metrics"] == 2
    assert stats["total_successes"] == 1
    assert stats["total_failures"] == 1
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 1
    assert stats["registered_callbacks"] == 1
    print("  test_stats PASSED")


def test_reset():
    svc = PipelineStepMetric()
    svc.record_metric("p1", "step_a", 100.0)
    svc.on_change("cb1", lambda a, d: None)
    svc.reset()
    assert svc.get_metric_count() == 0
    assert svc.list_pipelines() == []
    stats = svc.get_stats()
    assert stats["registered_callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_record_metric()
    test_get_metrics()
    test_get_metrics_filtered()
    test_get_average_duration()
    test_get_success_rate()
    test_get_execution_count()
    test_get_metric_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")
