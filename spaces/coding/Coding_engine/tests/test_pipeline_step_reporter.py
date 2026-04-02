"""Tests for PipelineStepReporter service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_reporter import PipelineStepReporter


def test_record_execution_returns_id():
    svc = PipelineStepReporter()
    eid = svc.record_execution("p1", "step_a", 100.0)
    assert isinstance(eid, str), f"Expected str, got {type(eid)}"
    assert eid.startswith("psrp-"), f"Expected psrp- prefix, got {eid}"
    print("  test_record_execution_returns_id PASSED")


def test_record_execution_stores_fields():
    svc = PipelineStepReporter()
    eid = svc.record_execution("p1", "step_a", 150.5, status="error", metadata={"key": "val"})
    entry = svc.get_execution(eid)
    assert entry["pipeline_id"] == "p1"
    assert entry["step_name"] == "step_a"
    assert entry["duration_ms"] == 150.5
    assert entry["status"] == "error"
    assert entry["metadata"] == {"key": "val"}
    assert "created_at" in entry
    print("  test_record_execution_stores_fields PASSED")


def test_record_execution_default_status():
    svc = PipelineStepReporter()
    eid = svc.record_execution("p1", "step_a", 50.0)
    entry = svc.get_execution(eid)
    assert entry["status"] == "success"
    print("  test_record_execution_default_status PASSED")


def test_get_execution_not_found():
    svc = PipelineStepReporter()
    result = svc.get_execution("nonexistent")
    assert result == {}, f"Expected empty dict, got {result}"
    print("  test_get_execution_not_found PASSED")


def test_get_report_empty():
    svc = PipelineStepReporter()
    report = svc.get_report("p1")
    assert report["pipeline_id"] == "p1"
    assert report["total_executions"] == 0
    assert report["avg_duration_ms"] == 0.0
    assert report["success_count"] == 0
    assert report["error_count"] == 0
    assert report["steps"] == {}
    print("  test_get_report_empty PASSED")


def test_get_report_aggregation():
    svc = PipelineStepReporter()
    svc.record_execution("p1", "step_a", 100.0, status="success")
    svc.record_execution("p1", "step_a", 200.0, status="success")
    svc.record_execution("p1", "step_b", 300.0, status="error")
    report = svc.get_report("p1")
    assert report["total_executions"] == 3
    assert report["avg_duration_ms"] == 200.0, f"Expected 200.0, got {report['avg_duration_ms']}"
    assert report["success_count"] == 2
    assert report["error_count"] == 1
    assert report["steps"]["step_a"]["count"] == 2
    assert report["steps"]["step_a"]["avg_duration_ms"] == 150.0
    assert report["steps"]["step_b"]["count"] == 1
    assert report["steps"]["step_b"]["avg_duration_ms"] == 300.0
    print("  test_get_report_aggregation PASSED")


def test_get_executions_basic():
    svc = PipelineStepReporter()
    svc.record_execution("p1", "step_a", 100.0)
    svc.record_execution("p1", "step_b", 200.0)
    svc.record_execution("p2", "step_a", 300.0)
    results = svc.get_executions("p1")
    assert len(results) == 2, f"Expected 2, got {len(results)}"
    print("  test_get_executions_basic PASSED")


def test_get_executions_filter_by_step():
    svc = PipelineStepReporter()
    svc.record_execution("p1", "step_a", 100.0)
    svc.record_execution("p1", "step_b", 200.0)
    svc.record_execution("p1", "step_a", 300.0)
    results = svc.get_executions("p1", step_name="step_a")
    assert len(results) == 2, f"Expected 2, got {len(results)}"
    for r in results:
        assert r["step_name"] == "step_a"
    print("  test_get_executions_filter_by_step PASSED")


def test_get_executions_limit():
    svc = PipelineStepReporter()
    for i in range(10):
        svc.record_execution("p1", "step_a", float(i))
    results = svc.get_executions("p1", limit=3)
    assert len(results) == 3, f"Expected 3, got {len(results)}"
    print("  test_get_executions_limit PASSED")


def test_get_execution_count():
    svc = PipelineStepReporter()
    assert svc.get_execution_count() == 0
    svc.record_execution("p1", "step_a", 100.0)
    svc.record_execution("p1", "step_b", 200.0)
    svc.record_execution("p2", "step_a", 300.0)
    assert svc.get_execution_count() == 3
    assert svc.get_execution_count("p1") == 2
    assert svc.get_execution_count("p2") == 1
    assert svc.get_execution_count("p3") == 0
    print("  test_get_execution_count PASSED")


def test_clear_executions():
    svc = PipelineStepReporter()
    svc.record_execution("p1", "step_a", 100.0)
    svc.record_execution("p1", "step_b", 200.0)
    svc.record_execution("p2", "step_a", 300.0)
    removed = svc.clear_executions("p1")
    assert removed == 2, f"Expected 2 removed, got {removed}"
    assert svc.get_execution_count("p1") == 0
    assert svc.get_execution_count("p2") == 1
    print("  test_clear_executions PASSED")


def test_clear_executions_empty():
    svc = PipelineStepReporter()
    removed = svc.clear_executions("nonexistent")
    assert removed == 0
    print("  test_clear_executions_empty PASSED")


def test_get_stats():
    svc = PipelineStepReporter()
    stats = svc.get_stats()
    assert stats["total_executions"] == 0
    assert stats["unique_pipelines"] == 0
    assert stats["total_duration_ms"] == 0

    svc.record_execution("p1", "step_a", 100.0)
    svc.record_execution("p1", "step_b", 200.0)
    svc.record_execution("p2", "step_a", 50.0)
    stats = svc.get_stats()
    assert stats["total_executions"] == 3
    assert stats["unique_pipelines"] == 2
    assert stats["total_duration_ms"] == 350.0
    print("  test_get_stats PASSED")


def test_reset():
    svc = PipelineStepReporter()
    svc.record_execution("p1", "step_a", 100.0)
    svc.on_change = lambda a, d: None
    svc.reset()
    assert svc.get_execution_count() == 0
    assert svc.on_change is None
    print("  test_reset PASSED")


def test_on_change_property():
    svc = PipelineStepReporter()
    assert svc.on_change is None
    events = []
    svc.on_change = lambda action, detail: events.append((action, detail))
    svc.record_execution("p1", "step_a", 100.0)
    assert len(events) == 1
    assert events[0][0] == "execution_recorded"
    svc.on_change = None
    assert svc.on_change is None
    print("  test_on_change_property PASSED")


def test_remove_callback():
    svc = PipelineStepReporter()
    svc.on_change = lambda a, d: None
    assert svc.remove_callback("__default__") is True
    assert svc.remove_callback("__default__") is False
    assert svc.remove_callback("nonexistent") is False
    print("  test_remove_callback PASSED")


def test_unique_ids():
    svc = PipelineStepReporter()
    ids = set()
    for _ in range(100):
        eid = svc.record_execution("p1", "step_a", 10.0)
        ids.add(eid)
    assert len(ids) == 100, f"Expected 100 unique IDs, got {len(ids)}"
    print("  test_unique_ids PASSED")


if __name__ == "__main__":
    tests = [
        test_record_execution_returns_id,
        test_record_execution_stores_fields,
        test_record_execution_default_status,
        test_get_execution_not_found,
        test_get_report_empty,
        test_get_report_aggregation,
        test_get_executions_basic,
        test_get_executions_filter_by_step,
        test_get_executions_limit,
        test_get_execution_count,
        test_clear_executions,
        test_clear_executions_empty,
        test_get_stats,
        test_reset,
        test_on_change_property,
        test_remove_callback,
        test_unique_ids,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAILED: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed")
