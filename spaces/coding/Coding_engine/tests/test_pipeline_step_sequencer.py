"""Tests for PipelineStepSequencer service."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_sequencer import PipelineStepSequencer


def test_register_sequence_returns_id():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("build", ["compile", "link", "package"])
    assert isinstance(sid, str), f"Expected str, got {type(sid)}"
    assert sid.startswith("psseq-"), f"Expected psseq- prefix, got {sid}"
    print("  test_register_sequence_returns_id PASSED")


def test_register_sequence_stores_fields():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("deploy", ["build", "test", "deploy"])
    entry = svc.get_sequence(sid)
    assert entry["name"] == "deploy"
    assert entry["steps"] == ["build", "test", "deploy"]
    assert entry["execution_count"] == 0
    assert "created_at" in entry
    print("  test_register_sequence_stores_fields PASSED")


def test_get_sequence_not_found():
    svc = PipelineStepSequencer()
    result = svc.get_sequence("nonexistent")
    assert result == {}, f"Expected empty dict, got {result}"
    print("  test_get_sequence_not_found PASSED")


def test_get_next_step_first():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("flow", ["a", "b", "c"])
    step = svc.get_next_step(sid)
    assert step == "a", f"Expected 'a', got '{step}'"
    print("  test_get_next_step_first PASSED")


def test_get_next_step_middle():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("flow", ["a", "b", "c"])
    step = svc.get_next_step(sid, "a")
    assert step == "b", f"Expected 'b', got '{step}'"
    print("  test_get_next_step_middle PASSED")


def test_get_next_step_end():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("flow", ["a", "b", "c"])
    step = svc.get_next_step(sid, "c")
    assert step == "", f"Expected empty string at end, got '{step}'"
    print("  test_get_next_step_end PASSED")


def test_get_next_step_invalid_current():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("flow", ["a", "b"])
    step = svc.get_next_step(sid, "z")
    assert step == "", f"Expected empty string for invalid step, got '{step}'"
    print("  test_get_next_step_invalid_current PASSED")


def test_get_next_step_nonexistent_sequence():
    svc = PipelineStepSequencer()
    step = svc.get_next_step("no-such-id")
    assert step == "", f"Expected empty string, got '{step}'"
    print("  test_get_next_step_nonexistent_sequence PASSED")


def test_is_valid_transition_true():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("flow", ["a", "b", "c"])
    assert svc.is_valid_transition(sid, "a", "b") is True
    assert svc.is_valid_transition(sid, "b", "c") is True
    print("  test_is_valid_transition_true PASSED")


def test_is_valid_transition_false():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("flow", ["a", "b", "c"])
    assert svc.is_valid_transition(sid, "a", "c") is False
    assert svc.is_valid_transition(sid, "c", "a") is False
    print("  test_is_valid_transition_false PASSED")


def test_is_valid_transition_nonexistent():
    svc = PipelineStepSequencer()
    assert svc.is_valid_transition("no-id", "a", "b") is False
    print("  test_is_valid_transition_nonexistent PASSED")


def test_execute_sequence():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("build", ["compile", "link"])
    result = svc.execute_sequence(sid)
    assert result["sequence_id"] == sid
    assert result["steps_executed"] == ["compile", "link"]
    assert result["total_steps"] == 2
    entry = svc.get_sequence(sid)
    assert entry["execution_count"] == 1
    print("  test_execute_sequence PASSED")


def test_execute_sequence_increments_count():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("build", ["a", "b"])
    svc.execute_sequence(sid)
    svc.execute_sequence(sid)
    svc.execute_sequence(sid)
    entry = svc.get_sequence(sid)
    assert entry["execution_count"] == 3
    print("  test_execute_sequence_increments_count PASSED")


def test_execute_sequence_nonexistent():
    svc = PipelineStepSequencer()
    result = svc.execute_sequence("no-id")
    assert result["steps_executed"] == []
    assert result["total_steps"] == 0
    print("  test_execute_sequence_nonexistent PASSED")


def test_get_sequences():
    svc = PipelineStepSequencer()
    svc.register_sequence("a", ["s1"])
    svc.register_sequence("b", ["s2", "s3"])
    seqs = svc.get_sequences()
    assert len(seqs) == 2
    names = [s["name"] for s in seqs]
    assert "a" in names and "b" in names
    print("  test_get_sequences PASSED")


def test_get_sequence_count():
    svc = PipelineStepSequencer()
    assert svc.get_sequence_count() == 0
    svc.register_sequence("x", ["s1"])
    assert svc.get_sequence_count() == 1
    print("  test_get_sequence_count PASSED")


def test_remove_sequence():
    svc = PipelineStepSequencer()
    sid = svc.register_sequence("x", ["s1"])
    assert svc.remove_sequence(sid) is True
    assert svc.get_sequence(sid) == {}
    assert svc.remove_sequence(sid) is False
    print("  test_remove_sequence PASSED")


def test_get_stats():
    svc = PipelineStepSequencer()
    sid1 = svc.register_sequence("a", ["s1"])
    sid2 = svc.register_sequence("b", ["s2"])
    svc.execute_sequence(sid1)
    svc.execute_sequence(sid1)
    svc.execute_sequence(sid2)
    stats = svc.get_stats()
    assert stats["total_sequences"] == 2
    assert stats["total_executions"] == 3
    print("  test_get_stats PASSED")


def test_reset():
    svc = PipelineStepSequencer()
    svc.register_sequence("a", ["s1"])
    svc.register_sequence("b", ["s2"])
    svc.reset()
    assert svc.get_sequence_count() == 0
    assert svc.get_sequences() == []
    stats = svc.get_stats()
    assert stats["total_sequences"] == 0
    assert stats["total_executions"] == 0
    print("  test_reset PASSED")


def test_on_change_callback():
    svc = PipelineStepSequencer()
    events = []
    svc.on_change = lambda evt, data: events.append((evt, data))
    svc.register_sequence("x", ["s1"])
    assert len(events) == 1
    assert events[0][0] == "sequence_registered"
    print("  test_on_change_callback PASSED")


def test_remove_callback():
    svc = PipelineStepSequencer()
    svc._callbacks["cb1"] = lambda e, d: None
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False
    print("  test_remove_callback PASSED")


if __name__ == "__main__":
    tests = [
        test_register_sequence_returns_id,
        test_register_sequence_stores_fields,
        test_get_sequence_not_found,
        test_get_next_step_first,
        test_get_next_step_middle,
        test_get_next_step_end,
        test_get_next_step_invalid_current,
        test_get_next_step_nonexistent_sequence,
        test_is_valid_transition_true,
        test_is_valid_transition_false,
        test_is_valid_transition_nonexistent,
        test_execute_sequence,
        test_execute_sequence_increments_count,
        test_execute_sequence_nonexistent,
        test_get_sequences,
        test_get_sequence_count,
        test_remove_sequence,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
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
    total = passed + failed
    print(f"\n{passed}/{total} tests passed")
