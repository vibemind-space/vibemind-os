"""Tests for PipelineDataAnnotator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_annotator import PipelineDataAnnotator


class TestAnnotateBasic:
    """Basic annotate operations."""

    def test_annotate_returns_string_id(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"key": "value"}, {"tag": "v1"})
        assert isinstance(aid, str)
        assert aid.startswith("pdan-")

    def test_annotate_ids_are_unique(self):
        ann = PipelineDataAnnotator()
        ids = [ann.annotate({"i": i}, {"t": str(i)}) for i in range(10)]
        assert len(set(ids)) == 10

    def test_annotate_deep_copies_data(self):
        ann = PipelineDataAnnotator()
        original = {"nested": {"a": 1}}
        aid = ann.annotate(original, {"tag": "x"})
        original["nested"]["a"] = 999
        record = ann.get_annotation(aid)
        assert record["data"]["nested"]["a"] == 1

    def test_annotate_deep_copies_annotations(self):
        ann = PipelineDataAnnotator()
        annotations = {"tag": "v1", "extra": "yes"}
        aid = ann.annotate({"x": 1}, annotations)
        annotations["tag"] = "modified"
        record = ann.get_annotation(aid)
        assert record["annotations"]["tag"] == "v1"

    def test_annotate_with_label(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"x": 1}, {"tag": "v1"}, label="test-label")
        record = ann.get_annotation(aid)
        assert record["label"] == "test-label"

    def test_annotate_default_label_empty(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"x": 1}, {"tag": "v1"})
        record = ann.get_annotation(aid)
        assert record["label"] == ""


class TestGetAnnotation:
    """get_annotation method."""

    def test_get_annotation_existing(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"a": 1}, {"tag": "v1"})
        result = ann.get_annotation(aid)
        assert result is not None
        assert result["annotation_id"] == aid

    def test_get_annotation_nonexistent(self):
        ann = PipelineDataAnnotator()
        assert ann.get_annotation("pdan-nonexistent") is None

    def test_get_annotation_contains_data(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"field": "value"}, {"tag": "v1"})
        record = ann.get_annotation(aid)
        assert record["data"]["field"] == "value"

    def test_get_annotation_contains_annotations(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"x": 1}, {"color": "red", "size": "large"})
        record = ann.get_annotation(aid)
        assert record["annotations"]["color"] == "red"
        assert record["annotations"]["size"] == "large"


class TestGetAnnotations:
    """get_annotations listing."""

    def test_get_annotations_returns_list(self):
        ann = PipelineDataAnnotator()
        ann.annotate({"a": 1}, {"t": "v"})
        result = ann.get_annotations()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_annotations_newest_first(self):
        ann = PipelineDataAnnotator()
        id1 = ann.annotate({"order": 1}, {"t": "v"})
        id2 = ann.annotate({"order": 2}, {"t": "v"})
        results = ann.get_annotations()
        assert results[0]["annotation_id"] == id2
        assert results[1]["annotation_id"] == id1

    def test_get_annotations_filter_by_label(self):
        ann = PipelineDataAnnotator()
        ann.annotate({"x": 1}, {"t": "v"}, label="alpha")
        ann.annotate({"x": 2}, {"t": "v"}, label="beta")
        ann.annotate({"x": 3}, {"t": "v"}, label="alpha")
        results = ann.get_annotations(label="alpha")
        assert len(results) == 2
        assert all(r["label"] == "alpha" for r in results)

    def test_get_annotations_respects_limit(self):
        ann = PipelineDataAnnotator()
        for i in range(10):
            ann.annotate({"i": i}, {"t": str(i)})
        results = ann.get_annotations(limit=3)
        assert len(results) == 3

    def test_get_annotations_empty(self):
        ann = PipelineDataAnnotator()
        assert ann.get_annotations() == []


class TestAddAnnotation:
    """add_annotation method."""

    def test_add_annotation_success(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"x": 1}, {"tag": "v1"})
        result = ann.add_annotation(aid, "priority", "high")
        assert result is True
        record = ann.get_annotation(aid)
        assert record["annotations"]["priority"] == "high"

    def test_add_annotation_nonexistent(self):
        ann = PipelineDataAnnotator()
        result = ann.add_annotation("pdan-missing", "key", "value")
        assert result is False

    def test_add_annotation_overwrites_existing_key(self):
        ann = PipelineDataAnnotator()
        aid = ann.annotate({"x": 1}, {"tag": "v1"})
        ann.add_annotation(aid, "tag", "v2")
        record = ann.get_annotation(aid)
        assert record["annotations"]["tag"] == "v2"

    def test_add_annotation_fires_event(self):
        ann = PipelineDataAnnotator()
        events = []
        ann.on_change = lambda action, data: events.append(action)
        aid = ann.annotate({"x": 1}, {"tag": "v1"})
        ann.add_annotation(aid, "new_key", "new_val")
        assert "add_annotation" in events


class TestAnnotationCount:
    """get_annotation_count method."""

    def test_count_all(self):
        ann = PipelineDataAnnotator()
        for i in range(5):
            ann.annotate({"i": i}, {"t": str(i)})
        assert ann.get_annotation_count() == 5

    def test_count_by_label(self):
        ann = PipelineDataAnnotator()
        ann.annotate({"x": 1}, {"t": "v"}, label="a")
        ann.annotate({"x": 2}, {"t": "v"}, label="b")
        ann.annotate({"x": 3}, {"t": "v"}, label="a")
        assert ann.get_annotation_count(label="a") == 2
        assert ann.get_annotation_count(label="b") == 1
        assert ann.get_annotation_count(label="c") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        ann = PipelineDataAnnotator()
        stats = ann.get_stats()
        assert stats["total_annotations"] == 0
        assert stats["unique_labels"] == 0
        assert stats["total_annotation_keys"] == 0

    def test_stats_populated(self):
        ann = PipelineDataAnnotator()
        ann.annotate({"a": 1}, {"color": "red", "size": "big"}, label="x")
        ann.annotate({"b": 2}, {"color": "blue"}, label="y")
        ann.annotate({"c": 3}, {"weight": "heavy"}, label="x")
        stats = ann.get_stats()
        assert stats["total_annotations"] == 3
        assert stats["unique_labels"] == 2
        assert stats["total_annotation_keys"] == 4


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        ann = PipelineDataAnnotator()
        ann.annotate({"a": 1}, {"t": "v"})
        ann.annotate({"b": 2}, {"t": "v"})
        assert ann.get_annotation_count() == 2
        ann.reset()
        assert ann.get_annotation_count() == 0

    def test_reset_fires_event(self):
        ann = PipelineDataAnnotator()
        events = []
        ann.on_change = lambda action, data: events.append(action)
        ann.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_annotate(self):
        ann = PipelineDataAnnotator()
        events = []
        ann.on_change = lambda action, data: events.append((action, data))
        ann.annotate({"x": 1}, {"t": "v"})
        assert len(events) == 1
        assert events[0][0] == "annotate"

    def test_on_change_property(self):
        ann = PipelineDataAnnotator()
        assert ann.on_change is None
        cb = lambda a, d: None
        ann.on_change = cb
        assert ann.on_change is cb

    def test_callback_exception_is_silent(self):
        ann = PipelineDataAnnotator()
        ann.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        aid = ann.annotate({"x": 1}, {"t": "v"})
        assert aid.startswith("pdan-")

    def test_remove_callback(self):
        ann = PipelineDataAnnotator()
        ann._callbacks["mycb"] = lambda a, d: None
        assert ann.remove_callback("mycb") is True
        assert ann.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        ann = PipelineDataAnnotator()
        fired = []
        ann._callbacks["tracker"] = lambda a, d: fired.append(a)
        ann.annotate({"v": 1}, {"t": "v"})
        assert "annotate" in fired

    def test_named_callback_exception_silent(self):
        ann = PipelineDataAnnotator()
        ann._callbacks["bad"] = lambda a, d: 1 / 0
        aid = ann.annotate({"v": 1}, {"t": "v"})
        assert aid.startswith("pdan-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        ann = PipelineDataAnnotator()
        ann.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(ann.annotate({"i": i}, {"t": str(i)}))
        assert ann.get_annotation_count() == 5
        assert ann.get_annotation(ids[0]) is None
        assert ann.get_annotation(ids[1]) is None
        assert ann.get_annotation(ids[6]) is not None
