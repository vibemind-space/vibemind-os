"""Tests for PipelineDataTruncator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_truncator import PipelineDataTruncator


class TestIdGeneration:
    """ID generation and prefix."""

    def test_truncate_returns_string_id(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "name")
        assert isinstance(rid, str)

    def test_id_has_prefix(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "name")
        assert rid.startswith("pdtr-")

    def test_ids_are_unique(self):
        t = PipelineDataTruncator()
        ids = [t.truncate("pipe-1", f"field-{i}") for i in range(20)]
        assert len(set(ids)) == 20

    def test_id_length_consistent(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "name")
        # PREFIX (5) + 12 hex chars = 17
        assert len(rid) == 17


class TestTruncateBasic:
    """Basic truncate operations."""

    def test_truncate_stores_pipeline_id(self):
        t = PipelineDataTruncator()
        rid = t.truncate("my-pipeline", "field_a")
        record = t.get_truncation(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_truncate_stores_field_name(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "description")
        record = t.get_truncation(rid)
        assert record["field_name"] == "description"

    def test_truncate_default_max_length(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "field_a")
        record = t.get_truncation(rid)
        assert record["max_length"] == 100

    def test_truncate_custom_max_length(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "field_a", max_length=500)
        record = t.get_truncation(rid)
        assert record["max_length"] == 500

    def test_truncate_default_metadata_none(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "field_a")
        record = t.get_truncation(rid)
        assert record["metadata"] is None

    def test_truncate_with_metadata(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "field_a", metadata={"reason": "too long"})
        record = t.get_truncation(rid)
        assert record["metadata"]["reason"] == "too long"

    def test_truncate_metadata_is_copied(self):
        t = PipelineDataTruncator()
        meta = {"key": "original"}
        rid = t.truncate("pipe-1", "field_a", metadata=meta)
        meta["key"] = "modified"
        record = t.get_truncation(rid)
        assert record["metadata"]["key"] == "original"

    def test_truncate_stores_created_at(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "field_a")
        record = t.get_truncation(rid)
        assert "created_at" in record
        assert isinstance(record["created_at"], float)


class TestGetTruncation:
    """get_truncation method."""

    def test_found(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "name")
        result = t.get_truncation(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_not_found(self):
        t = PipelineDataTruncator()
        assert t.get_truncation("pdtr-nonexistent") is None

    def test_returns_copy(self):
        t = PipelineDataTruncator()
        rid = t.truncate("pipe-1", "name")
        r1 = t.get_truncation(rid)
        r2 = t.get_truncation(rid)
        assert r1 is not r2
        assert r1 == r2


class TestGetTruncations:
    """get_truncations method."""

    def test_returns_all_when_no_filter(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.truncate("pipe-2", "b")
        results = t.get_truncations()
        assert len(results) == 2

    def test_filter_by_pipeline_id(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.truncate("pipe-2", "b")
        t.truncate("pipe-1", "c")
        results = t.get_truncations(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_ordering_newest_first(self):
        t = PipelineDataTruncator()
        r1 = t.truncate("pipe-1", "a")
        r2 = t.truncate("pipe-1", "b")
        r3 = t.truncate("pipe-1", "c")
        results = t.get_truncations()
        assert results[0]["record_id"] == r3
        assert results[2]["record_id"] == r1

    def test_limit(self):
        t = PipelineDataTruncator()
        for i in range(10):
            t.truncate("pipe-1", f"field-{i}")
        results = t.get_truncations(limit=3)
        assert len(results) == 3

    def test_returns_copies(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        results = t.get_truncations()
        results[0]["pipeline_id"] = "tampered"
        fresh = t.get_truncations()
        assert fresh[0]["pipeline_id"] == "pipe-1"

    def test_empty(self):
        t = PipelineDataTruncator()
        assert t.get_truncations() == []


class TestGetTruncationCount:
    """get_truncation_count method."""

    def test_total_count(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.truncate("pipe-2", "b")
        assert t.get_truncation_count() == 2

    def test_filtered_count(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.truncate("pipe-2", "b")
        t.truncate("pipe-1", "c")
        assert t.get_truncation_count(pipeline_id="pipe-1") == 2

    def test_zero_count(self):
        t = PipelineDataTruncator()
        assert t.get_truncation_count() == 0

    def test_nonexistent_pipeline(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        assert t.get_truncation_count(pipeline_id="pipe-999") == 0


class TestGetStats:
    """get_stats method."""

    def test_stats_structure(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        stats = t.get_stats()
        assert "total_truncations" in stats
        assert "unique_pipelines" in stats

    def test_stats_values(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.truncate("pipe-2", "b")
        t.truncate("pipe-1", "c")
        stats = t.get_stats()
        assert stats["total_truncations"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_empty(self):
        t = PipelineDataTruncator()
        stats = t.get_stats()
        assert stats["total_truncations"] == 0
        assert stats["unique_pipelines"] == 0


class TestOnChangeCallback:
    """on_change callback property."""

    def test_on_change_default_none(self):
        t = PipelineDataTruncator()
        assert t.on_change is None

    def test_on_change_setter_getter(self):
        t = PipelineDataTruncator()
        cb = lambda action, data: None
        t.on_change = cb
        assert t.on_change is cb

    def test_on_change_fires_on_truncate(self):
        t = PipelineDataTruncator()
        fired = []
        t.on_change = lambda action, data: fired.append(action)
        t.truncate("pipe-1", "a")
        assert "truncate" in fired

    def test_on_change_set_to_none(self):
        t = PipelineDataTruncator()
        t.on_change = lambda a, d: None
        t.on_change = None
        assert t.on_change is None

    def test_callback_exception_does_not_propagate(self):
        t = PipelineDataTruncator()
        t.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        # Should not raise
        t.truncate("pipe-1", "a")


class TestRemoveCallback:
    """remove_callback method."""

    def test_remove_existing(self):
        t = PipelineDataTruncator()
        t._state.callbacks["my_cb"] = lambda a, d: None
        assert t.remove_callback("my_cb") is True

    def test_remove_nonexistent(self):
        t = PipelineDataTruncator()
        assert t.remove_callback("no_such") is False

    def test_remove_stops_firing(self):
        t = PipelineDataTruncator()
        fired = []
        t._state.callbacks["tracker"] = lambda a, d: fired.append(a)
        t.truncate("pipe-1", "a")
        assert len(fired) == 1
        t.remove_callback("tracker")
        t.truncate("pipe-1", "b")
        assert len(fired) == 1


class TestPrune:
    """_prune at MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        t = PipelineDataTruncator()
        t.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(t.truncate("pipe-1", f"field-{i}"))
        assert len(t._state.entries) == 5
        # Oldest two should be gone
        assert t.get_truncation(ids[0]) is None
        assert t.get_truncation(ids[1]) is None
        # Newest should remain
        assert t.get_truncation(ids[6]) is not None

    def test_prune_does_not_trigger_below_max(self):
        t = PipelineDataTruncator()
        t.MAX_ENTRIES = 100
        for i in range(50):
            t.truncate("pipe-1", f"field-{i}")
        assert len(t._state.entries) == 50


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.reset()
        assert t.get_truncation_count() == 0

    def test_reset_clears_callbacks(self):
        t = PipelineDataTruncator()
        t.on_change = lambda a, d: None
        t.reset()
        assert t.on_change is None

    def test_reset_resets_seq(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.reset()
        assert t._state._seq == 0

    def test_can_use_after_reset(self):
        t = PipelineDataTruncator()
        t.truncate("pipe-1", "a")
        t.reset()
        rid = t.truncate("pipe-2", "b")
        assert t.get_truncation(rid) is not None
        assert t.get_truncation_count() == 1
