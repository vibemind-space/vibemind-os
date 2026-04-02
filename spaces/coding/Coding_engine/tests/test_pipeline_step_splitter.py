"""Tests for PipelineStepSplitter."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_splitter import PipelineStepSplitter, PipelineStepSplitterState


def test_initial_state():
    pss = PipelineStepSplitter()
    assert pss.get_split_count() == 0
    assert pss.get_stats() == {"total_splits": 0, "total_executions": 0, "total_sub_steps": 0}


def test_register_split():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a", "b", "c"])
    assert sid.startswith("pss2-")
    assert len(sid) == 5 + 16
    assert pss.get_split_count() == 1


def test_register_split_parallel_mode():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a", "b"], mode="parallel")
    info = pss.get_split(sid)
    assert info["mode"] == "parallel"
    assert info["step_name"] == "step1"
    assert info["sub_steps"] == ["a", "b"]


def test_get_split():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a", "b"])
    info = pss.get_split(sid)
    assert info["split_id"] == sid
    assert info["step_name"] == "step1"
    assert info["sub_steps"] == ["a", "b"]
    assert info["execution_count"] == 0
    assert "created_at" in info


def test_get_split_not_found():
    pss = PipelineStepSplitter()
    try:
        pss.get_split("nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_get_splits_all():
    pss = PipelineStepSplitter()
    pss.register_split("step1", ["a"])
    pss.register_split("step2", ["b"])
    splits = pss.get_splits()
    assert len(splits) == 2


def test_get_splits_filtered():
    pss = PipelineStepSplitter()
    pss.register_split("step1", ["a"])
    pss.register_split("step2", ["b"])
    pss.register_split("step1", ["c"])
    splits = pss.get_splits(step_name="step1")
    assert len(splits) == 2
    for s in splits:
        assert s["step_name"] == "step1"


def test_execute_split():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a", "b", "c"])
    result = pss.execute_split(sid, {"key": "val"})
    assert result["split_id"] == sid
    assert result["step_name"] == "step1"
    assert result["mode"] == "sequential"
    assert result["total_sub_steps"] == 3
    assert len(result["sub_results"]) == 3
    for sr in result["sub_results"]:
        assert sr["status"] == "success"
        assert sr["context"] == {"key": "val"}
    info = pss.get_split(sid)
    assert info["execution_count"] == 1


def test_execute_split_not_found():
    pss = PipelineStepSplitter()
    try:
        pss.execute_split("nonexistent", {})
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_add_sub_step():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a"])
    assert pss.add_sub_step(sid, "b") is True
    info = pss.get_split(sid)
    assert info["sub_steps"] == ["a", "b"]


def test_add_sub_step_not_found():
    pss = PipelineStepSplitter()
    assert pss.add_sub_step("nonexistent", "x") is False


def test_remove_sub_step():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a", "b", "c"])
    assert pss.remove_sub_step(sid, "b") is True
    info = pss.get_split(sid)
    assert info["sub_steps"] == ["a", "c"]


def test_remove_sub_step_not_found():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a"])
    assert pss.remove_sub_step(sid, "z") is False
    assert pss.remove_sub_step("nonexistent", "a") is False


def test_remove_split():
    pss = PipelineStepSplitter()
    sid = pss.register_split("step1", ["a"])
    assert pss.remove_split(sid) is True
    assert pss.get_split_count() == 0
    assert pss.remove_split(sid) is False


def test_get_stats():
    pss = PipelineStepSplitter()
    sid1 = pss.register_split("step1", ["a", "b"])
    sid2 = pss.register_split("step2", ["c", "d", "e"])
    pss.execute_split(sid1, {})
    pss.execute_split(sid1, {})
    pss.execute_split(sid2, {})
    stats = pss.get_stats()
    assert stats["total_splits"] == 2
    assert stats["total_executions"] == 3
    assert stats["total_sub_steps"] == 5


def test_reset():
    pss = PipelineStepSplitter()
    pss.register_split("step1", ["a"])
    pss.register_split("step2", ["b"])
    pss.reset()
    assert pss.get_split_count() == 0
    assert pss.get_stats()["total_splits"] == 0


def test_on_change_callback():
    events = []
    pss = PipelineStepSplitter()
    pss.on_change = lambda event, data: events.append((event, data))
    pss.register_split("step1", ["a"])
    assert len(events) == 1
    assert events[0][0] == "register_split"


def test_remove_callback():
    called = []
    pss = PipelineStepSplitter()
    pss._callbacks["cb1"] = lambda e, d: called.append(e)
    pss.register_split("step1", ["a"])
    assert len(called) == 1
    assert pss.remove_callback("cb1") is True
    assert pss.remove_callback("cb1") is False
    pss.register_split("step2", ["b"])
    assert len(called) == 1  # no more calls after removal


def test_generate_id_uniqueness():
    pss = PipelineStepSplitter()
    ids = set()
    for i in range(50):
        sid = pss.register_split(f"step{i}", ["a"])
        ids.add(sid)
    assert len(ids) == 50


def test_fire_exception_handling():
    pss = PipelineStepSplitter()
    pss.on_change = lambda e, d: (_ for _ in ()).throw(ValueError("boom"))
    pss._callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("oops"))
    # Should not raise
    sid = pss.register_split("step1", ["a"])
    assert pss.get_split_count() == 1


def test_prune():
    pss = PipelineStepSplitter()
    pss.MAX_ENTRIES = 5
    for i in range(8):
        pss.register_split(f"step{i}", ["a"])
    assert pss.get_split_count() <= 5


if __name__ == "__main__":
    tests = [
        test_initial_state,
        test_register_split,
        test_register_split_parallel_mode,
        test_get_split,
        test_get_split_not_found,
        test_get_splits_all,
        test_get_splits_filtered,
        test_execute_split,
        test_execute_split_not_found,
        test_add_sub_step,
        test_add_sub_step_not_found,
        test_remove_sub_step,
        test_remove_sub_step_not_found,
        test_remove_split,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_generate_id_uniqueness,
        test_fire_exception_handling,
        test_prune,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    total = passed + failed
    print(f"{passed}/{total} tests passed")
