"""Tests for PipelineStepDebouncer."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_debouncer import PipelineStepDebouncer


def test_register_debounce():
    d = PipelineStepDebouncer()
    did = d.register_debounce("step_a", 1.0)
    assert did.startswith("psdb-")
    assert len(did) == 5 + 16


def test_register_creates_entry():
    d = PipelineStepDebouncer()
    did = d.register_debounce("step_b", 2.0)
    info = d.get_debounce(did)
    assert info["step_name"] == "step_b"
    assert info["window_seconds"] == 2.0
    assert info["last_execution_at"] == 0
    assert info["total_calls"] == 0
    assert info["total_debounced"] == 0


def test_should_execute_first_call():
    d = PipelineStepDebouncer()
    did = d.register_debounce("step_c", 1.0)
    assert d.should_execute(did) is True


def test_should_execute_debounced():
    d = PipelineStepDebouncer()
    did = d.register_debounce("step_d", 10.0)
    assert d.should_execute(did) is True
    assert d.should_execute(did) is False


def test_should_execute_after_window():
    d = PipelineStepDebouncer()
    did = d.register_debounce("step_e", 0.05)
    assert d.should_execute(did) is True
    time.sleep(0.06)
    assert d.should_execute(did) is True


def test_should_execute_invalid_id():
    d = PipelineStepDebouncer()
    assert d.should_execute("psdb-nonexistent1234") is False


def test_force_execute():
    d = PipelineStepDebouncer()
    did = d.register_debounce("step_f", 10.0)
    d.should_execute(did)
    assert d.force_execute(did) is True
    info = d.get_debounce(did)
    assert info["total_calls"] == 2


def test_force_execute_invalid_id():
    d = PipelineStepDebouncer()
    assert d.force_execute("psdb-nonexistent1234") is False


def test_get_debounce_not_found():
    d = PipelineStepDebouncer()
    assert d.get_debounce("psdb-nope") == {}


def test_get_debounces_all():
    d = PipelineStepDebouncer()
    d.register_debounce("s1")
    d.register_debounce("s2")
    d.register_debounce("s3")
    assert len(d.get_debounces()) == 3


def test_get_debounces_filtered():
    d = PipelineStepDebouncer()
    d.register_debounce("alpha")
    d.register_debounce("beta")
    d.register_debounce("alpha")
    results = d.get_debounces(step_name="alpha")
    assert len(results) == 2
    assert all(r["step_name"] == "alpha" for r in results)


def test_get_debounce_count():
    d = PipelineStepDebouncer()
    assert d.get_debounce_count() == 0
    d.register_debounce("x")
    d.register_debounce("y")
    assert d.get_debounce_count() == 2


def test_remove_debounce():
    d = PipelineStepDebouncer()
    did = d.register_debounce("rem")
    assert d.remove_debounce(did) is True
    assert d.get_debounce_count() == 0
    assert d.remove_debounce(did) is False


def test_get_stats():
    d = PipelineStepDebouncer()
    did = d.register_debounce("stat_step", 10.0)
    d.should_execute(did)
    d.should_execute(did)
    d.should_execute(did)
    stats = d.get_stats()
    assert stats["total_debounces"] == 1
    assert stats["total_calls"] == 1
    assert stats["total_debounced"] == 2
    assert stats["hit_rate"] == 2.0 / 1.0


def test_get_stats_empty():
    d = PipelineStepDebouncer()
    stats = d.get_stats()
    assert stats["hit_rate"] == 0


def test_reset():
    d = PipelineStepDebouncer()
    d.register_debounce("r1")
    d.register_debounce("r2")
    d.reset()
    assert d.get_debounce_count() == 0
    assert d.get_stats()["total_calls"] == 0


def test_on_change_property():
    d = PipelineStepDebouncer()
    events = []
    d.on_change = lambda e, data: events.append(e)
    d.register_debounce("oc_step")
    assert len(events) == 1
    assert events[0] == "debounce_registered"


def test_callbacks_and_remove():
    d = PipelineStepDebouncer()
    events = []
    d._callbacks["my_cb"] = lambda e, data: events.append(e)
    d.register_debounce("cb_step")
    assert len(events) == 1
    assert d.remove_callback("my_cb") is True
    assert d.remove_callback("my_cb") is False
    d.register_debounce("cb_step2")
    assert len(events) == 1


def test_unique_ids():
    d = PipelineStepDebouncer()
    ids = set()
    for i in range(50):
        ids.add(d.register_debounce(f"step_{i}"))
    assert len(ids) == 50


def test_callback_exception_handled():
    d = PipelineStepDebouncer()

    def bad_cb(event, data):
        raise ValueError("boom")

    d._callbacks["bad"] = bad_cb
    # Should not raise
    did = d.register_debounce("safe_step")
    assert did.startswith("psdb-")


if __name__ == "__main__":
    tests = [
        test_register_debounce,
        test_register_creates_entry,
        test_should_execute_first_call,
        test_should_execute_debounced,
        test_should_execute_after_window,
        test_should_execute_invalid_id,
        test_force_execute,
        test_force_execute_invalid_id,
        test_get_debounce_not_found,
        test_get_debounces_all,
        test_get_debounces_filtered,
        test_get_debounce_count,
        test_remove_debounce,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_property,
        test_callbacks_and_remove,
        test_unique_ids,
        test_callback_exception_handled,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
