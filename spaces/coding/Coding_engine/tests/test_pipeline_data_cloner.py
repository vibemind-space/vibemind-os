"""Tests for PipelineDataCloner service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_cloner import PipelineDataCloner


class TestPipelineDataClonerBasic:
    """Basic clone operations."""

    def test_clone_returns_string_id(self):
        cloner = PipelineDataCloner()
        clone_id = cloner.clone({"key": "value"})
        assert isinstance(clone_id, str)
        assert clone_id.startswith("pdcl-")

    def test_clone_ids_are_unique(self):
        cloner = PipelineDataCloner()
        ids = [cloner.clone({"i": i}) for i in range(10)]
        assert len(set(ids)) == 10

    def test_clone_deep_copies_data(self):
        cloner = PipelineDataCloner()
        original = {"nested": {"a": 1}}
        clone_id = cloner.clone(original)
        original["nested"]["a"] = 999
        retrieved = cloner.retrieve_data(clone_id)
        assert retrieved["nested"]["a"] == 1

    def test_clone_with_label(self):
        cloner = PipelineDataCloner()
        clone_id = cloner.clone({"x": 1}, label="test-label")
        record = cloner.get_clone(clone_id)
        assert record["label"] == "test-label"

    def test_clone_with_metadata(self):
        cloner = PipelineDataCloner()
        meta = {"author": "tester"}
        clone_id = cloner.clone({"x": 1}, metadata=meta)
        record = cloner.get_clone(clone_id)
        assert record["metadata"]["author"] == "tester"

    def test_clone_metadata_is_deep_copied(self):
        cloner = PipelineDataCloner()
        meta = {"info": [1, 2, 3]}
        clone_id = cloner.clone({"x": 1}, metadata=meta)
        meta["info"].append(4)
        record = cloner.get_clone(clone_id)
        assert record["metadata"]["info"] == [1, 2, 3]


class TestGetClone:
    """get_clone method."""

    def test_get_clone_existing(self):
        cloner = PipelineDataCloner()
        clone_id = cloner.clone({"a": 1})
        result = cloner.get_clone(clone_id)
        assert result is not None
        assert result["clone_id"] == clone_id

    def test_get_clone_nonexistent(self):
        cloner = PipelineDataCloner()
        assert cloner.get_clone("pdcl-nonexistent") is None

    def test_get_clone_contains_data(self):
        cloner = PipelineDataCloner()
        clone_id = cloner.clone({"field": "value"})
        record = cloner.get_clone(clone_id)
        assert record["data"]["field"] == "value"


class TestGetClones:
    """get_clones listing."""

    def test_get_clones_returns_list(self):
        cloner = PipelineDataCloner()
        cloner.clone({"a": 1})
        result = cloner.get_clones()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_clones_newest_first(self):
        cloner = PipelineDataCloner()
        id1 = cloner.clone({"order": 1})
        id2 = cloner.clone({"order": 2})
        results = cloner.get_clones()
        assert results[0]["clone_id"] == id2
        assert results[1]["clone_id"] == id1

    def test_get_clones_filter_by_label(self):
        cloner = PipelineDataCloner()
        cloner.clone({"x": 1}, label="alpha")
        cloner.clone({"x": 2}, label="beta")
        cloner.clone({"x": 3}, label="alpha")
        results = cloner.get_clones(label="alpha")
        assert len(results) == 2
        assert all(r["label"] == "alpha" for r in results)

    def test_get_clones_respects_limit(self):
        cloner = PipelineDataCloner()
        for i in range(10):
            cloner.clone({"i": i})
        results = cloner.get_clones(limit=3)
        assert len(results) == 3

    def test_get_clones_empty(self):
        cloner = PipelineDataCloner()
        assert cloner.get_clones() == []


class TestRetrieveData:
    """retrieve_data method."""

    def test_retrieve_data_returns_deep_copy(self):
        cloner = PipelineDataCloner()
        clone_id = cloner.clone({"nested": {"val": 42}})
        data1 = cloner.retrieve_data(clone_id)
        data2 = cloner.retrieve_data(clone_id)
        assert data1 == data2
        data1["nested"]["val"] = 0
        data2_again = cloner.retrieve_data(clone_id)
        assert data2_again["nested"]["val"] == 42

    def test_retrieve_data_nonexistent(self):
        cloner = PipelineDataCloner()
        assert cloner.retrieve_data("pdcl-missing") is None


class TestCloneCount:
    """get_clone_count method."""

    def test_count_all(self):
        cloner = PipelineDataCloner()
        for i in range(5):
            cloner.clone({"i": i})
        assert cloner.get_clone_count() == 5

    def test_count_by_label(self):
        cloner = PipelineDataCloner()
        cloner.clone({"x": 1}, label="a")
        cloner.clone({"x": 2}, label="b")
        cloner.clone({"x": 3}, label="a")
        assert cloner.get_clone_count(label="a") == 2
        assert cloner.get_clone_count(label="b") == 1
        assert cloner.get_clone_count(label="c") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        cloner = PipelineDataCloner()
        stats = cloner.get_stats()
        assert stats["total_clones"] == 0
        assert stats["unique_labels"] == 0

    def test_stats_populated(self):
        cloner = PipelineDataCloner()
        cloner.clone({"a": 1}, label="x")
        cloner.clone({"b": 2}, label="y")
        cloner.clone({"c": 3}, label="x")
        stats = cloner.get_stats()
        assert stats["total_clones"] == 3
        assert stats["unique_labels"] == 2


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        cloner = PipelineDataCloner()
        cloner.clone({"a": 1})
        cloner.clone({"b": 2})
        assert cloner.get_clone_count() == 2
        cloner.reset()
        assert cloner.get_clone_count() == 0

    def test_reset_fires_event(self):
        cloner = PipelineDataCloner()
        events = []
        cloner.on_change = lambda action, data: events.append(action)
        cloner.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_clone(self):
        cloner = PipelineDataCloner()
        events = []
        cloner.on_change = lambda action, data: events.append((action, data))
        cloner.clone({"x": 1})
        assert len(events) == 1
        assert events[0][0] == "clone"

    def test_on_change_property(self):
        cloner = PipelineDataCloner()
        assert cloner.on_change is None
        cb = lambda a, d: None
        cloner.on_change = cb
        assert cloner.on_change is cb

    def test_callback_exception_is_silent(self):
        cloner = PipelineDataCloner()
        cloner.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        # Should not raise
        clone_id = cloner.clone({"x": 1})
        assert clone_id.startswith("pdcl-")

    def test_remove_callback(self):
        cloner = PipelineDataCloner()
        cloner._callbacks["mycb"] = lambda a, d: None
        assert cloner.remove_callback("mycb") is True
        assert cloner.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        cloner = PipelineDataCloner()
        fired = []
        cloner._callbacks["tracker"] = lambda a, d: fired.append(a)
        cloner.clone({"v": 1})
        assert "clone" in fired

    def test_named_callback_exception_silent(self):
        cloner = PipelineDataCloner()
        cloner._callbacks["bad"] = lambda a, d: 1 / 0
        clone_id = cloner.clone({"v": 1})
        assert clone_id.startswith("pdcl-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        cloner = PipelineDataCloner()
        cloner.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(cloner.clone({"i": i}))
        assert cloner.get_clone_count() == 5
        # First two should have been evicted
        assert cloner.get_clone(ids[0]) is None
        assert cloner.get_clone(ids[1]) is None
        assert cloner.get_clone(ids[6]) is not None
