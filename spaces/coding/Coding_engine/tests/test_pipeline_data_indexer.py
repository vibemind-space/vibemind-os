"""Tests for PipelineDataIndexer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_indexer import PipelineDataIndexer


class TestIndexBasic:
    """Basic indexing and retrieval."""

    def test_index_returns_id(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"name": "alice"}, ["name"])
        assert idx.startswith("pdix-")
        assert len(idx) > 5

    def test_index_empty_pipeline_id(self):
        svc = PipelineDataIndexer()
        assert svc.index("", {"a": 1}, ["a"]) == ""

    def test_index_empty_data(self):
        svc = PipelineDataIndexer()
        assert svc.index("p1", {}, ["a"]) == ""

    def test_index_empty_fields(self):
        svc = PipelineDataIndexer()
        assert svc.index("p1", {"a": 1}, []) == ""

    def test_get_index_existing(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"x": 10, "y": 20}, ["x", "y"], label="test")
        entry = svc.get_index(idx)
        assert entry is not None
        assert entry["pipeline_id"] == "p1"
        assert entry["label"] == "test"
        assert entry["data"] == {"x": 10, "y": 20}

    def test_get_index_nonexistent(self):
        svc = PipelineDataIndexer()
        assert svc.get_index("pdix-nonexistent") is None


class TestLookup:
    """Lookup by indexed field."""

    def test_lookup_match(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"name": "bob", "age": 30}, ["name", "age"])
        result = svc.lookup(idx, "name", "bob")
        assert result is not None
        assert result["name"] == "bob"
        assert result["age"] == 30

    def test_lookup_no_match(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"name": "bob"}, ["name"])
        result = svc.lookup(idx, "name", "alice")
        assert result is None

    def test_lookup_nonexistent_index(self):
        svc = PipelineDataIndexer()
        assert svc.lookup("pdix-nope", "name", "x") is None

    def test_lookup_non_indexed_field(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"name": "bob", "age": 30}, ["name"])
        result = svc.lookup(idx, "age", 30)
        assert result is None

    def test_lookup_returns_deep_copy(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"name": "bob", "items": [1, 2]}, ["name"])
        result = svc.lookup(idx, "name", "bob")
        result["items"].append(3)
        result2 = svc.lookup(idx, "name", "bob")
        assert result2["items"] == [1, 2]


class TestGetIndices:
    """Get indices listing."""

    def test_get_indices_all(self):
        svc = PipelineDataIndexer()
        svc.index("p1", {"a": 1}, ["a"])
        svc.index("p2", {"b": 2}, ["b"])
        results = svc.get_indices()
        assert len(results) == 2

    def test_get_indices_by_pipeline(self):
        svc = PipelineDataIndexer()
        svc.index("p1", {"a": 1}, ["a"])
        svc.index("p2", {"b": 2}, ["b"])
        svc.index("p1", {"c": 3}, ["c"])
        results = svc.get_indices(pipeline_id="p1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "p1" for r in results)

    def test_get_indices_newest_first(self):
        svc = PipelineDataIndexer()
        id1 = svc.index("p1", {"a": 1}, ["a"])
        id2 = svc.index("p1", {"b": 2}, ["b"])
        results = svc.get_indices()
        assert results[0]["index_id"] == id2
        assert results[1]["index_id"] == id1

    def test_get_indices_limit(self):
        svc = PipelineDataIndexer()
        for i in range(10):
            svc.index("p1", {"v": i}, ["v"])
        results = svc.get_indices(limit=3)
        assert len(results) == 3


class TestGetIndexCount:
    """Count indices."""

    def test_count_all(self):
        svc = PipelineDataIndexer()
        svc.index("p1", {"a": 1}, ["a"])
        svc.index("p2", {"b": 2}, ["b"])
        assert svc.get_index_count() == 2

    def test_count_by_pipeline(self):
        svc = PipelineDataIndexer()
        svc.index("p1", {"a": 1}, ["a"])
        svc.index("p2", {"b": 2}, ["b"])
        svc.index("p1", {"c": 3}, ["c"])
        assert svc.get_index_count("p1") == 2
        assert svc.get_index_count("p2") == 1

    def test_count_empty(self):
        svc = PipelineDataIndexer()
        assert svc.get_index_count() == 0


class TestDeepCopy:
    """Deep copy isolation."""

    def test_index_data_deep_copied(self):
        svc = PipelineDataIndexer()
        data = {"nested": {"x": 1}}
        idx = svc.index("p1", data, ["nested"])
        data["nested"]["x"] = 999
        entry = svc.get_index(idx)
        assert entry["data"]["nested"]["x"] == 1

    def test_get_index_returns_copy(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"a": [1, 2]}, ["a"])
        entry = svc.get_index(idx)
        entry["data"]["a"].append(3)
        entry2 = svc.get_index(idx)
        assert entry2["data"]["a"] == [1, 2]


class TestStats:
    """Stats reporting."""

    def test_stats_empty(self):
        svc = PipelineDataIndexer()
        stats = svc.get_stats()
        assert stats["total_indices"] == 0
        assert stats["total_fields_indexed"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        svc = PipelineDataIndexer()
        svc.index("p1", {"a": 1, "b": 2}, ["a", "b"])
        svc.index("p2", {"c": 3}, ["c"])
        stats = svc.get_stats()
        assert stats["total_indices"] == 2
        assert stats["total_fields_indexed"] == 3
        assert stats["unique_pipelines"] == 2


class TestReset:
    """Reset behaviour."""

    def test_reset_clears_entries(self):
        svc = PipelineDataIndexer()
        svc.index("p1", {"a": 1}, ["a"])
        svc.reset()
        assert svc.get_index_count() == 0
        assert svc.get_indices() == []

    def test_reset_clears_callbacks(self):
        svc = PipelineDataIndexer()
        svc.on_change = {"cb1": lambda e, d: None}
        svc.reset()
        assert len(svc.on_change) == 0


class TestCallbacks:
    """Callback and event firing."""

    def test_fire_on_index(self):
        svc = PipelineDataIndexer()
        events = []
        svc.on_change = {"cb": lambda action, data: events.append((action, data))}
        svc.index("p1", {"a": 1}, ["a"])
        assert len(events) == 1
        assert events[0][0] == "indexed"

    def test_remove_callback(self):
        svc = PipelineDataIndexer()
        svc.on_change = {"cb1": lambda a, d: None}
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_fire_silent_on_error(self):
        svc = PipelineDataIndexer()

        def bad_cb(action, data):
            raise RuntimeError("boom")

        svc.on_change = {"bad": bad_cb}
        # Should not raise
        idx = svc.index("p1", {"a": 1}, ["a"])
        assert idx.startswith("pdix-")


class TestPrune:
    """Pruning when exceeding MAX_ENTRIES."""

    def test_prune_keeps_max(self):
        svc = PipelineDataIndexer()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(8):
            ids.append(svc.index("p1", {"v": i}, ["v"]))
        assert svc.get_index_count() <= 5
        # newest should still exist
        assert svc.get_index(ids[-1]) is not None


class TestIndexFieldsPartial:
    """Indexing with fields not all present in data."""

    def test_partial_fields(self):
        svc = PipelineDataIndexer()
        idx = svc.index("p1", {"a": 1}, ["a", "b"])
        entry = svc.get_index(idx)
        assert "a" in entry["indexed_fields"]
        assert "b" not in entry["indexed_fields"]
