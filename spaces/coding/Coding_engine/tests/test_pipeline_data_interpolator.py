"""Tests for PipelineDataInterpolator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_interpolator import PipelineDataInterpolator


class TestInterpolateBasic:
    """Basic interpolate operations."""

    def test_interpolate_returns_string_with_prefix(self):
        svc = PipelineDataInterpolator()
        rid = svc.interpolate("pipe-1", "temperature")
        assert isinstance(rid, str)
        assert rid.startswith("pdin-")

    def test_interpolate_ids_are_unique(self):
        svc = PipelineDataInterpolator()
        ids = [svc.interpolate("pipe-1", f"key-{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_interpolate_stores_fields(self):
        svc = PipelineDataInterpolator()
        rid = svc.interpolate("pipe-1", "pressure", method="cubic", metadata={"unit": "Pa"})
        record = svc.get_interpolation(rid)
        assert record["pipeline_id"] == "pipe-1"
        assert record["data_key"] == "pressure"
        assert record["method"] == "cubic"
        assert record["metadata"]["unit"] == "Pa"
        assert "created_at" in record

    def test_interpolate_default_method_linear(self):
        svc = PipelineDataInterpolator()
        rid = svc.interpolate("pipe-1", "temp")
        record = svc.get_interpolation(rid)
        assert record["method"] == "linear"

    def test_interpolate_metadata_deepcopy(self):
        svc = PipelineDataInterpolator()
        meta = {"nested": {"a": 1}}
        rid = svc.interpolate("pipe-1", "key", metadata=meta)
        meta["nested"]["a"] = 999
        record = svc.get_interpolation(rid)
        assert record["metadata"]["nested"]["a"] == 1

    def test_interpolate_empty_pipeline_id_returns_empty(self):
        svc = PipelineDataInterpolator()
        assert svc.interpolate("", "key") == ""

    def test_interpolate_empty_data_key_returns_empty(self):
        svc = PipelineDataInterpolator()
        assert svc.interpolate("pipe-1", "") == ""

    def test_interpolate_both_empty_returns_empty(self):
        svc = PipelineDataInterpolator()
        assert svc.interpolate("", "") == ""


class TestGetInterpolation:
    """get_interpolation method."""

    def test_get_interpolation_found(self):
        svc = PipelineDataInterpolator()
        rid = svc.interpolate("pipe-1", "key-a")
        result = svc.get_interpolation(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_interpolation_not_found(self):
        svc = PipelineDataInterpolator()
        assert svc.get_interpolation("pdin-nonexistent") is None

    def test_get_interpolation_returns_copy(self):
        svc = PipelineDataInterpolator()
        rid = svc.interpolate("pipe-1", "key-a")
        r1 = svc.get_interpolation(rid)
        r2 = svc.get_interpolation(rid)
        assert r1 is not r2
        assert r1 == r2


class TestGetInterpolations:
    """get_interpolations listing."""

    def test_get_interpolations_all(self):
        svc = PipelineDataInterpolator()
        svc.interpolate("pipe-1", "k1")
        svc.interpolate("pipe-2", "k2")
        svc.interpolate("pipe-1", "k3")
        results = svc.get_interpolations()
        assert len(results) == 3

    def test_get_interpolations_filter_by_pipeline(self):
        svc = PipelineDataInterpolator()
        svc.interpolate("pipe-1", "k1")
        svc.interpolate("pipe-2", "k2")
        svc.interpolate("pipe-1", "k3")
        results = svc.get_interpolations(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_get_interpolations_newest_first(self):
        svc = PipelineDataInterpolator()
        id1 = svc.interpolate("pipe-1", "k1")
        id2 = svc.interpolate("pipe-1", "k2")
        results = svc.get_interpolations()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_interpolations_respects_limit(self):
        svc = PipelineDataInterpolator()
        for i in range(10):
            svc.interpolate("pipe-1", f"k{i}")
        results = svc.get_interpolations(limit=3)
        assert len(results) == 3

    def test_get_interpolations_empty(self):
        svc = PipelineDataInterpolator()
        assert svc.get_interpolations() == []


class TestGetInterpolationCount:
    """get_interpolation_count method."""

    def test_count_all(self):
        svc = PipelineDataInterpolator()
        for i in range(5):
            svc.interpolate("pipe-1", f"k{i}")
        assert svc.get_interpolation_count() == 5

    def test_count_by_pipeline(self):
        svc = PipelineDataInterpolator()
        svc.interpolate("pipe-1", "k1")
        svc.interpolate("pipe-2", "k2")
        svc.interpolate("pipe-1", "k3")
        assert svc.get_interpolation_count(pipeline_id="pipe-1") == 2
        assert svc.get_interpolation_count(pipeline_id="pipe-2") == 1
        assert svc.get_interpolation_count(pipeline_id="pipe-3") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        svc = PipelineDataInterpolator()
        stats = svc.get_stats()
        assert stats["total_interpolations"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        svc = PipelineDataInterpolator()
        svc.interpolate("pipe-1", "k1")
        svc.interpolate("pipe-2", "k2")
        svc.interpolate("pipe-1", "k3")
        stats = svc.get_stats()
        assert stats["total_interpolations"] == 3
        assert stats["unique_pipelines"] == 2


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_interpolate(self):
        svc = PipelineDataInterpolator()
        events = []
        svc.on_change = lambda action: events.append(action)
        svc.interpolate("pipe-1", "k1")
        assert "interpolate" in events

    def test_on_change_property(self):
        svc = PipelineDataInterpolator()
        assert svc.on_change is None
        cb = lambda a: None
        svc.on_change = cb
        assert svc.on_change is cb

    def test_on_change_exception_is_silent(self):
        svc = PipelineDataInterpolator()
        svc.on_change = lambda a: (_ for _ in ()).throw(ValueError("boom"))
        rid = svc.interpolate("pipe-1", "k1")
        assert rid.startswith("pdin-")

    def test_remove_callback(self):
        svc = PipelineDataInterpolator()
        svc._state.callbacks["mycb"] = lambda a: None
        assert svc.remove_callback("mycb") is True
        assert svc.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        svc = PipelineDataInterpolator()
        fired = []
        svc._state.callbacks["tracker"] = lambda a: fired.append(a)
        svc.interpolate("pipe-1", "k1")
        assert "interpolate" in fired

    def test_named_callback_exception_silent(self):
        svc = PipelineDataInterpolator()
        svc._state.callbacks["bad"] = lambda a: 1 / 0
        rid = svc.interpolate("pipe-1", "k1")
        assert rid.startswith("pdin-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        svc = PipelineDataInterpolator()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.interpolate("pipe-1", f"k{i}"))
        assert svc.get_interpolation_count() == 5
        assert svc.get_interpolation(ids[0]) is None
        assert svc.get_interpolation(ids[1]) is None
        assert svc.get_interpolation(ids[6]) is not None


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        svc = PipelineDataInterpolator()
        svc.interpolate("pipe-1", "k1")
        svc.interpolate("pipe-1", "k2")
        assert svc.get_interpolation_count() == 2
        svc.reset()
        assert svc.get_interpolation_count() == 0

    def test_reset_fires_event(self):
        svc = PipelineDataInterpolator()
        events = []
        svc.on_change = lambda action: events.append(action)
        svc.reset()
        assert "reset" in events
