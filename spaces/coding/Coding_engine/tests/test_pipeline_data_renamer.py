"""Tests for PipelineDataRenamer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_renamer import PipelineDataRenamer


class TestRenameBasic:
    """Basic rename operations."""

    def test_rename_returns_string_id(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "old_field", "new_field")
        assert isinstance(rid, str)
        assert rid.startswith("pdrn-")

    def test_rename_ids_are_unique(self):
        renamer = PipelineDataRenamer()
        ids = [renamer.rename("pipe-1", f"old_{i}", f"new_{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_rename_stores_pipeline_id(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("my-pipeline", "old", "new")
        record = renamer.get_rename(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_rename_stores_old_name(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "old_field", "new_field")
        record = renamer.get_rename(rid)
        assert record["old_name"] == "old_field"

    def test_rename_stores_new_name(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "old_field", "new_field")
        record = renamer.get_rename(rid)
        assert record["new_name"] == "new_field"

    def test_rename_with_metadata(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "old", "new", metadata={"reason": "typo"})
        record = renamer.get_rename(rid)
        assert record["metadata"]["reason"] == "typo"

    def test_rename_default_metadata_empty(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "old", "new")
        record = renamer.get_rename(rid)
        assert record["metadata"] == {}

    def test_rename_metadata_is_copied(self):
        renamer = PipelineDataRenamer()
        meta = {"key": "value"}
        rid = renamer.rename("pipe-1", "old", "new", metadata=meta)
        meta["key"] = "changed"
        record = renamer.get_rename(rid)
        assert record["metadata"]["key"] == "value"

    def test_rename_has_created_at(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "old", "new")
        record = renamer.get_rename(rid)
        assert "created_at" in record
        assert isinstance(record["created_at"], float)


class TestGetRename:
    """get_rename method."""

    def test_get_rename_existing(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "a", "b")
        result = renamer.get_rename(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_rename_nonexistent(self):
        renamer = PipelineDataRenamer()
        assert renamer.get_rename("pdrn-nonexistent") is None

    def test_get_rename_returns_dict_copy(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "a", "b")
        r1 = renamer.get_rename(rid)
        r2 = renamer.get_rename(rid)
        assert r1 is not r2
        assert r1 == r2


class TestGetRenames:
    """get_renames listing."""

    def test_get_renames_returns_list(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-1", "a", "b")
        result = renamer.get_renames()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_renames_newest_first(self):
        renamer = PipelineDataRenamer()
        id1 = renamer.rename("pipe-1", "a", "b")
        id2 = renamer.rename("pipe-1", "c", "d")
        results = renamer.get_renames()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_renames_filter_by_pipeline_id(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-a", "a", "b")
        renamer.rename("pipe-b", "c", "d")
        renamer.rename("pipe-a", "e", "f")
        results = renamer.get_renames(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_renames_respects_limit(self):
        renamer = PipelineDataRenamer()
        for i in range(10):
            renamer.rename("pipe-1", f"old_{i}", f"new_{i}")
        results = renamer.get_renames(limit=3)
        assert len(results) == 3

    def test_get_renames_empty(self):
        renamer = PipelineDataRenamer()
        assert renamer.get_renames() == []

    def test_get_renames_default_limit_50(self):
        renamer = PipelineDataRenamer()
        for i in range(60):
            renamer.rename("pipe-1", f"old_{i}", f"new_{i}")
        results = renamer.get_renames()
        assert len(results) == 50

    def test_get_renames_returns_dict_copies(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-1", "a", "b")
        renamer.rename("pipe-1", "c", "d")
        results = renamer.get_renames()
        assert all(isinstance(r, dict) for r in results)


class TestGetRenameCount:
    """get_rename_count method."""

    def test_count_all(self):
        renamer = PipelineDataRenamer()
        for i in range(5):
            renamer.rename("pipe-1", f"old_{i}", f"new_{i}")
        assert renamer.get_rename_count() == 5

    def test_count_by_pipeline_id(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-a", "a", "b")
        renamer.rename("pipe-b", "c", "d")
        renamer.rename("pipe-a", "e", "f")
        assert renamer.get_rename_count(pipeline_id="pipe-a") == 2
        assert renamer.get_rename_count(pipeline_id="pipe-b") == 1
        assert renamer.get_rename_count(pipeline_id="pipe-c") == 0

    def test_count_empty(self):
        renamer = PipelineDataRenamer()
        assert renamer.get_rename_count() == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        renamer = PipelineDataRenamer()
        stats = renamer.get_stats()
        assert stats["total_records"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-a", "a", "b")
        renamer.rename("pipe-b", "c", "d")
        renamer.rename("pipe-a", "e", "f")
        stats = renamer.get_stats()
        assert stats["total_records"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_returns_dict(self):
        renamer = PipelineDataRenamer()
        assert isinstance(renamer.get_stats(), dict)


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-1", "a", "b")
        renamer.rename("pipe-1", "c", "d")
        assert renamer.get_rename_count() == 2
        renamer.reset()
        assert renamer.get_rename_count() == 0

    def test_reset_fires_event(self):
        renamer = PipelineDataRenamer()
        events = []
        renamer.on_change = lambda action, data: events.append(action)
        renamer.reset()
        assert "reset" in events

    def test_reset_allows_new_entries(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-1", "a", "b")
        renamer.reset()
        rid = renamer.rename("pipe-1", "c", "d")
        assert renamer.get_rename(rid) is not None
        assert renamer.get_rename_count() == 1


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_rename(self):
        renamer = PipelineDataRenamer()
        events = []
        renamer.on_change = lambda action, data: events.append((action, data))
        renamer.rename("pipe-1", "a", "b")
        assert len(events) == 1
        assert events[0][0] == "rename"

    def test_on_change_property(self):
        renamer = PipelineDataRenamer()
        assert renamer.on_change is None
        cb = lambda a, d: None
        renamer.on_change = cb
        assert renamer.on_change is cb

    def test_on_change_exception_is_silent(self):
        renamer = PipelineDataRenamer()
        renamer.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = renamer.rename("pipe-1", "a", "b")
        assert rid.startswith("pdrn-")

    def test_remove_callback(self):
        renamer = PipelineDataRenamer()
        renamer._callbacks["mycb"] = lambda a, d: None
        assert renamer.remove_callback("mycb") is True
        assert renamer.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        renamer = PipelineDataRenamer()
        fired = []
        renamer._callbacks["tracker"] = lambda a, d: fired.append(a)
        renamer.rename("pipe-1", "a", "b")
        assert "rename" in fired

    def test_named_callback_exception_silent(self):
        renamer = PipelineDataRenamer()
        renamer._callbacks["bad"] = lambda a, d: 1 / 0
        rid = renamer.rename("pipe-1", "a", "b")
        assert rid.startswith("pdrn-")

    def test_remove_callback_nonexistent(self):
        renamer = PipelineDataRenamer()
        assert renamer.remove_callback("does_not_exist") is False


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest_quarter(self):
        renamer = PipelineDataRenamer()
        renamer.MAX_ENTRIES = 8
        ids = []
        for i in range(10):
            ids.append(renamer.rename("pipe-1", f"old_{i}", f"new_{i}"))
        # After adding 9th entry (over 8), prune removes quarter (2).
        # After adding 10th entry (over 8 again), prune removes another quarter.
        # Oldest entries should be gone.
        assert renamer.get_rename(ids[0]) is None
        assert renamer.get_rename(ids[-1]) is not None

    def test_prune_keeps_newest(self):
        renamer = PipelineDataRenamer()
        renamer.MAX_ENTRIES = 4
        ids = []
        for i in range(6):
            ids.append(renamer.rename("pipe-1", f"old_{i}", f"new_{i}"))
        last = renamer.get_rename(ids[-1])
        assert last is not None
        assert last["record_id"] == ids[-1]


class TestReturnDicts:
    """All return values that are records should be dicts."""

    def test_get_rename_returns_dict(self):
        renamer = PipelineDataRenamer()
        rid = renamer.rename("pipe-1", "a", "b")
        result = renamer.get_rename(rid)
        assert isinstance(result, dict)

    def test_get_renames_returns_list_of_dicts(self):
        renamer = PipelineDataRenamer()
        renamer.rename("pipe-1", "a", "b")
        renamer.rename("pipe-1", "c", "d")
        results = renamer.get_renames()
        assert all(isinstance(r, dict) for r in results)
