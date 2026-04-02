"""Tests for PipelineStepBatcher."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_batcher import PipelineStepBatcher


def test_register_batcher():
    b = PipelineStepBatcher()
    bid = b.register_batcher("step_a", 5)
    assert bid.startswith("psba-")
    assert len(bid) == 5 + 16


def test_register_creates_entry():
    b = PipelineStepBatcher()
    bid = b.register_batcher("step_b", 3)
    info = b.get_batcher(bid)
    assert info["step_name"] == "step_b"
    assert info["batch_size"] == 3
    assert info["buffer_size"] == 0
    assert info["total_batches"] == 0
    assert info["total_items"] == 0


def test_add_item_no_flush():
    b = PipelineStepBatcher()
    bid = b.register_batcher("step_c", 3)
    result = b.add_item(bid, "item1")
    assert result["flushed"] is False
    assert result["buffer_size"] == 1


def test_add_item_triggers_flush():
    b = PipelineStepBatcher()
    bid = b.register_batcher("step_d", 2)
    b.add_item(bid, "a")
    result = b.add_item(bid, "b")
    assert result["flushed"] is True
    assert result["batch"] == ["a", "b"]
    assert result["batch_number"] == 1


def test_add_item_multiple_flushes():
    b = PipelineStepBatcher()
    bid = b.register_batcher("step_e", 2)
    b.add_item(bid, 1)
    b.add_item(bid, 2)
    b.add_item(bid, 3)
    result = b.add_item(bid, 4)
    assert result["flushed"] is True
    assert result["batch"] == [3, 4]
    assert result["batch_number"] == 2


def test_add_item_invalid_id():
    b = PipelineStepBatcher()
    result = b.add_item("psba-nonexistent12345", "x")
    assert result == {}


def test_flush_with_items():
    b = PipelineStepBatcher()
    bid = b.register_batcher("step_f", 10)
    b.add_item(bid, "x")
    b.add_item(bid, "y")
    result = b.flush(bid)
    assert result["batch"] == ["x", "y"]
    assert result["size"] == 2
    assert result["batch_number"] == 1


def test_flush_empty_buffer():
    b = PipelineStepBatcher()
    bid = b.register_batcher("step_g", 5)
    result = b.flush(bid)
    assert result["batch"] == []
    assert result["size"] == 0


def test_flush_invalid_id():
    b = PipelineStepBatcher()
    result = b.flush("psba-nope")
    assert result == {}


def test_get_batcher_not_found():
    b = PipelineStepBatcher()
    assert b.get_batcher("psba-nope") == {}


def test_get_batchers_all():
    b = PipelineStepBatcher()
    b.register_batcher("s1")
    b.register_batcher("s2")
    b.register_batcher("s3")
    assert len(b.get_batchers()) == 3


def test_get_batchers_filtered():
    b = PipelineStepBatcher()
    b.register_batcher("alpha")
    b.register_batcher("beta")
    b.register_batcher("alpha")
    results = b.get_batchers(step_name="alpha")
    assert len(results) == 2
    assert all(r["step_name"] == "alpha" for r in results)


def test_get_batcher_count():
    b = PipelineStepBatcher()
    assert b.get_batcher_count() == 0
    b.register_batcher("x")
    b.register_batcher("y")
    assert b.get_batcher_count() == 2


def test_remove_batcher():
    b = PipelineStepBatcher()
    bid = b.register_batcher("rem")
    assert b.remove_batcher(bid) is True
    assert b.get_batcher_count() == 0
    assert b.remove_batcher(bid) is False


def test_get_stats():
    b = PipelineStepBatcher()
    bid = b.register_batcher("stat_step", 2)
    b.add_item(bid, "a")
    b.add_item(bid, "b")
    b.add_item(bid, "c")
    stats = b.get_stats()
    assert stats["total_batchers"] == 1
    assert stats["total_batches_flushed"] == 1
    assert stats["total_items_processed"] == 3


def test_get_stats_empty():
    b = PipelineStepBatcher()
    stats = b.get_stats()
    assert stats["total_batchers"] == 0
    assert stats["total_batches_flushed"] == 0
    assert stats["total_items_processed"] == 0


def test_reset():
    b = PipelineStepBatcher()
    b.register_batcher("r1")
    b.register_batcher("r2")
    b.reset()
    assert b.get_batcher_count() == 0
    assert b.get_stats()["total_items_processed"] == 0


def test_on_change_property():
    b = PipelineStepBatcher()
    events = []
    b.on_change = lambda e, data: events.append(e)
    b.register_batcher("oc_step")
    assert len(events) == 1
    assert events[0] == "batcher_registered"


def test_callbacks_and_remove():
    b = PipelineStepBatcher()
    events = []
    b._callbacks["my_cb"] = lambda e, data: events.append(e)
    b.register_batcher("cb_step")
    assert len(events) == 1
    assert b.remove_callback("my_cb") is True
    assert b.remove_callback("my_cb") is False
    b.register_batcher("cb_step2")
    assert len(events) == 1


def test_unique_ids():
    b = PipelineStepBatcher()
    ids = set()
    for i in range(50):
        ids.add(b.register_batcher(f"step_{i}"))
    assert len(ids) == 50


def test_callback_exception_handled():
    b = PipelineStepBatcher()

    def bad_cb(event, data):
        raise ValueError("boom")

    b._callbacks["bad"] = bad_cb
    bid = b.register_batcher("safe_step")
    assert bid.startswith("psba-")


def test_buffer_clears_after_flush():
    b = PipelineStepBatcher()
    bid = b.register_batcher("clear_step", 2)
    b.add_item(bid, "a")
    b.add_item(bid, "b")
    info = b.get_batcher(bid)
    assert info["buffer_size"] == 0


if __name__ == "__main__":
    tests = [
        test_register_batcher,
        test_register_creates_entry,
        test_add_item_no_flush,
        test_add_item_triggers_flush,
        test_add_item_multiple_flushes,
        test_add_item_invalid_id,
        test_flush_with_items,
        test_flush_empty_buffer,
        test_flush_invalid_id,
        test_get_batcher_not_found,
        test_get_batchers_all,
        test_get_batchers_filtered,
        test_get_batcher_count,
        test_remove_batcher,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_property,
        test_callbacks_and_remove,
        test_unique_ids,
        test_callback_exception_handled,
        test_buffer_clears_after_flush,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
