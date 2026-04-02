"""Tests for PipelineStepTagger service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_tagger import PipelineStepTagger


class TestIdGeneration:
    def test_prefix(self):
        t = PipelineStepTagger()
        rid = t.tag("p1", "s1", "fast")
        assert rid.startswith("pstg-")

    def test_unique_ids(self):
        t = PipelineStepTagger()
        ids = {t.tag("p1", "s1", f"t{i}") for i in range(20)}
        assert len(ids) == 20


class TestTagBasic:
    def test_tag_returns_id(self):
        t = PipelineStepTagger()
        rid = t.tag("p1", "step-a", "urgent")
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_tag_stores_fields(self):
        t = PipelineStepTagger()
        rid = t.tag("p1", "step-a", "urgent")
        entry = t.get_tag(rid)
        assert entry["pipeline_id"] == "p1"
        assert entry["step_name"] == "step-a"
        assert entry["tag"] == "urgent"

    def test_tag_with_metadata(self):
        t = PipelineStepTagger()
        rid = t.tag("p1", "s1", "fast", metadata={"k": "v"})
        entry = t.get_tag(rid)
        assert entry["metadata"]["k"] == "v"

    def test_tag_stores_created_at(self):
        t = PipelineStepTagger()
        before = time.time()
        rid = t.tag("p1", "s1", "tag1")
        entry = t.get_tag(rid)
        assert entry["created_at"] >= before


class TestGetTag:
    def test_found(self):
        t = PipelineStepTagger()
        rid = t.tag("p1", "s1", "x")
        assert t.get_tag(rid) is not None

    def test_not_found(self):
        t = PipelineStepTagger()
        assert t.get_tag("nonexistent") is None

    def test_returns_copy(self):
        t = PipelineStepTagger()
        rid = t.tag("p1", "s1", "x")
        a = t.get_tag(rid)
        b = t.get_tag(rid)
        assert a is not b


class TestGetTags:
    def test_no_filter(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "a")
        t.tag("p2", "s2", "b")
        assert len(t.get_tags()) == 2

    def test_filter_by_pipeline(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "a")
        t.tag("p2", "s2", "b")
        assert len(t.get_tags(pipeline_id="p1")) == 1

    def test_ordering_newest_first(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "a")
        t.tag("p1", "s2", "b")
        tags = t.get_tags(pipeline_id="p1")
        assert tags[0]["step_name"] == "s2"

    def test_limit(self):
        t = PipelineStepTagger()
        for i in range(10):
            t.tag("p1", f"s{i}", f"t{i}")
        assert len(t.get_tags(limit=3)) == 3

    def test_returns_copies(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "a")
        tags = t.get_tags()
        assert tags[0] is not t.get_tags()[0]


class TestGetTagCount:
    def test_total(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "a")
        t.tag("p2", "s2", "b")
        assert t.get_tag_count() == 2

    def test_filtered(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "a")
        t.tag("p2", "s2", "b")
        assert t.get_tag_count(pipeline_id="p1") == 1

    def test_empty(self):
        t = PipelineStepTagger()
        assert t.get_tag_count() == 0


class TestGetStats:
    def test_empty(self):
        t = PipelineStepTagger()
        s = t.get_stats()
        assert s["total_tags"] == 0

    def test_with_data(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "a")
        t.tag("p2", "s2", "b")
        s = t.get_stats()
        assert s["total_tags"] == 2
        assert s["unique_pipelines"] == 2


class TestOnChangeCallback:
    def test_setter_getter(self):
        t = PipelineStepTagger()
        cb = lambda a, d: None
        t.on_change = cb
        assert t.on_change is cb

    def test_fires(self):
        t = PipelineStepTagger()
        events = []
        t.on_change = lambda a, d: events.append((a, d))
        t.tag("p1", "s1", "t1")
        assert len(events) >= 1

    def test_clear(self):
        t = PipelineStepTagger()
        t.on_change = lambda a, d: None
        t.on_change = None
        assert t.on_change is None

    def test_exception_suppressed(self):
        t = PipelineStepTagger()
        t.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = t.tag("p1", "s1", "t1")
        assert rid.startswith("pstg-")


class TestRemoveCallback:
    def test_remove_existing(self):
        t = PipelineStepTagger()
        t._state.callbacks["test_cb"] = lambda a, d: None
        assert t.remove_callback("test_cb") is True

    def test_remove_nonexistent(self):
        t = PipelineStepTagger()
        assert t.remove_callback("nope") is False

    def test_remove_stops_firing(self):
        t = PipelineStepTagger()
        events = []
        t._state.callbacks["mycb"] = lambda a, d: events.append(1)
        t.tag("p1", "s1", "x")
        count_before = len(events)
        t.remove_callback("mycb")
        t.tag("p1", "s2", "y")
        assert len(events) == count_before


class TestPrune:
    def test_prune_at_max(self):
        t = PipelineStepTagger()
        t.MAX_ENTRIES = 5
        for i in range(8):
            t.tag("p1", f"s{i}", f"t{i}")
        assert t.get_tag_count() < 8  # prune removed some entries


class TestReset:
    def test_clears_entries(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "x")
        t.reset()
        assert t.get_tag_count() == 0

    def test_clears_callbacks(self):
        t = PipelineStepTagger()
        t.on_change = lambda a, d: None
        t.reset()
        assert t.on_change is None

    def test_resets_seq(self):
        t = PipelineStepTagger()
        t.tag("p1", "s1", "x")
        t.reset()
        assert t._state._seq == 0
