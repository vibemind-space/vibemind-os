"""Tests for PipelineStepLogger service."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "services"))

from pipeline_step_logger import PipelineStepLogger


def test_log_step():
    svc = PipelineStepLogger()
    log_id = svc.log_step("pipe-1", "extract", status="success",
                          input_data={"url": "http://x"}, output_data={"rows": 10},
                          duration_ms=150.5)
    assert log_id.startswith("psl-"), f"Expected psl- prefix, got {log_id}"
    assert svc.get_log_count() == 1
    print("  test_log_step PASSED")


def test_get_logs():
    svc = PipelineStepLogger()
    svc.log_step("pipe-1", "extract")
    svc.log_step("pipe-1", "transform")
    svc.log_step("pipe-2", "load")
    logs = svc.get_logs("pipe-1")
    assert len(logs) == 2, f"Expected 2, got {len(logs)}"
    assert logs[0]["step_name"] == "extract"
    assert logs[1]["step_name"] == "transform"
    print("  test_get_logs PASSED")


def test_get_logs_filtered():
    svc = PipelineStepLogger()
    svc.log_step("pipe-1", "extract", status="success")
    svc.log_step("pipe-1", "transform", status="failure")
    svc.log_step("pipe-1", "load", status="success")
    by_status = svc.get_logs("pipe-1", status="failure")
    assert len(by_status) == 1
    assert by_status[0]["step_name"] == "transform"
    by_step = svc.get_logs("pipe-1", step_name="extract")
    assert len(by_step) == 1
    assert by_step[0]["status"] == "success"
    print("  test_get_logs_filtered PASSED")


def test_get_latest_log():
    svc = PipelineStepLogger()
    assert svc.get_latest_log("pipe-1") is None
    svc.log_step("pipe-1", "extract")
    svc.log_step("pipe-1", "transform")
    latest = svc.get_latest_log("pipe-1")
    assert latest is not None
    assert latest["step_name"] == "transform"
    print("  test_get_latest_log PASSED")


def test_get_log_count():
    svc = PipelineStepLogger()
    assert svc.get_log_count() == 0
    svc.log_step("pipe-1", "extract")
    svc.log_step("pipe-1", "transform")
    svc.log_step("pipe-2", "load")
    assert svc.get_log_count() == 3
    assert svc.get_log_count("pipe-1") == 2
    assert svc.get_log_count("pipe-2") == 1
    print("  test_get_log_count PASSED")


def test_clear_logs():
    svc = PipelineStepLogger()
    svc.log_step("pipe-1", "extract")
    svc.log_step("pipe-1", "transform")
    svc.log_step("pipe-2", "load")
    removed = svc.clear_logs("pipe-1")
    assert removed == 2
    assert svc.get_log_count() == 1
    assert svc.get_log_count("pipe-1") == 0
    print("  test_clear_logs PASSED")


def test_list_pipelines():
    svc = PipelineStepLogger()
    assert svc.list_pipelines() == []
    svc.log_step("pipe-1", "extract")
    svc.log_step("pipe-2", "load")
    svc.log_step("pipe-1", "transform")
    pipelines = svc.list_pipelines()
    assert set(pipelines) == {"pipe-1", "pipe-2"}
    print("  test_list_pipelines PASSED")


def test_callbacks():
    svc = PipelineStepLogger()
    events = []
    svc.on_change("logger", lambda action, detail: events.append((action, detail)))
    svc.log_step("pipe-1", "extract")
    assert len(events) == 1
    assert events[0][0] == "step_logged"
    assert events[0][1]["pipeline_id"] == "pipe-1"
    removed = svc.remove_callback("logger")
    assert removed is True
    svc.log_step("pipe-1", "transform")
    assert len(events) == 1  # no new event after removal
    assert svc.remove_callback("nonexistent") is False
    print("  test_callbacks PASSED")


def test_stats():
    svc = PipelineStepLogger()
    stats = svc.get_stats()
    assert stats["total_logs"] == 0
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 0
    assert stats["registered_callbacks"] == 0
    svc.log_step("pipe-1", "extract")
    svc.log_step("pipe-2", "load")
    svc.on_change("cb1", lambda a, d: None)
    stats = svc.get_stats()
    assert stats["total_logs"] == 2
    assert stats["pipelines"] == 2
    assert stats["registered_callbacks"] == 1
    print("  test_stats PASSED")


def test_reset():
    svc = PipelineStepLogger()
    svc.log_step("pipe-1", "extract")
    svc.on_change("cb1", lambda a, d: None)
    svc.reset()
    assert svc.get_log_count() == 0
    assert svc.list_pipelines() == []
    stats = svc.get_stats()
    assert stats["registered_callbacks"] == 0
    # IDs should restart sequence
    log_id = svc.log_step("pipe-1", "new")
    assert log_id.startswith("psl-")
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_log_step()
    test_get_logs()
    test_get_logs_filtered()
    test_get_latest_log()
    test_get_log_count()
    test_clear_logs()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
