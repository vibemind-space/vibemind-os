"""Tests for PipelineStepLabeler service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_labeler import PipelineStepLabeler


class TestIdGeneration:
    def test_prefix(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "s1", "Init Step")
        assert rid.startswith("pslb-")

    def test_unique_ids(self):
        lb = PipelineStepLabeler()
        ids = {lb.label("p1", "s1", f"label-{i}") for i in range(20)}
        assert len(ids) == 20

    def test_id_is_string(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "s1", "test")
        assert isinstance(rid, str)


class TestLabelBasic:
    def test_label_returns_id(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "step-a", "Setup Phase")
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_label_stores_fields(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "step-a", "Setup Phase")
        entry = lb.get_label(rid)
        assert entry["pipeline_id"] == "p1"
        assert entry["step_name"] == "step-a"
        assert entry["label_text"] == "Setup Phase"

    def test_label_with_metadata(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "s1", "fast", metadata={"k": "v"})
        entry = lb.get_label(rid)
        assert entry["metadata"]["k"] == "v"

    def test_label_default_metadata_is_empty(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "s1", "test")
        entry = lb.get_label(rid)
        assert entry["metadata"] == {}

    def test_label_stores_created_at(self):
        lb = PipelineStepLabeler()
        before = time.time()
        rid = lb.label("p1", "s1", "label1")
        entry = lb.get_label(rid)
        assert entry["created_at"] >= before


class TestGetLabel:
    def test_found(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "s1", "x")
        assert lb.get_label(rid) is not None

    def test_not_found(self):
        lb = PipelineStepLabeler()
        assert lb.get_label("nonexistent") is None

    def test_returns_copy(self):
        lb = PipelineStepLabeler()
        rid = lb.label("p1", "s1", "x")
        a = lb.get_label(rid)
        b = lb.get_label(rid)
        assert a is not b


class TestGetLabels:
    def test_no_filter(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        lb.label("p2", "s2", "b")
        assert len(lb.get_labels()) == 2

    def test_filter_by_pipeline(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        lb.label("p2", "s2", "b")
        assert len(lb.get_labels(pipeline_id="p1")) == 1

    def test_ordering_newest_first(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        lb.label("p1", "s2", "b")
        labels = lb.get_labels(pipeline_id="p1")
        assert labels[0]["step_name"] == "s2"

    def test_limit(self):
        lb = PipelineStepLabeler()
        for i in range(10):
            lb.label("p1", f"s{i}", f"label-{i}")
        assert len(lb.get_labels(limit=3)) == 3

    def test_returns_copies(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        labels = lb.get_labels()
        assert labels[0] is not lb.get_labels()[0]

    def test_empty_result(self):
        lb = PipelineStepLabeler()
        assert lb.get_labels() == []


class TestGetLabelCount:
    def test_total(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        lb.label("p2", "s2", "b")
        assert lb.get_label_count() == 2

    def test_filtered(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        lb.label("p2", "s2", "b")
        assert lb.get_label_count(pipeline_id="p1") == 1

    def test_empty(self):
        lb = PipelineStepLabeler()
        assert lb.get_label_count() == 0


class TestGetStats:
    def test_empty(self):
        lb = PipelineStepLabeler()
        s = lb.get_stats()
        assert s["total_labels"] == 0

    def test_with_data(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        lb.label("p2", "s2", "b")
        s = lb.get_stats()
        assert s["total_labels"] == 2
        assert s["unique_pipelines"] == 2

    def test_unique_pipelines_deduplicates(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "a")
        lb.label("p1", "s2", "b")
        s = lb.get_stats()
        assert s["unique_pipelines"] == 1


class TestOnChangeCallback:
    def test_setter_getter(self):
        lb = PipelineStepLabeler()
        cb = lambda a, d: None
        lb.on_change = cb
        assert lb.on_change is cb

    def test_fires(self):
        lb = PipelineStepLabeler()
        events = []
        lb.on_change = lambda a, d: events.append((a, d))
        lb.label("p1", "s1", "t1")
        assert len(events) >= 1

    def test_fire_action_name(self):
        lb = PipelineStepLabeler()
        events = []
        lb.on_change = lambda a, d: events.append((a, d))
        lb.label("p1", "s1", "t1")
        assert events[0][0] == "labeled"

    def test_clear(self):
        lb = PipelineStepLabeler()
        lb.on_change = lambda a, d: None
        lb.on_change = None
        assert lb.on_change is None

    def test_exception_suppressed(self):
        lb = PipelineStepLabeler()
        lb.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = lb.label("p1", "s1", "t1")
        assert rid.startswith("pslb-")


class TestRemoveCallback:
    def test_remove_existing(self):
        lb = PipelineStepLabeler()
        lb._state.callbacks["test_cb"] = lambda a, d: None
        assert lb.remove_callback("test_cb") is True

    def test_remove_nonexistent(self):
        lb = PipelineStepLabeler()
        assert lb.remove_callback("nope") is False

    def test_remove_stops_firing(self):
        lb = PipelineStepLabeler()
        events = []
        lb._state.callbacks["mycb"] = lambda a, d: events.append(1)
        lb.label("p1", "s1", "x")
        count_before = len(events)
        lb.remove_callback("mycb")
        lb.label("p1", "s2", "y")
        assert len(events) == count_before


class TestPrune:
    def test_prune_at_max(self):
        lb = PipelineStepLabeler()
        lb.MAX_ENTRIES = 5
        for i in range(8):
            lb.label("p1", f"s{i}", f"label-{i}")
        assert lb.get_label_count() < 8


class TestReset:
    def test_clears_entries(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "x")
        lb.reset()
        assert lb.get_label_count() == 0

    def test_clears_callbacks(self):
        lb = PipelineStepLabeler()
        lb.on_change = lambda a, d: None
        lb.reset()
        assert lb.on_change is None

    def test_resets_seq(self):
        lb = PipelineStepLabeler()
        lb.label("p1", "s1", "x")
        lb.reset()
        assert lb._state._seq == 0
