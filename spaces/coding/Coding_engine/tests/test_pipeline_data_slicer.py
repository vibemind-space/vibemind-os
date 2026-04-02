"""Tests for PipelineDataSlicer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_slicer import PipelineDataSlicer


class TestSliceFieldsBasic:
    """Basic slice_fields operations."""

    def test_slice_fields_returns_string_id(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_fields({"a": 1, "b": 2}, ["a"])
        assert isinstance(sid, str)
        assert sid.startswith("pdsl-")

    def test_slice_fields_ids_are_unique(self):
        slicer = PipelineDataSlicer()
        ids = [slicer.slice_fields({"k": i}, ["k"]) for i in range(10)]
        assert len(set(ids)) == 10

    def test_slice_fields_extracts_specified_fields(self):
        slicer = PipelineDataSlicer()
        data = {"a": 1, "b": 2, "c": 3}
        sid = slicer.slice_fields(data, ["a", "c"])
        record = slicer.get_slice(sid)
        assert record["data"] == {"a": 1, "c": 3}

    def test_slice_fields_ignores_missing_fields(self):
        slicer = PipelineDataSlicer()
        data = {"a": 1, "b": 2}
        sid = slicer.slice_fields(data, ["a", "z"])
        record = slicer.get_slice(sid)
        assert record["data"] == {"a": 1}

    def test_slice_fields_deep_copies_data(self):
        slicer = PipelineDataSlicer()
        original = {"nested": {"val": 42}, "other": 0}
        sid = slicer.slice_fields(original, ["nested"])
        original["nested"]["val"] = 999
        record = slicer.get_slice(sid)
        assert record["data"]["nested"]["val"] == 42

    def test_slice_fields_with_label(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_fields({"x": 1}, ["x"], label="my-label")
        record = slicer.get_slice(sid)
        assert record["label"] == "my-label"

    def test_slice_fields_stores_type(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_fields({"a": 1}, ["a"])
        record = slicer.get_slice(sid)
        assert record["type"] == "fields"

    def test_slice_fields_stores_fields_list(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_fields({"a": 1, "b": 2}, ["a", "b"])
        record = slicer.get_slice(sid)
        assert set(record["fields"]) == {"a", "b"}


class TestSliceRangeBasic:
    """Basic slice_range operations."""

    def test_slice_range_returns_string_id(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_range([1, 2, 3, 4, 5], 1, 3)
        assert isinstance(sid, str)
        assert sid.startswith("pdsl-")

    def test_slice_range_extracts_correct_range(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_range([10, 20, 30, 40, 50], 1, 4)
        record = slicer.get_slice(sid)
        assert record["data"] == [20, 30, 40]

    def test_slice_range_deep_copies_data(self):
        slicer = PipelineDataSlicer()
        original = [{"v": 1}, {"v": 2}, {"v": 3}]
        sid = slicer.slice_range(original, 0, 2)
        original[0]["v"] = 999
        record = slicer.get_slice(sid)
        assert record["data"][0]["v"] == 1

    def test_slice_range_with_label(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_range([1, 2, 3], 0, 2, label="range-label")
        record = slicer.get_slice(sid)
        assert record["label"] == "range-label"

    def test_slice_range_stores_type(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_range([1, 2], 0, 1)
        record = slicer.get_slice(sid)
        assert record["type"] == "range"

    def test_slice_range_stores_start_end(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_range([1, 2, 3, 4], 1, 3)
        record = slicer.get_slice(sid)
        assert record["start"] == 1
        assert record["end"] == 3


class TestGetSlice:
    """get_slice method."""

    def test_get_slice_existing(self):
        slicer = PipelineDataSlicer()
        sid = slicer.slice_fields({"a": 1}, ["a"])
        result = slicer.get_slice(sid)
        assert result is not None
        assert result["slice_id"] == sid

    def test_get_slice_nonexistent(self):
        slicer = PipelineDataSlicer()
        assert slicer.get_slice("pdsl-nonexistent") is None


class TestGetSlices:
    """get_slices listing."""

    def test_get_slices_returns_list(self):
        slicer = PipelineDataSlicer()
        slicer.slice_fields({"a": 1}, ["a"])
        result = slicer.get_slices()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_slices_newest_first(self):
        slicer = PipelineDataSlicer()
        id1 = slicer.slice_fields({"order": 1}, ["order"])
        id2 = slicer.slice_fields({"order": 2}, ["order"])
        results = slicer.get_slices()
        assert results[0]["slice_id"] == id2
        assert results[1]["slice_id"] == id1

    def test_get_slices_filter_by_label(self):
        slicer = PipelineDataSlicer()
        slicer.slice_fields({"x": 1}, ["x"], label="alpha")
        slicer.slice_fields({"x": 2}, ["x"], label="beta")
        slicer.slice_fields({"x": 3}, ["x"], label="alpha")
        results = slicer.get_slices(label="alpha")
        assert len(results) == 2
        assert all(r["label"] == "alpha" for r in results)

    def test_get_slices_respects_limit(self):
        slicer = PipelineDataSlicer()
        for i in range(10):
            slicer.slice_fields({"i": i}, ["i"])
        results = slicer.get_slices(limit=3)
        assert len(results) == 3

    def test_get_slices_empty(self):
        slicer = PipelineDataSlicer()
        assert slicer.get_slices() == []


class TestGetSliceCount:
    """get_slice_count method."""

    def test_count_all(self):
        slicer = PipelineDataSlicer()
        for i in range(5):
            slicer.slice_fields({"i": i}, ["i"])
        assert slicer.get_slice_count() == 5

    def test_count_by_label(self):
        slicer = PipelineDataSlicer()
        slicer.slice_fields({"x": 1}, ["x"], label="a")
        slicer.slice_range([1, 2], 0, 1, label="b")
        slicer.slice_fields({"x": 3}, ["x"], label="a")
        assert slicer.get_slice_count(label="a") == 2
        assert slicer.get_slice_count(label="b") == 1
        assert slicer.get_slice_count(label="c") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        slicer = PipelineDataSlicer()
        stats = slicer.get_stats()
        assert stats["total_slices"] == 0
        assert stats["unique_labels"] == 0

    def test_stats_populated(self):
        slicer = PipelineDataSlicer()
        slicer.slice_fields({"a": 1}, ["a"], label="x")
        slicer.slice_range([1, 2, 3], 0, 2, label="y")
        slicer.slice_fields({"c": 3}, ["c"], label="x")
        stats = slicer.get_stats()
        assert stats["total_slices"] == 3
        assert stats["unique_labels"] == 2


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        slicer = PipelineDataSlicer()
        slicer.slice_fields({"a": 1}, ["a"])
        slicer.slice_range([1, 2], 0, 1)
        assert slicer.get_slice_count() == 2
        slicer.reset()
        assert slicer.get_slice_count() == 0

    def test_reset_fires_event(self):
        slicer = PipelineDataSlicer()
        events = []
        slicer.on_change = lambda action, data: events.append(action)
        slicer.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_slice_fields(self):
        slicer = PipelineDataSlicer()
        events = []
        slicer.on_change = lambda action, data: events.append((action, data))
        slicer.slice_fields({"x": 1}, ["x"])
        assert len(events) == 1
        assert events[0][0] == "slice_fields"

    def test_on_change_fires_on_slice_range(self):
        slicer = PipelineDataSlicer()
        events = []
        slicer.on_change = lambda action, data: events.append((action, data))
        slicer.slice_range([1, 2, 3], 0, 2)
        assert len(events) == 1
        assert events[0][0] == "slice_range"

    def test_on_change_property(self):
        slicer = PipelineDataSlicer()
        assert slicer.on_change is None
        cb = lambda a, d: None
        slicer.on_change = cb
        assert slicer.on_change is cb

    def test_callback_exception_is_silent(self):
        slicer = PipelineDataSlicer()
        slicer.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        sid = slicer.slice_fields({"x": 1}, ["x"])
        assert sid.startswith("pdsl-")

    def test_remove_callback(self):
        slicer = PipelineDataSlicer()
        slicer._callbacks["mycb"] = lambda a, d: None
        assert slicer.remove_callback("mycb") is True
        assert slicer.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        slicer = PipelineDataSlicer()
        fired = []
        slicer._callbacks["tracker"] = lambda a, d: fired.append(a)
        slicer.slice_fields({"v": 1}, ["v"])
        assert "slice_fields" in fired

    def test_named_callback_exception_silent(self):
        slicer = PipelineDataSlicer()
        slicer._callbacks["bad"] = lambda a, d: 1 / 0
        sid = slicer.slice_fields({"v": 1}, ["v"])
        assert sid.startswith("pdsl-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        slicer = PipelineDataSlicer()
        slicer.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(slicer.slice_fields({"i": i}, ["i"]))
        assert slicer.get_slice_count() == 5
        assert slicer.get_slice(ids[0]) is None
        assert slicer.get_slice(ids[1]) is None
        assert slicer.get_slice(ids[6]) is not None
