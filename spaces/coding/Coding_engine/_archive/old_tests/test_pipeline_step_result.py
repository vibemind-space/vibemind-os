"""Tests for PipelineStepResult service."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_result import PipelineStepResult


def test_store_result():
    svc = PipelineStepResult()
    rid = svc.store_result("pipe-1", "step-a", "success", {"output": 42})
    assert rid.startswith("psr3-"), f"Expected psr3- prefix, got {rid}"
    assert len(rid) > 5
    print("PASSED test_store_result")


def test_get_result():
    svc = PipelineStepResult()
    rid = svc.store_result("pipe-1", "step-a", "success", {"val": 1})
    result = svc.get_result(rid)
    assert result is not None
    assert result["pipeline_id"] == "pipe-1"
    assert result["step_name"] == "step-a"
    assert result["status"] == "success"
    assert result["data"] == {"val": 1}
    assert "timestamp" in result
    # Non-existent
    assert svc.get_result("psr3-nonexistent") is None
    print("PASSED test_get_result")


def test_get_results():
    svc = PipelineStepResult()
    svc.store_result("pipe-1", "step-a", "success")
    svc.store_result("pipe-1", "step-b", "failure")
    svc.store_result("pipe-2", "step-a", "success")
    results = svc.get_results("pipe-1")
    assert len(results) == 2
    results2 = svc.get_results("pipe-2")
    assert len(results2) == 1
    assert results2[0]["step_name"] == "step-a"
    print("PASSED test_get_results")


def test_get_results_filtered():
    svc = PipelineStepResult()
    svc.store_result("pipe-1", "step-a", "success")
    svc.store_result("pipe-1", "step-a", "failure")
    svc.store_result("pipe-1", "step-b", "success")
    # Filter by step_name
    results = svc.get_results("pipe-1", step_name="step-a")
    assert len(results) == 2
    # Filter by status
    results = svc.get_results("pipe-1", status="success")
    assert len(results) == 2
    # Filter by both
    results = svc.get_results("pipe-1", step_name="step-a", status="failure")
    assert len(results) == 1
    assert results[0]["status"] == "failure"
    print("PASSED test_get_results_filtered")


def test_get_latest_result():
    svc = PipelineStepResult()
    svc.store_result("pipe-1", "step-a", "success", {"v": 1})
    svc.store_result("pipe-1", "step-a", "failure", {"v": 2})
    svc.store_result("pipe-1", "step-b", "success", {"v": 3})
    latest = svc.get_latest_result("pipe-1")
    assert latest is not None
    assert latest["data"] == {"v": 3}
    # Filter by step_name
    latest_a = svc.get_latest_result("pipe-1", step_name="step-a")
    assert latest_a is not None
    assert latest_a["data"] == {"v": 2}
    # Non-existent pipeline
    assert svc.get_latest_result("pipe-999") is None
    print("PASSED test_get_latest_result")


def test_get_result_count():
    svc = PipelineStepResult()
    assert svc.get_result_count() == 0
    svc.store_result("pipe-1", "step-a", "success")
    svc.store_result("pipe-1", "step-b", "failure")
    svc.store_result("pipe-2", "step-a", "success")
    assert svc.get_result_count() == 3
    assert svc.get_result_count("pipe-1") == 2
    assert svc.get_result_count("pipe-2") == 1
    assert svc.get_result_count("pipe-3") == 0
    print("PASSED test_get_result_count")


def test_clear_results():
    svc = PipelineStepResult()
    svc.store_result("pipe-1", "step-a", "success")
    svc.store_result("pipe-1", "step-b", "failure")
    svc.store_result("pipe-2", "step-a", "success")
    removed = svc.clear_results("pipe-1")
    assert removed == 2
    assert svc.get_result_count("pipe-1") == 0
    assert svc.get_result_count("pipe-2") == 1
    # Clear non-existent
    assert svc.clear_results("pipe-999") == 0
    print("PASSED test_clear_results")


def test_list_pipelines():
    svc = PipelineStepResult()
    assert svc.list_pipelines() == []
    svc.store_result("pipe-1", "step-a", "success")
    svc.store_result("pipe-2", "step-b", "failure")
    svc.store_result("pipe-1", "step-c", "success")
    pipelines = svc.list_pipelines()
    assert sorted(pipelines) == ["pipe-1", "pipe-2"]
    print("PASSED test_list_pipelines")


def test_callbacks():
    svc = PipelineStepResult()
    events = []
    svc.on_change("tracker", lambda action, detail: events.append((action, detail)))
    svc.store_result("pipe-1", "step-a", "success")
    assert len(events) == 1
    assert events[0][0] == "result_stored"
    assert events[0][1]["pipeline_id"] == "pipe-1"
    # Remove callback
    assert svc.remove_callback("tracker") is True
    svc.store_result("pipe-1", "step-b", "failure")
    assert len(events) == 1  # No new event
    # Remove non-existent
    assert svc.remove_callback("nonexistent") is False
    print("PASSED test_callbacks")


def test_stats():
    svc = PipelineStepResult()
    svc.store_result("pipe-1", "step-a", "success")
    svc.store_result("pipe-1", "step-b", "failure")
    svc.store_result("pipe-2", "step-a", "success")
    svc.on_change("cb1", lambda a, d: None)
    stats = svc.get_stats()
    assert stats["total_results"] == 3
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 2
    assert stats["statuses"]["success"] == 2
    assert stats["statuses"]["failure"] == 1
    assert stats["registered_callbacks"] == 1
    print("PASSED test_stats")


def test_reset():
    svc = PipelineStepResult()
    svc.store_result("pipe-1", "step-a", "success")
    svc.on_change("cb1", lambda a, d: None)
    svc.reset()
    assert svc.get_result_count() == 0
    assert svc.list_pipelines() == []
    assert svc.get_stats()["registered_callbacks"] == 0
    # Verify seq reset by storing new result
    rid = svc.store_result("pipe-1", "step-a", "success")
    assert rid.startswith("psr3-")
    print("PASSED test_reset")


if __name__ == "__main__":
    test_store_result()
    test_get_result()
    test_get_results()
    test_get_results_filtered()
    test_get_latest_result()
    test_get_result_count()
    test_clear_results()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")
