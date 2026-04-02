"""Tests for PipelineStepLoggerV2."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_logger_v2 import PipelineStepLoggerV2


def run_tests():
    passed = 0
    failed = 0
    total = 0

    def test(name, fn):
        nonlocal passed, failed, total
        total += 1
        try:
            fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL: {name} — {e}")

    # 1
    def test_log_returns_id():
        svc = PipelineStepLoggerV2()
        log_id = svc.log("p1", "step1")
        assert log_id.startswith("pslv2-"), f"Bad prefix: {log_id}"
        assert len(log_id) > 6
    test("log returns id with prefix", test_log_returns_id)

    # 2
    def test_get_log():
        svc = PipelineStepLoggerV2()
        log_id = svc.log("p1", "step1", message="hello")
        entry = svc.get_log(log_id)
        assert entry is not None
        assert entry["pipeline_id"] == "p1"
        assert entry["step_name"] == "step1"
        assert entry["message"] == "hello"
        assert entry["level"] == "info"
    test("get_log retrieves entry", test_get_log)

    # 3
    def test_get_log_not_found():
        svc = PipelineStepLoggerV2()
        assert svc.get_log("nonexistent") is None
    test("get_log returns None for missing", test_get_log_not_found)

    # 4
    def test_get_logs_filter_pipeline():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1")
        svc.log("p2", "s1")
        svc.log("p1", "s2")
        logs = svc.get_logs("p1")
        assert len(logs) == 2
        for l in logs:
            assert l["pipeline_id"] == "p1"
    test("get_logs filters by pipeline_id", test_get_logs_filter_pipeline)

    # 5
    def test_get_logs_filter_step():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1")
        svc.log("p1", "s2")
        svc.log("p1", "s1")
        logs = svc.get_logs("p1", step_name="s1")
        assert len(logs) == 2
    test("get_logs filters by step_name", test_get_logs_filter_step)

    # 6
    def test_get_logs_filter_level():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1", level="error")
        svc.log("p1", "s1", level="info")
        svc.log("p1", "s1", level="error")
        logs = svc.get_logs("p1", level="error")
        assert len(logs) == 2
    test("get_logs filters by level", test_get_logs_filter_level)

    # 7
    def test_get_logs_sorted_newest_first():
        svc = PipelineStepLoggerV2()
        id1 = svc.log("p1", "s1", message="first")
        id2 = svc.log("p1", "s1", message="second")
        logs = svc.get_logs("p1")
        assert logs[0]["message"] == "second"
        assert logs[1]["message"] == "first"
    test("get_logs sorted newest first", test_get_logs_sorted_newest_first)

    # 8
    def test_get_logs_limit():
        svc = PipelineStepLoggerV2()
        for i in range(10):
            svc.log("p1", "s1")
        logs = svc.get_logs("p1", limit=3)
        assert len(logs) == 3
    test("get_logs respects limit", test_get_logs_limit)

    # 9
    def test_get_log_count():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1")
        svc.log("p1", "s1", level="error")
        svc.log("p2", "s1")
        assert svc.get_log_count(pipeline_id="p1") == 2
        assert svc.get_log_count(level="error") == 1
        assert svc.get_log_count() == 3
    test("get_log_count with filters", test_get_log_count)

    # 10
    def test_clear_logs():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1")
        svc.log("p1", "s2")
        svc.log("p2", "s1")
        removed = svc.clear_logs("p1")
        assert removed == 2
        assert svc.get_log_count(pipeline_id="p1") == 0
        assert svc.get_log_count() == 1
    test("clear_logs removes pipeline entries", test_clear_logs)

    # 11
    def test_get_levels_summary():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1", level="debug")
        svc.log("p1", "s1", level="info")
        svc.log("p1", "s1", level="info")
        svc.log("p1", "s1", level="error")
        summary = svc.get_levels_summary("p1")
        assert summary == {"debug": 1, "info": 2, "warning": 0, "error": 1}
    test("get_levels_summary counts per level", test_get_levels_summary)

    # 12
    def test_get_stats():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1", level="info")
        svc.log("p2", "s1", level="error")
        svc.log("p1", "s2", level="debug")
        stats = svc.get_stats()
        assert stats["total_logs"] == 3
        assert stats["total_pipelines"] == 2
        assert stats["logs_by_level"]["info"] == 1
        assert stats["logs_by_level"]["error"] == 1
        assert stats["logs_by_level"]["debug"] == 1
    test("get_stats returns correct totals", test_get_stats)

    # 13
    def test_reset():
        svc = PipelineStepLoggerV2()
        svc.log("p1", "s1")
        svc.log("p2", "s2")
        svc.reset()
        assert svc.get_log_count() == 0
        assert svc.get_stats()["total_logs"] == 0
    test("reset clears all state", test_reset)

    # 14
    def test_on_change_callback():
        events = []
        svc = PipelineStepLoggerV2()
        svc.on_change = lambda evt, data: events.append((evt, data))
        svc.log("p1", "s1")
        assert len(events) == 1
        assert events[0][0] == "log_created"
    test("on_change fires on log", test_on_change_callback)

    # 15
    def test_register_and_remove_callback():
        events = []
        svc = PipelineStepLoggerV2()
        svc.register_callback("cb1", lambda e, d: events.append(e))
        svc.log("p1", "s1")
        assert len(events) == 1
        assert svc.remove_callback("cb1") is True
        svc.log("p1", "s1")
        assert len(events) == 1  # no new event
        assert svc.remove_callback("cb1") is False
    test("register and remove callback", test_register_and_remove_callback)

    # 16
    def test_callback_exception_handled():
        svc = PipelineStepLoggerV2()
        def _raise(e, d):
            raise RuntimeError("boom")
        svc.on_change = _raise
        # Should not raise
        log_id = svc.log("p1", "s1")
        assert log_id is not None
    test("callback exception is caught", test_callback_exception_handled)

    # 17
    def test_metadata_stored():
        svc = PipelineStepLoggerV2()
        log_id = svc.log("p1", "s1", metadata={"key": "value", "count": 42})
        entry = svc.get_log(log_id)
        assert entry["metadata"]["key"] == "value"
        assert entry["metadata"]["count"] == 42
    test("metadata is stored correctly", test_metadata_stored)

    # 18
    def test_unique_ids():
        svc = PipelineStepLoggerV2()
        ids = set()
        for i in range(100):
            ids.add(svc.log("p1", "s1"))
        assert len(ids) == 100
    test("generated IDs are unique", test_unique_ids)

    print(f"{passed}/{total} tests passed")


if __name__ == "__main__":
    run_tests()
