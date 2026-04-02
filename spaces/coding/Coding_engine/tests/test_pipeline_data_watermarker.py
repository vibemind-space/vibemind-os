"""Tests for PipelineDataWatermarker service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_watermarker import PipelineDataWatermarker


class TestPrefix:
    """Prefix validation."""

    def test_prefix_is_pdwm(self):
        wm = PipelineDataWatermarker()
        assert wm.PREFIX == "pdwm-"

    def test_watermark_id_starts_with_prefix(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "wm-val")
        assert rid.startswith("pdwm-")


class TestBasicOps:
    """Basic watermark operations."""

    def test_watermark_returns_string_id(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "wm-val")
        assert isinstance(rid, str)

    def test_watermark_ids_are_unique(self):
        wm = PipelineDataWatermarker()
        ids = [wm.watermark("pipe-1", f"k{i}", f"v{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_watermark_stores_pipeline_id(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("my-pipeline", "key-a", "wm-val")
        record = wm.get_watermark(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_watermark_stores_data_key(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "my-key", "wm-val")
        record = wm.get_watermark(rid)
        assert record["data_key"] == "my-key"

    def test_watermark_stores_watermark_value(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "the-watermark")
        record = wm.get_watermark(rid)
        assert record["watermark_value"] == "the-watermark"


class TestMetadata:
    """Metadata handling."""

    def test_watermark_with_metadata(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "wm-val", metadata={"author": "alice"})
        record = wm.get_watermark(rid)
        assert record["metadata"]["author"] == "alice"

    def test_watermark_default_metadata_empty(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "wm-val")
        record = wm.get_watermark(rid)
        assert record["metadata"] == {}

    def test_watermark_metadata_none_becomes_empty_dict(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "wm-val", metadata=None)
        record = wm.get_watermark(rid)
        assert record["metadata"] == {}


class TestGetWatermark:
    """get_watermark method."""

    def test_get_watermark_found(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "wm-val")
        result = wm.get_watermark(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_watermark_not_found(self):
        wm = PipelineDataWatermarker()
        assert wm.get_watermark("pdwm-nonexistent") is None

    def test_get_watermark_returns_dict(self):
        wm = PipelineDataWatermarker()
        rid = wm.watermark("pipe-1", "key-a", "wm-val")
        result = wm.get_watermark(rid)
        assert isinstance(result, dict)


class TestGetWatermarks:
    """get_watermarks listing."""

    def test_get_watermarks_returns_list(self):
        wm = PipelineDataWatermarker()
        wm.watermark("pipe-1", "k1", "v1")
        result = wm.get_watermarks()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_watermarks_filter_by_pipeline_id(self):
        wm = PipelineDataWatermarker()
        wm.watermark("pipe-a", "k1", "v1")
        wm.watermark("pipe-b", "k2", "v2")
        wm.watermark("pipe-a", "k3", "v3")
        results = wm.get_watermarks(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_watermarks_newest_first(self):
        wm = PipelineDataWatermarker()
        id1 = wm.watermark("pipe-1", "k1", "v1")
        id2 = wm.watermark("pipe-1", "k2", "v2")
        results = wm.get_watermarks()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_watermarks_respects_limit(self):
        wm = PipelineDataWatermarker()
        for i in range(10):
            wm.watermark("pipe-1", f"k{i}", f"v{i}")
        results = wm.get_watermarks(limit=3)
        assert len(results) == 3

    def test_get_watermarks_empty(self):
        wm = PipelineDataWatermarker()
        assert wm.get_watermarks() == []


class TestGetWatermarkCount:
    """get_watermark_count method."""

    def test_count_all(self):
        wm = PipelineDataWatermarker()
        for i in range(5):
            wm.watermark("pipe-1", f"k{i}", f"v{i}")
        assert wm.get_watermark_count() == 5

    def test_count_by_pipeline_id(self):
        wm = PipelineDataWatermarker()
        wm.watermark("pipe-a", "k1", "v1")
        wm.watermark("pipe-b", "k2", "v2")
        wm.watermark("pipe-a", "k3", "v3")
        assert wm.get_watermark_count(pipeline_id="pipe-a") == 2
        assert wm.get_watermark_count(pipeline_id="pipe-b") == 1
        assert wm.get_watermark_count(pipeline_id="pipe-c") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        wm = PipelineDataWatermarker()
        stats = wm.get_stats()
        assert stats["total_watermarks"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        wm = PipelineDataWatermarker()
        wm.watermark("pipe-a", "k1", "v1")
        wm.watermark("pipe-b", "k2", "v2")
        wm.watermark("pipe-a", "k3", "v3")
        stats = wm.get_stats()
        assert stats["total_watermarks"] == 3
        assert stats["unique_pipelines"] == 2


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_watermark(self):
        wm = PipelineDataWatermarker()
        events = []
        wm.on_change = lambda action, data: events.append((action, data))
        wm.watermark("pipe-1", "k1", "v1")
        assert len(events) == 1
        assert events[0][0] == "watermark"

    def test_on_change_property(self):
        wm = PipelineDataWatermarker()
        assert wm.on_change is None
        cb = lambda a, d: None
        wm.on_change = cb
        assert wm.on_change is cb

    def test_callback_exception_is_silent(self):
        wm = PipelineDataWatermarker()
        wm.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = wm.watermark("pipe-1", "k1", "v1")
        assert rid.startswith("pdwm-")

    def test_remove_callback(self):
        wm = PipelineDataWatermarker()
        wm._state.callbacks["mycb"] = lambda a, d: None
        assert wm.remove_callback("mycb") is True
        assert wm.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        wm = PipelineDataWatermarker()
        fired = []
        wm._state.callbacks["tracker"] = lambda a, d: fired.append(a)
        wm.watermark("pipe-1", "k1", "v1")
        assert "watermark" in fired

    def test_named_callback_exception_silent(self):
        wm = PipelineDataWatermarker()
        wm._state.callbacks["bad"] = lambda a, d: 1 / 0
        rid = wm.watermark("pipe-1", "k1", "v1")
        assert rid.startswith("pdwm-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        wm = PipelineDataWatermarker()
        wm.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(wm.watermark("pipe-1", f"k{i}", f"v{i}"))
        assert wm.get_watermark_count() == 5
        assert wm.get_watermark(ids[0]) is None
        assert wm.get_watermark(ids[1]) is None
        assert wm.get_watermark(ids[6]) is not None


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        wm = PipelineDataWatermarker()
        wm.watermark("pipe-1", "k1", "v1")
        wm.watermark("pipe-1", "k2", "v2")
        assert wm.get_watermark_count() == 2
        wm.reset()
        assert wm.get_watermark_count() == 0

    def test_reset_fires_event(self):
        wm = PipelineDataWatermarker()
        events = []
        wm.on_change = lambda action, data: events.append(action)
        wm.reset()
        assert "reset" in events
