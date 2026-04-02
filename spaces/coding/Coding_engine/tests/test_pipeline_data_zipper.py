"""Tests for pipeline_data_zipper module."""

from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_zipper import PipelineDataZipper, PipelineDataZipperState


def test_initial_state():
    z = PipelineDataZipper()
    assert z.get_stats() == {"total_streams": 0, "total_zips": 0, "total_records": 0}
    assert z.get_streams() == []
    assert z.get_zip_count() == 0


def test_register_stream():
    z = PipelineDataZipper()
    sid = z.register_stream("users", keys=["id"])
    assert sid.startswith("pdz-")
    assert len(sid) == 4 + 16  # prefix + 16 hex chars
    info = z.get_stream(sid)
    assert info["stream_name"] == "users"
    assert info["keys"] == ["id"]
    assert info["record_count"] == 0
    assert "created_at" in info


def test_register_stream_no_keys():
    z = PipelineDataZipper()
    sid = z.register_stream("events")
    info = z.get_stream(sid)
    assert info["keys"] == []


def test_add_records():
    z = PipelineDataZipper()
    sid = z.register_stream("users", keys=["id"])
    z.add_records(sid, [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
    info = z.get_stream(sid)
    assert info["record_count"] == 2


def test_add_records_invalid_stream():
    z = PipelineDataZipper()
    # Should not raise
    z.add_records("nonexistent", [{"a": 1}])


def test_zip_positional():
    z = PipelineDataZipper()
    s1 = z.register_stream("names")
    s2 = z.register_stream("ages")
    z.add_records(s1, [{"name": "Alice"}, {"name": "Bob"}])
    z.add_records(s2, [{"age": 30}, {"age": 25}])
    result = z.zip_streams([s1, s2], mode="positional")
    assert result["mode"] == "positional"
    assert result["stream_count"] == 2
    assert len(result["records"]) == 2
    assert result["records"][0] == {"name": "Alice", "age": 30}
    assert result["records"][1] == {"name": "Bob", "age": 25}
    assert result["zip_id"].startswith("pdz-")


def test_zip_positional_unequal_lengths():
    z = PipelineDataZipper()
    s1 = z.register_stream("a")
    s2 = z.register_stream("b")
    z.add_records(s1, [{"x": 1}, {"x": 2}, {"x": 3}])
    z.add_records(s2, [{"y": 10}])
    result = z.zip_streams([s1, s2], mode="positional")
    assert len(result["records"]) == 3
    assert result["records"][0] == {"x": 1, "y": 10}
    assert result["records"][2] == {"x": 3}


def test_zip_inner():
    z = PipelineDataZipper()
    s1 = z.register_stream("users", keys=["id"])
    s2 = z.register_stream("orders", keys=["id"])
    z.add_records(s1, [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
    z.add_records(s2, [{"id": 1, "total": 100}, {"id": 3, "total": 50}])
    result = z.zip_streams([s1, s2], mode="inner")
    assert result["mode"] == "inner"
    assert len(result["records"]) == 1
    assert result["records"][0]["id"] == 1
    assert result["records"][0]["name"] == "Alice"
    assert result["records"][0]["total"] == 100


def test_zip_outer():
    z = PipelineDataZipper()
    s1 = z.register_stream("users", keys=["id"])
    s2 = z.register_stream("orders", keys=["id"])
    z.add_records(s1, [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
    z.add_records(s2, [{"id": 1, "total": 100}, {"id": 3, "total": 50}])
    result = z.zip_streams([s1, s2], mode="outer")
    assert result["mode"] == "outer"
    assert len(result["records"]) == 3


def test_zip_invalid_mode():
    z = PipelineDataZipper()
    s1 = z.register_stream("a")
    result = z.zip_streams([s1], mode="cross")
    assert result["zip_id"] == ""
    assert result["records"] == []


def test_zip_invalid_stream_ids():
    z = PipelineDataZipper()
    result = z.zip_streams(["fake1", "fake2"])
    assert result["zip_id"] == ""
    assert result["stream_count"] == 0


def test_get_stream_not_found():
    z = PipelineDataZipper()
    assert z.get_stream("nonexistent") == {}


def test_get_streams():
    z = PipelineDataZipper()
    z.register_stream("a")
    z.register_stream("b")
    streams = z.get_streams()
    assert len(streams) == 2
    names = {s["stream_name"] for s in streams}
    assert names == {"a", "b"}


def test_get_zip_count():
    z = PipelineDataZipper()
    s1 = z.register_stream("a")
    s2 = z.register_stream("b")
    z.add_records(s1, [{"x": 1}])
    z.add_records(s2, [{"y": 2}])
    assert z.get_zip_count() == 0
    z.zip_streams([s1, s2], mode="positional")
    assert z.get_zip_count() == 1
    z.zip_streams([s1, s2], mode="positional")
    assert z.get_zip_count() == 2


def test_remove_stream():
    z = PipelineDataZipper()
    sid = z.register_stream("temp")
    assert z.remove_stream(sid) is True
    assert z.remove_stream(sid) is False
    assert z.get_stream(sid) == {}


def test_get_stats():
    z = PipelineDataZipper()
    s1 = z.register_stream("a")
    s2 = z.register_stream("b")
    z.add_records(s1, [{"x": 1}, {"x": 2}])
    z.add_records(s2, [{"y": 10}])
    z.zip_streams([s1, s2], mode="positional")
    stats = z.get_stats()
    assert stats["total_streams"] == 2
    assert stats["total_zips"] == 1
    assert stats["total_records"] == 3


def test_reset():
    z = PipelineDataZipper()
    s1 = z.register_stream("a")
    z.add_records(s1, [{"x": 1}])
    z.zip_streams([s1], mode="positional")
    z.reset()
    assert z.get_stats() == {"total_streams": 0, "total_zips": 0, "total_records": 0}
    assert z.get_streams() == []
    assert z.get_zip_count() == 0


def test_on_change_callback():
    events = []
    z = PipelineDataZipper()
    z.on_change = lambda event, data: events.append((event, data))
    z.register_stream("test")
    assert len(events) == 1
    assert events[0][0] == "stream_registered"


def test_remove_callback():
    z = PipelineDataZipper()
    z._callbacks["my_cb"] = lambda e, d: None
    assert z.remove_callback("my_cb") is True
    assert z.remove_callback("my_cb") is False


def test_callback_exception_handling():
    z = PipelineDataZipper()

    def bad_callback(event, data):
        raise RuntimeError("boom")

    z._callbacks["bad"] = bad_callback
    # Should not raise
    z.register_stream("safe")


def test_generate_id_uniqueness():
    z = PipelineDataZipper()
    ids = set()
    for i in range(100):
        sid = z.register_stream(f"stream_{i}")
        ids.add(sid)
    assert len(ids) == 100


def test_prune():
    z = PipelineDataZipper()
    original_max = PipelineDataZipper.MAX_ENTRIES
    PipelineDataZipper.MAX_ENTRIES = 5
    try:
        for i in range(7):
            z.register_stream(f"s{i}")
        assert len(z._state.entries) <= 5
    finally:
        PipelineDataZipper.MAX_ENTRIES = original_max


def test_state_dataclass():
    state = PipelineDataZipperState()
    assert state.entries == {}
    assert state._seq == 0
    assert state.zip_count == 0


if __name__ == "__main__":
    test_funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    total = len(test_funcs)
    for fn in test_funcs:
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"FAIL: {fn.__name__}: {exc}")
    print(f"{passed}/{total} tests passed")
