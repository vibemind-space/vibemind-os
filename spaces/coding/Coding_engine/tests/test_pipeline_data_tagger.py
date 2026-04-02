"""Tests for PipelineDataTagger service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_tagger import PipelineDataTagger


class TestTagBasic:
    """Basic tag operations."""

    def test_tag_returns_string_id(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"key": "value"}, ["alpha"])
        assert isinstance(rid, str)
        assert rid.startswith("pdtg-")

    def test_tag_ids_are_unique(self):
        tagger = PipelineDataTagger()
        ids = [tagger.tag("pipe-1", {"i": i}, [str(i)]) for i in range(10)]
        assert len(set(ids)) == 10

    def test_tag_deep_copies_data(self):
        tagger = PipelineDataTagger()
        original = {"nested": {"a": 1}}
        rid = tagger.tag("pipe-1", original, ["t1"])
        original["nested"]["a"] = 999
        record = tagger.get_tag_record(rid)
        assert record["data"]["nested"]["a"] == 1

    def test_tag_deep_copies_tags(self):
        tagger = PipelineDataTagger()
        tags = ["alpha", "beta"]
        rid = tagger.tag("pipe-1", {"x": 1}, tags)
        tags.append("gamma")
        record = tagger.get_tag_record(rid)
        assert "gamma" not in record["tags"]

    def test_tag_with_label(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"], label="test-label")
        record = tagger.get_tag_record(rid)
        assert record["label"] == "test-label"

    def test_tag_default_label_empty(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        record = tagger.get_tag_record(rid)
        assert record["label"] == ""

    def test_tag_stores_pipeline_id(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("my-pipeline", {"x": 1}, ["t1"])
        record = tagger.get_tag_record(rid)
        assert record["pipeline_id"] == "my-pipeline"


class TestGetTagRecord:
    """get_tag_record method."""

    def test_get_tag_record_existing(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"a": 1}, ["t1"])
        result = tagger.get_tag_record(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_tag_record_nonexistent(self):
        tagger = PipelineDataTagger()
        assert tagger.get_tag_record("pdtg-nonexistent") is None

    def test_get_tag_record_contains_data(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"field": "value"}, ["t1"])
        record = tagger.get_tag_record(rid)
        assert record["data"]["field"] == "value"

    def test_get_tag_record_contains_tags(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["alpha", "beta"])
        record = tagger.get_tag_record(rid)
        assert "alpha" in record["tags"]
        assert "beta" in record["tags"]


class TestAddTag:
    """add_tag method."""

    def test_add_tag_success(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        result = tagger.add_tag(rid, "t2")
        assert result is True
        record = tagger.get_tag_record(rid)
        assert "t2" in record["tags"]

    def test_add_tag_nonexistent_record(self):
        tagger = PipelineDataTagger()
        result = tagger.add_tag("pdtg-missing", "t1")
        assert result is False

    def test_add_tag_duplicate_no_duplicate_in_list(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        tagger.add_tag(rid, "t1")
        record = tagger.get_tag_record(rid)
        assert record["tags"].count("t1") == 1

    def test_add_tag_fires_event(self):
        tagger = PipelineDataTagger()
        events = []
        tagger.on_change = lambda action, data: events.append(action)
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        tagger.add_tag(rid, "t2")
        assert "add_tag" in events


class TestRemoveTag:
    """remove_tag method."""

    def test_remove_tag_success(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1", "t2"])
        result = tagger.remove_tag(rid, "t1")
        assert result is True
        record = tagger.get_tag_record(rid)
        assert "t1" not in record["tags"]
        assert "t2" in record["tags"]

    def test_remove_tag_nonexistent_record(self):
        tagger = PipelineDataTagger()
        result = tagger.remove_tag("pdtg-missing", "t1")
        assert result is False

    def test_remove_tag_not_present(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        result = tagger.remove_tag(rid, "nonexistent")
        assert result is False

    def test_remove_tag_fires_event(self):
        tagger = PipelineDataTagger()
        events = []
        tagger.on_change = lambda action, data: events.append(action)
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        tagger.remove_tag(rid, "t1")
        assert "remove_tag" in events


class TestGetTagRecords:
    """get_tag_records listing."""

    def test_get_tag_records_returns_list(self):
        tagger = PipelineDataTagger()
        tagger.tag("pipe-1", {"a": 1}, ["t1"])
        result = tagger.get_tag_records()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_tag_records_newest_first(self):
        tagger = PipelineDataTagger()
        id1 = tagger.tag("pipe-1", {"order": 1}, ["t1"])
        id2 = tagger.tag("pipe-1", {"order": 2}, ["t1"])
        results = tagger.get_tag_records()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_tag_records_filter_by_pipeline_id(self):
        tagger = PipelineDataTagger()
        tagger.tag("pipe-a", {"x": 1}, ["t1"])
        tagger.tag("pipe-b", {"x": 2}, ["t1"])
        tagger.tag("pipe-a", {"x": 3}, ["t1"])
        results = tagger.get_tag_records(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_tag_records_filter_by_tag(self):
        tagger = PipelineDataTagger()
        tagger.tag("pipe-1", {"x": 1}, ["alpha", "beta"])
        tagger.tag("pipe-1", {"x": 2}, ["gamma"])
        tagger.tag("pipe-1", {"x": 3}, ["alpha"])
        results = tagger.get_tag_records(tag="alpha")
        assert len(results) == 2

    def test_get_tag_records_respects_limit(self):
        tagger = PipelineDataTagger()
        for i in range(10):
            tagger.tag("pipe-1", {"i": i}, ["t1"])
        results = tagger.get_tag_records(limit=3)
        assert len(results) == 3

    def test_get_tag_records_empty(self):
        tagger = PipelineDataTagger()
        assert tagger.get_tag_records() == []


class TestGetTagCount:
    """get_tag_count method."""

    def test_count_all(self):
        tagger = PipelineDataTagger()
        for i in range(5):
            tagger.tag("pipe-1", {"i": i}, ["t1"])
        assert tagger.get_tag_count() == 5

    def test_count_by_pipeline_id(self):
        tagger = PipelineDataTagger()
        tagger.tag("pipe-a", {"x": 1}, ["t1"])
        tagger.tag("pipe-b", {"x": 2}, ["t1"])
        tagger.tag("pipe-a", {"x": 3}, ["t1"])
        assert tagger.get_tag_count(pipeline_id="pipe-a") == 2
        assert tagger.get_tag_count(pipeline_id="pipe-b") == 1
        assert tagger.get_tag_count(pipeline_id="pipe-c") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        tagger = PipelineDataTagger()
        stats = tagger.get_stats()
        assert stats["total_records"] == 0
        assert stats["unique_tags"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        tagger = PipelineDataTagger()
        tagger.tag("pipe-a", {"a": 1}, ["alpha", "beta"])
        tagger.tag("pipe-b", {"b": 2}, ["alpha", "gamma"])
        tagger.tag("pipe-a", {"c": 3}, ["delta"])
        stats = tagger.get_stats()
        assert stats["total_records"] == 3
        assert stats["unique_tags"] == 4
        assert stats["unique_pipelines"] == 2


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        tagger = PipelineDataTagger()
        tagger.tag("pipe-1", {"a": 1}, ["t1"])
        tagger.tag("pipe-1", {"b": 2}, ["t2"])
        assert tagger.get_tag_count() == 2
        tagger.reset()
        assert tagger.get_tag_count() == 0

    def test_reset_fires_event(self):
        tagger = PipelineDataTagger()
        events = []
        tagger.on_change = lambda action, data: events.append(action)
        tagger.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_tag(self):
        tagger = PipelineDataTagger()
        events = []
        tagger.on_change = lambda action, data: events.append((action, data))
        tagger.tag("pipe-1", {"x": 1}, ["t1"])
        assert len(events) == 1
        assert events[0][0] == "tag"

    def test_on_change_property(self):
        tagger = PipelineDataTagger()
        assert tagger.on_change is None
        cb = lambda a, d: None
        tagger.on_change = cb
        assert tagger.on_change is cb

    def test_callback_exception_is_silent(self):
        tagger = PipelineDataTagger()
        tagger.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        assert rid.startswith("pdtg-")

    def test_remove_callback(self):
        tagger = PipelineDataTagger()
        tagger._callbacks["mycb"] = lambda a, d: None
        assert tagger.remove_callback("mycb") is True
        assert tagger.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        tagger = PipelineDataTagger()
        fired = []
        tagger._callbacks["tracker"] = lambda a, d: fired.append(a)
        tagger.tag("pipe-1", {"v": 1}, ["t1"])
        assert "tag" in fired

    def test_named_callback_exception_silent(self):
        tagger = PipelineDataTagger()
        tagger._callbacks["bad"] = lambda a, d: 1 / 0
        rid = tagger.tag("pipe-1", {"v": 1}, ["t1"])
        assert rid.startswith("pdtg-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        tagger = PipelineDataTagger()
        tagger.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(tagger.tag("pipe-1", {"i": i}, ["t1"]))
        assert tagger.get_tag_count() == 5
        assert tagger.get_tag_record(ids[0]) is None
        assert tagger.get_tag_record(ids[1]) is None
        assert tagger.get_tag_record(ids[6]) is not None


class TestReturnDicts:
    """All return values that are records should be dicts."""

    def test_get_tag_record_returns_dict(self):
        tagger = PipelineDataTagger()
        rid = tagger.tag("pipe-1", {"x": 1}, ["t1"])
        result = tagger.get_tag_record(rid)
        assert isinstance(result, dict)

    def test_get_tag_records_returns_list_of_dicts(self):
        tagger = PipelineDataTagger()
        tagger.tag("pipe-1", {"x": 1}, ["t1"])
        tagger.tag("pipe-1", {"x": 2}, ["t2"])
        results = tagger.get_tag_records()
        assert all(isinstance(r, dict) for r in results)

    def test_get_stats_returns_dict(self):
        tagger = PipelineDataTagger()
        stats = tagger.get_stats()
        assert isinstance(stats, dict)
