"""Tests for PipelineDataStamper service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_stamper import PipelineDataStamper


class TestStampBasic:
    """Basic stamp operations."""

    def test_stamp_returns_string_id(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a")
        assert isinstance(sid, str)
        assert sid.startswith("pdst-")

    def test_stamp_ids_are_unique(self):
        stamper = PipelineDataStamper()
        ids = [stamper.stamp("pipe-1", f"key-{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_stamp_default_type_is_processed(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a")
        record = stamper.get_stamp(sid)
        assert record["stamp_type"] == "processed"

    def test_stamp_custom_type(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a", stamp_type="validated")
        record = stamper.get_stamp(sid)
        assert record["stamp_type"] == "validated"

    def test_stamp_stores_pipeline_id(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("my-pipeline", "key-a")
        record = stamper.get_stamp(sid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_stamp_stores_data_key(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "data-key-x")
        record = stamper.get_stamp(sid)
        assert record["data_key"] == "data-key-x"

    def test_stamp_with_metadata(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a", metadata={"source": "test"})
        record = stamper.get_stamp(sid)
        assert record["metadata"]["source"] == "test"

    def test_stamp_default_metadata_empty_dict(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a")
        record = stamper.get_stamp(sid)
        assert record["metadata"] == {}

    def test_stamp_metadata_is_copied(self):
        stamper = PipelineDataStamper()
        meta = {"key": "value"}
        sid = stamper.stamp("pipe-1", "key-a", metadata=meta)
        meta["key"] = "changed"
        record = stamper.get_stamp(sid)
        assert record["metadata"]["key"] == "value"


class TestGetStamp:
    """get_stamp method."""

    def test_get_stamp_existing(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a")
        result = stamper.get_stamp(sid)
        assert result is not None
        assert result["stamp_id"] == sid

    def test_get_stamp_nonexistent(self):
        stamper = PipelineDataStamper()
        assert stamper.get_stamp("pdst-nonexistent") is None

    def test_get_stamp_contains_created_at(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a")
        record = stamper.get_stamp(sid)
        assert "created_at" in record
        assert isinstance(record["created_at"], float)

    def test_get_stamp_returns_dict(self):
        stamper = PipelineDataStamper()
        sid = stamper.stamp("pipe-1", "key-a")
        result = stamper.get_stamp(sid)
        assert isinstance(result, dict)


class TestGetStamps:
    """get_stamps listing."""

    def test_get_stamps_returns_list(self):
        stamper = PipelineDataStamper()
        stamper.stamp("pipe-1", "key-a")
        result = stamper.get_stamps()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_stamps_newest_first(self):
        stamper = PipelineDataStamper()
        id1 = stamper.stamp("pipe-1", "key-1")
        id2 = stamper.stamp("pipe-1", "key-2")
        results = stamper.get_stamps()
        assert results[0]["stamp_id"] == id2
        assert results[1]["stamp_id"] == id1

    def test_get_stamps_filter_by_pipeline_id(self):
        stamper = PipelineDataStamper()
        stamper.stamp("pipe-a", "key-1")
        stamper.stamp("pipe-b", "key-2")
        stamper.stamp("pipe-a", "key-3")
        results = stamper.get_stamps(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_stamps_respects_limit(self):
        stamper = PipelineDataStamper()
        for i in range(10):
            stamper.stamp("pipe-1", f"key-{i}")
        results = stamper.get_stamps(limit=3)
        assert len(results) == 3

    def test_get_stamps_empty(self):
        stamper = PipelineDataStamper()
        assert stamper.get_stamps() == []

    def test_get_stamps_returns_list_of_dicts(self):
        stamper = PipelineDataStamper()
        stamper.stamp("pipe-1", "key-1")
        stamper.stamp("pipe-1", "key-2")
        results = stamper.get_stamps()
        assert all(isinstance(r, dict) for r in results)


class TestGetStampCount:
    """get_stamp_count method."""

    def test_count_all(self):
        stamper = PipelineDataStamper()
        for i in range(5):
            stamper.stamp("pipe-1", f"key-{i}")
        assert stamper.get_stamp_count() == 5

    def test_count_by_pipeline_id(self):
        stamper = PipelineDataStamper()
        stamper.stamp("pipe-a", "key-1")
        stamper.stamp("pipe-b", "key-2")
        stamper.stamp("pipe-a", "key-3")
        assert stamper.get_stamp_count(pipeline_id="pipe-a") == 2
        assert stamper.get_stamp_count(pipeline_id="pipe-b") == 1
        assert stamper.get_stamp_count(pipeline_id="pipe-c") == 0

    def test_count_empty(self):
        stamper = PipelineDataStamper()
        assert stamper.get_stamp_count() == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        stamper = PipelineDataStamper()
        stats = stamper.get_stats()
        assert stats["total_stamps"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        stamper = PipelineDataStamper()
        stamper.stamp("pipe-a", "key-1")
        stamper.stamp("pipe-b", "key-2")
        stamper.stamp("pipe-a", "key-3")
        stats = stamper.get_stats()
        assert stats["total_stamps"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_returns_dict(self):
        stamper = PipelineDataStamper()
        stats = stamper.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        stamper = PipelineDataStamper()
        stamper.stamp("pipe-1", "key-a")
        stamper.stamp("pipe-1", "key-b")
        assert stamper.get_stamp_count() == 2
        stamper.reset()
        assert stamper.get_stamp_count() == 0

    def test_reset_fires_event(self):
        stamper = PipelineDataStamper()
        events = []
        stamper.on_change = lambda action, data: events.append(action)
        stamper.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_stamp(self):
        stamper = PipelineDataStamper()
        events = []
        stamper.on_change = lambda action, data: events.append((action, data))
        stamper.stamp("pipe-1", "key-a")
        assert len(events) == 1
        assert events[0][0] == "stamp"

    def test_on_change_property(self):
        stamper = PipelineDataStamper()
        assert stamper.on_change is None
        cb = lambda a, d: None
        stamper.on_change = cb
        assert stamper.on_change is cb

    def test_callback_exception_is_silent(self):
        stamper = PipelineDataStamper()
        stamper.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        sid = stamper.stamp("pipe-1", "key-a")
        assert sid.startswith("pdst-")

    def test_remove_callback(self):
        stamper = PipelineDataStamper()
        stamper._callbacks["mycb"] = lambda a, d: None
        assert stamper.remove_callback("mycb") is True
        assert stamper.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        stamper = PipelineDataStamper()
        fired = []
        stamper._callbacks["tracker"] = lambda a, d: fired.append(a)
        stamper.stamp("pipe-1", "key-a")
        assert "stamp" in fired

    def test_named_callback_exception_silent(self):
        stamper = PipelineDataStamper()
        stamper._callbacks["bad"] = lambda a, d: 1 / 0
        sid = stamper.stamp("pipe-1", "key-a")
        assert sid.startswith("pdst-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        stamper = PipelineDataStamper()
        stamper.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(stamper.stamp("pipe-1", f"key-{i}"))
        assert stamper.get_stamp_count() == 5
        assert stamper.get_stamp(ids[0]) is None
        assert stamper.get_stamp(ids[1]) is None
        assert stamper.get_stamp(ids[6]) is not None
