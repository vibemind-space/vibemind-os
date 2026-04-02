"""Tests for PipelineStepDelayer."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_delayer import PipelineStepDelayer


def test_prefix():
    s = PipelineStepDelayer()
    rid = s.delay("p1", "s1")
    assert rid.startswith("psdl-")


def test_id_length():
    s = PipelineStepDelayer()
    rid = s.delay("p1", "s1")
    assert len(rid) == 5 + 16


def test_unique_ids():
    s = PipelineStepDelayer()
    ids = set()
    for i in range(50):
        ids.add(s.delay(f"p{i}", f"s{i}"))
    assert len(ids) == 50


def test_fields():
    s = PipelineStepDelayer()
    rid = s.delay("pipe1", "step1", 5.0, {"key": "val"})
    info = s.get_delay(rid)
    assert info["record_id"] == rid
    assert info["pipeline_id"] == "pipe1"
    assert info["step_name"] == "step1"
    assert info["delay_seconds"] == 5.0
    assert info["metadata"] == {"key": "val"}


def test_deepcopy_metadata():
    s = PipelineStepDelayer()
    meta = {"a": [1, 2, 3]}
    rid = s.delay("p1", "s1", metadata=meta)
    meta["a"].append(4)
    info = s.get_delay(rid)
    assert info["metadata"]["a"] == [1, 2, 3]


def test_created_at():
    s = PipelineStepDelayer()
    before = time.time()
    rid = s.delay("p1", "s1")
    after = time.time()
    info = s.get_delay(rid)
    assert before <= info["created_at"] <= after


def test_empty_pipeline_id():
    s = PipelineStepDelayer()
    result = s.delay("", "s1")
    assert result == ""


def test_empty_step_name():
    s = PipelineStepDelayer()
    result = s.delay("p1", "")
    assert result == ""


def test_both_empty():
    s = PipelineStepDelayer()
    result = s.delay("", "")
    assert result == ""


def test_get_delay_found():
    s = PipelineStepDelayer()
    rid = s.delay("p1", "s1")
    info = s.get_delay(rid)
    assert info is not None
    assert info["record_id"] == rid


def test_get_delay_not_found():
    s = PipelineStepDelayer()
    assert s.get_delay("psdl-nonexistent12345") is None


def test_get_delay_returns_copy():
    s = PipelineStepDelayer()
    rid = s.delay("p1", "s1")
    info = s.get_delay(rid)
    info["pipeline_id"] = "modified"
    assert s.get_delay(rid)["pipeline_id"] == "p1"


def test_get_delays_all():
    s = PipelineStepDelayer()
    s.delay("p1", "s1")
    s.delay("p2", "s2")
    s.delay("p3", "s3")
    results = s.get_delays()
    assert len(results) == 3


def test_get_delays_filter_by_pipeline():
    s = PipelineStepDelayer()
    s.delay("alpha", "s1")
    s.delay("beta", "s2")
    s.delay("alpha", "s3")
    results = s.get_delays(pipeline_id="alpha")
    assert len(results) == 2
    assert all(r["pipeline_id"] == "alpha" for r in results)


def test_get_delays_newest_first():
    s = PipelineStepDelayer()
    r1 = s.delay("p1", "s1")
    r2 = s.delay("p1", "s2")
    r3 = s.delay("p1", "s3")
    results = s.get_delays()
    assert results[0]["record_id"] == r3
    assert results[1]["record_id"] == r2
    assert results[2]["record_id"] == r1


def test_get_delays_limit():
    s = PipelineStepDelayer()
    for i in range(10):
        s.delay("p1", f"s{i}")
    results = s.get_delays(limit=3)
    assert len(results) == 3


def test_get_delay_count_total():
    s = PipelineStepDelayer()
    assert s.get_delay_count() == 0
    s.delay("p1", "s1")
    s.delay("p2", "s2")
    assert s.get_delay_count() == 2


def test_get_delay_count_by_pipeline():
    s = PipelineStepDelayer()
    s.delay("alpha", "s1")
    s.delay("beta", "s2")
    s.delay("alpha", "s3")
    assert s.get_delay_count(pipeline_id="alpha") == 2
    assert s.get_delay_count(pipeline_id="beta") == 1
    assert s.get_delay_count(pipeline_id="gamma") == 0


def test_get_stats():
    s = PipelineStepDelayer()
    s.delay("p1", "s1")
    s.delay("p1", "s2")
    s.delay("p2", "s3")
    stats = s.get_stats()
    assert stats["total_delays"] == 3
    assert stats["unique_pipelines"] == 2


def test_get_stats_empty():
    s = PipelineStepDelayer()
    stats = s.get_stats()
    assert stats["total_delays"] == 0
    assert stats["unique_pipelines"] == 0


def test_on_change_callback():
    s = PipelineStepDelayer()
    events = []
    s.on_change = lambda e, data: events.append(e)
    s.delay("p1", "s1")
    assert len(events) == 1
    assert events[0] == "delayed"


def test_on_change_property_getter():
    s = PipelineStepDelayer()
    assert s.on_change is None
    fn = lambda e, d: None
    s.on_change = fn
    assert s.on_change is fn


def test_callbacks_via_state():
    s = PipelineStepDelayer()
    events = []
    s._state.callbacks["my_cb"] = lambda e, data: events.append(e)
    s.delay("p1", "s1")
    assert len(events) == 1
    assert events[0] == "delayed"


def test_remove_callback():
    s = PipelineStepDelayer()
    s._state.callbacks["cb1"] = lambda e, d: None
    assert s.remove_callback("cb1") is True
    assert s.remove_callback("cb1") is False


def test_callback_exception_handled():
    s = PipelineStepDelayer()

    def bad_cb(event, data):
        raise ValueError("boom")

    s._state.callbacks["bad"] = bad_cb
    rid = s.delay("p1", "s1")
    assert rid.startswith("psdl-")


def test_on_change_exception_handled():
    s = PipelineStepDelayer()
    s.on_change = lambda e, d: (_ for _ in ()).throw(RuntimeError("fail"))
    rid = s.delay("p1", "s1")
    assert rid.startswith("psdl-")


def test_prune_over_max():
    s = PipelineStepDelayer()
    s.MAX_ENTRIES = 5
    for i in range(8):
        s.delay(f"p{i}", f"s{i}")
    assert s.get_delay_count() == 5


def test_prune_keeps_newest():
    s = PipelineStepDelayer()
    s.MAX_ENTRIES = 5
    ids = []
    for i in range(8):
        ids.append(s.delay(f"p{i}", f"s{i}"))
    # Oldest should be pruned, newest kept
    for rid in ids[-5:]:
        assert s.get_delay(rid) is not None


def test_prune_under_max():
    s = PipelineStepDelayer()
    s.MAX_ENTRIES = 5
    for i in range(3):
        s.delay(f"p{i}", f"s{i}")
    assert s.get_delay_count() == 3


def test_reset_clears_entries():
    s = PipelineStepDelayer()
    s.delay("p1", "s1")
    s.delay("p2", "s2")
    s.reset()
    assert s.get_delay_count() == 0


def test_reset_clears_callbacks():
    s = PipelineStepDelayer()
    s._state.callbacks["cb"] = lambda e, d: None
    s.on_change = lambda e, d: None
    s.reset()
    assert len(s._state.callbacks) == 0
    assert s.on_change is None


def test_reset_clears_seq():
    s = PipelineStepDelayer()
    s.delay("p1", "s1")
    s.delay("p2", "s2")
    s.reset()
    assert s._state._seq == 0


def test_default_delay_seconds():
    s = PipelineStepDelayer()
    rid = s.delay("p1", "s1")
    info = s.get_delay(rid)
    assert info["delay_seconds"] == 0


def test_default_metadata_none():
    s = PipelineStepDelayer()
    rid = s.delay("p1", "s1")
    info = s.get_delay(rid)
    assert info["metadata"] is None


if __name__ == "__main__":
    tests = [
        test_prefix,
        test_id_length,
        test_unique_ids,
        test_fields,
        test_deepcopy_metadata,
        test_created_at,
        test_empty_pipeline_id,
        test_empty_step_name,
        test_both_empty,
        test_get_delay_found,
        test_get_delay_not_found,
        test_get_delay_returns_copy,
        test_get_delays_all,
        test_get_delays_filter_by_pipeline,
        test_get_delays_newest_first,
        test_get_delays_limit,
        test_get_delay_count_total,
        test_get_delay_count_by_pipeline,
        test_get_stats,
        test_get_stats_empty,
        test_on_change_callback,
        test_on_change_property_getter,
        test_callbacks_via_state,
        test_remove_callback,
        test_callback_exception_handled,
        test_on_change_exception_handled,
        test_prune_over_max,
        test_prune_keeps_newest,
        test_prune_under_max,
        test_reset_clears_entries,
        test_reset_clears_callbacks,
        test_reset_clears_seq,
        test_default_delay_seconds,
        test_default_metadata_none,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
