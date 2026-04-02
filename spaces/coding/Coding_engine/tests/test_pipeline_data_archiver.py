"""Tests for PipelineDataArchiver service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_archiver import PipelineDataArchiver


class TestArchiveBasic:
    """Basic archive operations."""

    def test_archive_returns_string_id(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a")
        assert isinstance(rid, str)
        assert rid.startswith("pdar-")

    def test_archive_ids_are_unique(self):
        archiver = PipelineDataArchiver()
        ids = [archiver.archive("pipe-1", f"key-{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_archive_stores_pipeline_id(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("my-pipeline", "key-a")
        record = archiver.get_archive(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_archive_stores_data_key(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "data-key-x")
        record = archiver.get_archive(rid)
        assert record["data_key"] == "data-key-x"

    def test_archive_default_label_empty(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a")
        record = archiver.get_archive(rid)
        assert record["archive_label"] == ""

    def test_archive_custom_label(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a", archive_label="weekly-backup")
        record = archiver.get_archive(rid)
        assert record["archive_label"] == "weekly-backup"

    def test_archive_with_metadata(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a", metadata={"source": "test"})
        record = archiver.get_archive(rid)
        assert record["metadata"]["source"] == "test"

    def test_archive_default_metadata_empty_dict(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a")
        record = archiver.get_archive(rid)
        assert record["metadata"] == {}

    def test_archive_metadata_is_copied(self):
        archiver = PipelineDataArchiver()
        meta = {"key": "value"}
        rid = archiver.archive("pipe-1", "key-a", metadata=meta)
        meta["key"] = "changed"
        record = archiver.get_archive(rid)
        assert record["metadata"]["key"] == "value"


class TestGetArchive:
    """get_archive method."""

    def test_get_archive_existing(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a")
        result = archiver.get_archive(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_archive_nonexistent(self):
        archiver = PipelineDataArchiver()
        assert archiver.get_archive("pdar-nonexistent") is None

    def test_get_archive_contains_created_at(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a")
        record = archiver.get_archive(rid)
        assert "created_at" in record
        assert isinstance(record["created_at"], float)

    def test_get_archive_returns_dict(self):
        archiver = PipelineDataArchiver()
        rid = archiver.archive("pipe-1", "key-a")
        result = archiver.get_archive(rid)
        assert isinstance(result, dict)


class TestGetArchives:
    """get_archives listing."""

    def test_get_archives_returns_list(self):
        archiver = PipelineDataArchiver()
        archiver.archive("pipe-1", "key-a")
        result = archiver.get_archives()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_archives_newest_first(self):
        archiver = PipelineDataArchiver()
        id1 = archiver.archive("pipe-1", "key-1")
        id2 = archiver.archive("pipe-1", "key-2")
        results = archiver.get_archives()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_archives_filter_by_pipeline_id(self):
        archiver = PipelineDataArchiver()
        archiver.archive("pipe-a", "key-1")
        archiver.archive("pipe-b", "key-2")
        archiver.archive("pipe-a", "key-3")
        results = archiver.get_archives(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_archives_respects_limit(self):
        archiver = PipelineDataArchiver()
        for i in range(10):
            archiver.archive("pipe-1", f"key-{i}")
        results = archiver.get_archives(limit=3)
        assert len(results) == 3

    def test_get_archives_empty(self):
        archiver = PipelineDataArchiver()
        assert archiver.get_archives() == []

    def test_get_archives_returns_list_of_dicts(self):
        archiver = PipelineDataArchiver()
        archiver.archive("pipe-1", "key-1")
        archiver.archive("pipe-1", "key-2")
        results = archiver.get_archives()
        assert all(isinstance(r, dict) for r in results)


class TestGetArchiveCount:
    """get_archive_count method."""

    def test_count_all(self):
        archiver = PipelineDataArchiver()
        for i in range(5):
            archiver.archive("pipe-1", f"key-{i}")
        assert archiver.get_archive_count() == 5

    def test_count_by_pipeline_id(self):
        archiver = PipelineDataArchiver()
        archiver.archive("pipe-a", "key-1")
        archiver.archive("pipe-b", "key-2")
        archiver.archive("pipe-a", "key-3")
        assert archiver.get_archive_count(pipeline_id="pipe-a") == 2
        assert archiver.get_archive_count(pipeline_id="pipe-b") == 1
        assert archiver.get_archive_count(pipeline_id="pipe-c") == 0

    def test_count_empty(self):
        archiver = PipelineDataArchiver()
        assert archiver.get_archive_count() == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        archiver = PipelineDataArchiver()
        stats = archiver.get_stats()
        assert stats["total_archives"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        archiver = PipelineDataArchiver()
        archiver.archive("pipe-a", "key-1")
        archiver.archive("pipe-b", "key-2")
        archiver.archive("pipe-a", "key-3")
        stats = archiver.get_stats()
        assert stats["total_archives"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_returns_dict(self):
        archiver = PipelineDataArchiver()
        stats = archiver.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        archiver = PipelineDataArchiver()
        archiver.archive("pipe-1", "key-a")
        archiver.archive("pipe-1", "key-b")
        assert archiver.get_archive_count() == 2
        archiver.reset()
        assert archiver.get_archive_count() == 0

    def test_reset_clears_callbacks(self):
        archiver = PipelineDataArchiver()
        archiver.on_change = lambda a, d: None
        archiver.reset()
        assert archiver.on_change is None

    def test_reset_resets_sequence(self):
        archiver = PipelineDataArchiver()
        archiver.archive("pipe-1", "key-a")
        archiver.reset()
        assert archiver._state._seq == 0


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_archive(self):
        archiver = PipelineDataArchiver()
        events = []
        archiver.on_change = lambda action, data: events.append((action, data))
        archiver.archive("pipe-1", "key-a")
        assert len(events) == 1
        assert events[0][0] == "archive"

    def test_on_change_property_default_none(self):
        archiver = PipelineDataArchiver()
        assert archiver.on_change is None

    def test_on_change_property_set_and_get(self):
        archiver = PipelineDataArchiver()
        cb = lambda a, d: None
        archiver.on_change = cb
        assert archiver.on_change is cb

    def test_on_change_set_to_none(self):
        archiver = PipelineDataArchiver()
        archiver.on_change = lambda a, d: None
        archiver.on_change = None
        assert archiver.on_change is None

    def test_callback_exception_is_silent(self):
        archiver = PipelineDataArchiver()
        archiver.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = archiver.archive("pipe-1", "key-a")
        assert rid.startswith("pdar-")

    def test_remove_callback(self):
        archiver = PipelineDataArchiver()
        archiver._state.callbacks["mycb"] = lambda a, d: None
        assert archiver.remove_callback("mycb") is True
        assert archiver.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        archiver = PipelineDataArchiver()
        fired = []
        archiver._state.callbacks["tracker"] = lambda a, d: fired.append(a)
        archiver.archive("pipe-1", "key-a")
        assert "archive" in fired

    def test_named_callback_exception_silent(self):
        archiver = PipelineDataArchiver()
        archiver._state.callbacks["bad"] = lambda a, d: 1 / 0
        rid = archiver.archive("pipe-1", "key-a")
        assert rid.startswith("pdar-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        archiver = PipelineDataArchiver()
        archiver.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(archiver.archive("pipe-1", f"key-{i}"))
        assert archiver.get_archive_count() == 5
        assert archiver.get_archive(ids[0]) is None
        assert archiver.get_archive(ids[1]) is None
        assert archiver.get_archive(ids[6]) is not None

    def test_prune_keeps_max_entries(self):
        archiver = PipelineDataArchiver()
        archiver.MAX_ENTRIES = 3
        for i in range(10):
            archiver.archive("pipe-1", f"key-{i}")
        assert archiver.get_archive_count() <= 3
