"""Tests for PipelineStepLimiter."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_limiter import PipelineStepLimiter


def test_set_limit_returns_id():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "step_a", 10)
    assert lid.startswith("psli-")
    assert len(lid) == 5 + 16


def test_set_limit_creates_entry():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "step_b", 5)
    info = svc.get_limit(lid)
    assert info["pipeline_id"] == "pipe1"
    assert info["step_name"] == "step_b"
    assert info["max_executions"] == 5
    assert info["current_executions"] == 0


def test_set_limit_default_max():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "step_c")
    info = svc.get_limit(lid)
    assert info["max_executions"] == 10


def test_record_execution_success():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "step_d", 3)
    assert svc.record_execution(lid) is True
    info = svc.get_limit(lid)
    assert info["current_executions"] == 1


def test_record_execution_exceeds_limit():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "step_e", 2)
    assert svc.record_execution(lid) is True
    assert svc.record_execution(lid) is True
    assert svc.record_execution(lid) is False


def test_record_execution_invalid_id():
    svc = PipelineStepLimiter()
    assert svc.record_execution("psli-nonexistent12345") is False


def test_get_limit_not_found():
    svc = PipelineStepLimiter()
    assert svc.get_limit("psli-nope") is None


def test_get_limits_all():
    svc = PipelineStepLimiter()
    svc.set_limit("pipe1", "s1")
    svc.set_limit("pipe2", "s2")
    svc.set_limit("pipe3", "s3")
    assert len(svc.get_limits()) == 3


def test_get_limits_filtered_by_pipeline():
    svc = PipelineStepLimiter()
    svc.set_limit("alpha", "s1")
    svc.set_limit("beta", "s2")
    svc.set_limit("alpha", "s3")
    results = svc.get_limits(pipeline_id="alpha")
    assert len(results) == 2
    assert all(r["pipeline_id"] == "alpha" for r in results)


def test_get_limits_newest_first():
    svc = PipelineStepLimiter()
    lid1 = svc.set_limit("pipe1", "first")
    lid2 = svc.set_limit("pipe1", "second")
    lid3 = svc.set_limit("pipe1", "third")
    results = svc.get_limits()
    assert results[0]["step_name"] == "third"
    assert results[-1]["step_name"] == "first"


def test_get_limits_respects_limit_param():
    svc = PipelineStepLimiter()
    for i in range(10):
        svc.set_limit("pipe1", f"step_{i}")
    results = svc.get_limits(limit=3)
    assert len(results) == 3


def test_is_allowed_true():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "step_f", 5)
    assert svc.is_allowed(lid) is True


def test_is_allowed_false_when_exceeded():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "step_g", 1)
    svc.record_execution(lid)
    assert svc.is_allowed(lid) is False


def test_is_allowed_invalid_id():
    svc = PipelineStepLimiter()
    assert svc.is_allowed("psli-nonexistent12345") is False


def test_get_limit_count_empty():
    svc = PipelineStepLimiter()
    assert svc.get_limit_count() == 0


def test_get_limit_count_all():
    svc = PipelineStepLimiter()
    svc.set_limit("pipe1", "x")
    svc.set_limit("pipe2", "y")
    assert svc.get_limit_count() == 2


def test_get_limit_count_filtered():
    svc = PipelineStepLimiter()
    svc.set_limit("pipe1", "a")
    svc.set_limit("pipe2", "b")
    svc.set_limit("pipe1", "c")
    assert svc.get_limit_count(pipeline_id="pipe1") == 2
    assert svc.get_limit_count(pipeline_id="pipe2") == 1


def test_get_stats():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "stat_step", 2)
    svc.record_execution(lid)
    svc.record_execution(lid)
    svc.record_execution(lid)  # denied
    stats = svc.get_stats()
    assert stats["total_limits"] == 1
    assert stats["total_executions"] == 2
    assert stats["exceeded_count"] == 1


def test_get_stats_empty():
    svc = PipelineStepLimiter()
    stats = svc.get_stats()
    assert stats["total_limits"] == 0
    assert stats["total_executions"] == 0
    assert stats["exceeded_count"] == 0


def test_reset():
    svc = PipelineStepLimiter()
    svc.set_limit("pipe1", "r1")
    svc.set_limit("pipe2", "r2")
    svc.reset()
    assert svc.get_limit_count() == 0
    assert svc.get_stats()["total_executions"] == 0


def test_on_change_property():
    svc = PipelineStepLimiter()
    events = []
    svc.on_change = lambda e, data: events.append(e)
    svc.set_limit("pipe1", "oc_step")
    assert len(events) == 1
    assert events[0] == "limit_set"


def test_on_change_fires_on_record():
    svc = PipelineStepLimiter()
    events = []
    svc.on_change = lambda e, data: events.append(e)
    lid = svc.set_limit("pipe1", "rec_step", 2)
    svc.record_execution(lid)
    assert "execution_recorded" in events


def test_on_change_fires_on_denied():
    svc = PipelineStepLimiter()
    events = []
    svc.on_change = lambda e, data: events.append(e)
    lid = svc.set_limit("pipe1", "deny_step", 1)
    svc.record_execution(lid)
    svc.record_execution(lid)  # denied
    assert "execution_denied" in events


def test_callbacks_and_remove():
    svc = PipelineStepLimiter()
    events = []
    svc._callbacks["my_cb"] = lambda e, data: events.append(e)
    svc.set_limit("pipe1", "cb_step")
    assert len(events) == 1
    assert svc.remove_callback("my_cb") is True
    assert svc.remove_callback("my_cb") is False
    svc.set_limit("pipe1", "cb_step2")
    assert len(events) == 1


def test_unique_ids():
    svc = PipelineStepLimiter()
    ids = set()
    for i in range(50):
        ids.add(svc.set_limit(f"pipe_{i}", f"step_{i}"))
    assert len(ids) == 50


def test_callback_exception_handled():
    svc = PipelineStepLimiter()

    def bad_cb(event, data):
        raise ValueError("boom")

    svc._callbacks["bad"] = bad_cb
    lid = svc.set_limit("pipe1", "safe_step")
    assert lid.startswith("psli-")


def test_on_change_exception_handled():
    svc = PipelineStepLimiter()
    svc.on_change = lambda e, d: 1 / 0
    lid = svc.set_limit("pipe1", "safe_step2")
    assert lid.startswith("psli-")


def test_return_dicts():
    svc = PipelineStepLimiter()
    lid = svc.set_limit("pipe1", "dict_step", 5)
    assert isinstance(svc.get_limit(lid), dict)
    assert isinstance(svc.get_limits(), list)
    assert all(isinstance(r, dict) for r in svc.get_limits())
    assert isinstance(svc.get_stats(), dict)


if __name__ == "__main__":
    tests = [
        test_set_limit_returns_id,
        test_set_limit_creates_entry,
        test_set_limit_default_max,
        test_record_execution_success,
        test_record_execution_exceeds_limit,
        test_record_execution_invalid_id,
        test_get_limit_not_found,
        test_get_limits_all,
        test_get_limits_filtered_by_pipeline,
        test_get_limits_newest_first,
        test_get_limits_respects_limit_param,
        test_is_allowed_true,
        test_is_allowed_false_when_exceeded,
        test_is_allowed_invalid_id,
        test_get_limit_count_empty,
        test_get_limit_count_all,
        test_get_limit_count_filtered,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_property,
        test_on_change_fires_on_record,
        test_on_change_fires_on_denied,
        test_callbacks_and_remove,
        test_unique_ids,
        test_callback_exception_handled,
        test_on_change_exception_handled,
        test_return_dicts,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
