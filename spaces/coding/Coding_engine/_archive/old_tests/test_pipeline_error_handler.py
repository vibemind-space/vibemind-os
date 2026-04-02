"""Tests for PipelineErrorHandler."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "services"))

from pipeline_error_handler import PipelineErrorHandler


def test_record_error():
    h = PipelineErrorHandler()
    eid = h.record_error("pipe-1", "step-a", "timeout", "Request timed out")
    assert eid.startswith("peh-"), f"Expected peh- prefix, got {eid}"
    assert len(h.errors) == 1
    entry = h.errors[eid]
    assert entry.pipeline_id == "pipe-1"
    assert entry.step_name == "step-a"
    assert entry.error_type == "timeout"
    assert entry.message == "Request timed out"
    assert entry.severity == "error"

    eid2 = h.record_error("pipe-1", "step-b", "runtime", "NPE", severity="critical")
    assert eid2.startswith("peh-")
    assert eid2 != eid
    assert h.errors[eid2].severity == "critical"
    print("  test_record_error PASSED")


def test_get_errors():
    h = PipelineErrorHandler()
    h.record_error("pipe-1", "step-a", "timeout", "msg1")
    h.record_error("pipe-1", "step-b", "runtime", "msg2")
    h.record_error("pipe-2", "step-a", "timeout", "msg3")

    errs = h.get_errors("pipe-1")
    assert len(errs) == 2
    assert all(e["pipeline_id"] == "pipe-1" for e in errs)

    errs2 = h.get_errors("pipe-2")
    assert len(errs2) == 1

    errs3 = h.get_errors("pipe-999")
    assert len(errs3) == 0
    print("  test_get_errors PASSED")


def test_get_errors_filtered():
    h = PipelineErrorHandler()
    h.record_error("pipe-1", "step-a", "timeout", "msg1", severity="error")
    h.record_error("pipe-1", "step-a", "runtime", "msg2", severity="warning")
    h.record_error("pipe-1", "step-b", "timeout", "msg3", severity="error")

    errs = h.get_errors("pipe-1", step_name="step-a")
    assert len(errs) == 2

    errs = h.get_errors("pipe-1", error_type="timeout")
    assert len(errs) == 2

    errs = h.get_errors("pipe-1", severity="warning")
    assert len(errs) == 1

    errs = h.get_errors("pipe-1", step_name="step-a", error_type="timeout")
    assert len(errs) == 1
    print("  test_get_errors_filtered PASSED")


def test_get_error_summary():
    h = PipelineErrorHandler()
    h.record_error("pipe-1", "step-a", "timeout", "msg1", severity="error")
    h.record_error("pipe-1", "step-b", "runtime", "msg2", severity="warning")
    h.record_error("pipe-1", "step-c", "timeout", "msg3", severity="error")

    summary = h.get_error_summary("pipe-1")
    assert summary["pipeline_id"] == "pipe-1"
    assert summary["total"] == 3
    assert summary["by_type"]["timeout"] == 2
    assert summary["by_type"]["runtime"] == 1
    assert summary["by_severity"]["error"] == 2
    assert summary["by_severity"]["warning"] == 1

    empty = h.get_error_summary("pipe-999")
    assert empty["total"] == 0
    print("  test_get_error_summary PASSED")


def test_clear_errors():
    h = PipelineErrorHandler()
    h.record_error("pipe-1", "step-a", "timeout", "msg1")
    h.record_error("pipe-1", "step-b", "runtime", "msg2")
    h.record_error("pipe-2", "step-a", "timeout", "msg3")

    count = h.clear_errors("pipe-1")
    assert count == 2
    assert h.get_error_count("pipe-1") == 0
    assert h.get_error_count("pipe-2") == 1

    count2 = h.clear_errors("pipe-999")
    assert count2 == 0
    print("  test_clear_errors PASSED")


def test_get_error_count():
    h = PipelineErrorHandler()
    assert h.get_error_count() == 0
    assert h.get_error_count("pipe-1") == 0

    h.record_error("pipe-1", "step-a", "timeout", "msg1")
    h.record_error("pipe-1", "step-b", "runtime", "msg2")
    h.record_error("pipe-2", "step-a", "timeout", "msg3")

    assert h.get_error_count() == 3
    assert h.get_error_count("pipe-1") == 2
    assert h.get_error_count("pipe-2") == 1
    print("  test_get_error_count PASSED")


def test_list_pipelines():
    h = PipelineErrorHandler()
    assert h.list_pipelines() == []

    h.record_error("pipe-b", "step-a", "timeout", "msg1")
    h.record_error("pipe-a", "step-a", "runtime", "msg2")
    h.record_error("pipe-b", "step-b", "timeout", "msg3")

    pipelines = h.list_pipelines()
    assert pipelines == ["pipe-a", "pipe-b"]
    print("  test_list_pipelines PASSED")


def test_callbacks():
    h = PipelineErrorHandler()
    events = []

    h.on_change("listener1", lambda action, detail: events.append((action, detail)))

    h.record_error("pipe-1", "step-a", "timeout", "msg1")
    assert len(events) == 1
    assert events[0][0] == "record_error"
    assert events[0][1]["pipeline_id"] == "pipe-1"

    h.clear_errors("pipe-1")
    assert len(events) == 2
    assert events[1][0] == "clear_errors"

    removed = h.remove_callback("listener1")
    assert removed is True

    removed2 = h.remove_callback("nonexistent")
    assert removed2 is False

    h.record_error("pipe-1", "step-b", "runtime", "msg2")
    assert len(events) == 2  # no new events after callback removed
    print("  test_callbacks PASSED")


def test_stats():
    h = PipelineErrorHandler()
    stats = h.get_stats()
    assert stats["total_recorded"] == 0
    assert stats["total_cleared"] == 0
    assert stats["total_lookups"] == 0
    assert stats["current_errors"] == 0

    h.record_error("pipe-1", "step-a", "timeout", "msg1")
    h.record_error("pipe-1", "step-b", "runtime", "msg2")
    h.get_errors("pipe-1")
    h.clear_errors("pipe-1")

    stats = h.get_stats()
    assert stats["total_recorded"] == 2
    assert stats["total_cleared"] == 2
    assert stats["total_lookups"] == 1
    assert stats["current_errors"] == 0
    print("  test_stats PASSED")


def test_reset():
    h = PipelineErrorHandler()
    h.record_error("pipe-1", "step-a", "timeout", "msg1")
    h.on_change("cb1", lambda a, d: None)
    h.handlers["h1"] = lambda: None

    h.reset()

    assert len(h.errors) == 0
    assert len(h.handlers) == 0
    assert h._seq == 0
    assert h.get_stats()["total_recorded"] == 0
    assert h.remove_callback("cb1") is False  # callbacks cleared
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_record_error()
    test_get_errors()
    test_get_errors_filtered()
    test_get_error_summary()
    test_clear_errors()
    test_get_error_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
