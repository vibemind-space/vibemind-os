"""Tests for PipelineStepAnnotator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_annotator import PipelineStepAnnotator


class TestAnnotateBasic:
    """Basic annotate operations."""

    def test_annotate_returns_string_id(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "step-a", "initial note")
        assert isinstance(aid, str)
        assert aid.startswith("psan-")

    def test_annotate_ids_are_unique(self):
        svc = PipelineStepAnnotator()
        ids = [svc.annotate("pipe-1", f"step-{i}", f"note {i}") for i in range(20)]
        assert len(set(ids)) == 20

    def test_annotate_stores_pipeline_id(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-42", "step-x", "hello")
        record = svc.get_annotation(aid)
        assert record["pipeline_id"] == "pipe-42"

    def test_annotate_stores_step_name(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "transform", "note")
        record = svc.get_annotation(aid)
        assert record["step_name"] == "transform"

    def test_annotate_stores_note(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "step-a", "my note text")
        record = svc.get_annotation(aid)
        assert record["note"] == "my note text"

    def test_annotate_with_tags(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "step-a", "note", tags=["critical", "review"])
        record = svc.get_annotation(aid)
        assert record["tags"] == ["critical", "review"]

    def test_annotate_default_tags_empty(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "step-a", "note")
        record = svc.get_annotation(aid)
        assert record["tags"] == []

    def test_annotate_tags_are_copied(self):
        svc = PipelineStepAnnotator()
        tags = ["a", "b"]
        aid = svc.annotate("pipe-1", "step-a", "note", tags=tags)
        tags.append("c")
        record = svc.get_annotation(aid)
        assert record["tags"] == ["a", "b"]


class TestGetAnnotation:
    """get_annotation method."""

    def test_get_annotation_existing(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "step-a", "note")
        result = svc.get_annotation(aid)
        assert result is not None
        assert result["annotation_id"] == aid

    def test_get_annotation_nonexistent(self):
        svc = PipelineStepAnnotator()
        assert svc.get_annotation("psan-nonexistent") is None

    def test_get_annotation_returns_copy(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "step-a", "note")
        r1 = svc.get_annotation(aid)
        r2 = svc.get_annotation(aid)
        assert r1 is not r2
        assert r1 == r2

    def test_get_annotation_has_created_at(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("pipe-1", "step-a", "note")
        record = svc.get_annotation(aid)
        assert "created_at" in record
        assert isinstance(record["created_at"], float)


class TestGetAnnotations:
    """get_annotations listing."""

    def test_get_annotations_returns_list(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note")
        result = svc.get_annotations()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_annotations_newest_first(self):
        svc = PipelineStepAnnotator()
        id1 = svc.annotate("pipe-1", "step-a", "first")
        id2 = svc.annotate("pipe-1", "step-b", "second")
        results = svc.get_annotations()
        assert results[0]["annotation_id"] == id2
        assert results[1]["annotation_id"] == id1

    def test_get_annotations_filter_by_pipeline_id(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note")
        svc.annotate("pipe-2", "step-b", "note")
        svc.annotate("pipe-1", "step-c", "note")
        results = svc.get_annotations(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_get_annotations_filter_by_step_name(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note")
        svc.annotate("pipe-1", "step-b", "note")
        svc.annotate("pipe-2", "step-a", "note")
        results = svc.get_annotations(step_name="step-a")
        assert len(results) == 2
        assert all(r["step_name"] == "step-a" for r in results)

    def test_get_annotations_filter_by_both(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note")
        svc.annotate("pipe-1", "step-b", "note")
        svc.annotate("pipe-2", "step-a", "note")
        results = svc.get_annotations(pipeline_id="pipe-1", step_name="step-a")
        assert len(results) == 1

    def test_get_annotations_respects_limit(self):
        svc = PipelineStepAnnotator()
        for i in range(10):
            svc.annotate("pipe-1", f"step-{i}", f"note {i}")
        results = svc.get_annotations(limit=3)
        assert len(results) == 3

    def test_get_annotations_empty(self):
        svc = PipelineStepAnnotator()
        assert svc.get_annotations() == []


class TestAnnotationCount:
    """get_annotation_count method."""

    def test_count_all(self):
        svc = PipelineStepAnnotator()
        for i in range(5):
            svc.annotate("pipe-1", f"step-{i}", f"note {i}")
        assert svc.get_annotation_count() == 5

    def test_count_by_pipeline_id(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note")
        svc.annotate("pipe-2", "step-b", "note")
        svc.annotate("pipe-1", "step-c", "note")
        assert svc.get_annotation_count(pipeline_id="pipe-1") == 2
        assert svc.get_annotation_count(pipeline_id="pipe-2") == 1
        assert svc.get_annotation_count(pipeline_id="pipe-3") == 0

    def test_count_zero_when_empty(self):
        svc = PipelineStepAnnotator()
        assert svc.get_annotation_count() == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        svc = PipelineStepAnnotator()
        stats = svc.get_stats()
        assert stats["total_annotations"] == 0
        assert stats["unique_pipelines"] == 0
        assert stats["unique_steps"] == 0
        assert stats["total_tags"] == 0

    def test_stats_populated(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note", tags=["critical", "review"])
        svc.annotate("pipe-2", "step-b", "note", tags=["info"])
        svc.annotate("pipe-1", "step-c", "note")
        stats = svc.get_stats()
        assert stats["total_annotations"] == 3
        assert stats["unique_pipelines"] == 2
        assert stats["unique_steps"] == 3
        assert stats["total_tags"] == 3


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note")
        svc.annotate("pipe-2", "step-b", "note")
        assert svc.get_annotation_count() == 2
        svc.reset()
        assert svc.get_annotation_count() == 0

    def test_reset_clears_callbacks(self):
        svc = PipelineStepAnnotator()
        svc._callbacks["mycb"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None

    def test_reset_resets_seq(self):
        svc = PipelineStepAnnotator()
        svc.annotate("pipe-1", "step-a", "note")
        assert svc._state._seq > 0
        svc.reset()
        assert svc._state._seq == 0


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_annotate(self):
        svc = PipelineStepAnnotator()
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.annotate("pipe-1", "step-a", "note")
        assert len(events) == 1
        assert events[0][0] == "annotate"

    def test_on_change_property_getter_setter(self):
        svc = PipelineStepAnnotator()
        assert svc.on_change is None
        cb = lambda a, d: None
        svc.on_change = cb
        assert svc.on_change is cb

    def test_on_change_exception_is_silent(self):
        svc = PipelineStepAnnotator()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        aid = svc.annotate("pipe-1", "step-a", "note")
        assert aid.startswith("psan-")

    def test_remove_callback_existing(self):
        svc = PipelineStepAnnotator()
        svc._callbacks["mycb"] = lambda a, d: None
        assert svc.remove_callback("mycb") is True
        assert "mycb" not in svc._callbacks

    def test_remove_callback_nonexistent(self):
        svc = PipelineStepAnnotator()
        assert svc.remove_callback("nope") is False

    def test_named_callback_fires(self):
        svc = PipelineStepAnnotator()
        fired = []
        svc._callbacks["tracker"] = lambda a, d: fired.append(a)
        svc.annotate("pipe-1", "step-a", "note")
        assert "annotate" in fired

    def test_named_callback_exception_silent(self):
        svc = PipelineStepAnnotator()
        svc._callbacks["bad"] = lambda a, d: 1 / 0
        aid = svc.annotate("pipe-1", "step-a", "note")
        assert aid.startswith("psan-")

    def test_on_change_called_before_named_callbacks(self):
        svc = PipelineStepAnnotator()
        order = []
        svc.on_change = lambda a, d: order.append("on_change")
        svc._callbacks["named"] = lambda a, d: order.append("named")
        svc.annotate("pipe-1", "step-a", "note")
        assert order == ["on_change", "named"]


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        svc = PipelineStepAnnotator()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(10):
            ids.append(svc.annotate("pipe-1", f"step-{i}", f"note {i}"))
        # After pruning, should have removed a quarter of entries
        # 10 > 8, so prune removes 10//4 = 2 oldest
        assert svc.get_annotation_count() == 8
        assert svc.get_annotation(ids[0]) is None
        assert svc.get_annotation(ids[1]) is None
        assert svc.get_annotation(ids[9]) is not None

    def test_prune_keeps_newest(self):
        svc = PipelineStepAnnotator()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(6):
            ids.append(svc.annotate("pipe-1", f"step-{i}", f"note {i}"))
        # newest entry is always preserved
        assert svc.get_annotation(ids[5]) is not None

    def test_no_prune_under_limit(self):
        svc = PipelineStepAnnotator()
        svc.MAX_ENTRIES = 100
        for i in range(10):
            svc.annotate("pipe-1", f"step-{i}", f"note {i}")
        assert svc.get_annotation_count() == 10


class TestUniqueIds:
    """ID generation uniqueness."""

    def test_ids_have_correct_prefix(self):
        svc = PipelineStepAnnotator()
        aid = svc.annotate("p", "s", "n")
        assert aid.startswith("psan-")

    def test_many_ids_all_unique(self):
        svc = PipelineStepAnnotator()
        ids = set()
        for i in range(100):
            ids.add(svc.annotate("pipe-1", f"step-{i}", f"note {i}"))
        assert len(ids) == 100
