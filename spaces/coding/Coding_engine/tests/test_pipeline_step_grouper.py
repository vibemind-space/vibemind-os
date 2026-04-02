"""Tests for PipelineStepGrouper service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_grouper import PipelineStepGrouper


class TestIdGeneration:
    def test_prefix(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "s1")
        assert rid.startswith("psgr-")

    def test_unique_ids(self):
        g = PipelineStepGrouper()
        ids = {g.group("p1", f"s{i}") for i in range(20)}
        assert len(ids) == 20


class TestGroupBasic:
    def test_group_returns_id(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "step-a")
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_group_stores_fields(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "step-a", group_name="batch")
        entry = g.get_grouping(rid)
        assert entry["pipeline_id"] == "p1"
        assert entry["step_name"] == "step-a"
        assert entry["group_name"] == "batch"

    def test_group_default_group_name(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "s1")
        entry = g.get_grouping(rid)
        assert entry["group_name"] == "default"

    def test_group_with_metadata(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "s1", metadata={"k": "v"})
        entry = g.get_grouping(rid)
        assert entry["metadata"]["k"] == "v"

    def test_group_metadata_deepcopy(self):
        g = PipelineStepGrouper()
        meta = {"nested": {"a": 1}}
        rid = g.group("p1", "s1", metadata=meta)
        meta["nested"]["a"] = 999
        entry = g.get_grouping(rid)
        assert entry["metadata"]["nested"]["a"] == 1

    def test_group_stores_created_at(self):
        g = PipelineStepGrouper()
        before = time.time()
        rid = g.group("p1", "s1")
        entry = g.get_grouping(rid)
        assert entry["created_at"] >= before

    def test_group_stores_record_id(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "s1")
        entry = g.get_grouping(rid)
        assert entry["record_id"] == rid

    def test_group_stores_seq(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "s1")
        entry = g.get_grouping(rid)
        assert "_seq" in entry


class TestGroupValidation:
    def test_empty_pipeline_id_raises(self):
        g = PipelineStepGrouper()
        try:
            g.group("", "s1")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_empty_step_name_raises(self):
        g = PipelineStepGrouper()
        try:
            g.group("p1", "")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestGetGrouping:
    def test_found(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "s1")
        assert g.get_grouping(rid) is not None

    def test_not_found(self):
        g = PipelineStepGrouper()
        assert g.get_grouping("nonexistent") is None

    def test_returns_copy(self):
        g = PipelineStepGrouper()
        rid = g.group("p1", "s1")
        a = g.get_grouping(rid)
        b = g.get_grouping(rid)
        assert a is not b


class TestGetGroupings:
    def test_no_filter(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.group("p2", "s2")
        assert len(g.get_groupings()) == 2

    def test_filter_by_pipeline(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.group("p2", "s2")
        assert len(g.get_groupings(pipeline_id="p1")) == 1

    def test_ordering_newest_first(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.group("p1", "s2")
        groupings = g.get_groupings(pipeline_id="p1")
        assert groupings[0]["step_name"] == "s2"

    def test_limit(self):
        g = PipelineStepGrouper()
        for i in range(10):
            g.group("p1", f"s{i}")
        assert len(g.get_groupings(limit=3)) == 3

    def test_returns_copies(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        groupings = g.get_groupings()
        assert groupings[0] is not g.get_groupings()[0]


class TestGetGroupingCount:
    def test_total(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.group("p2", "s2")
        assert g.get_grouping_count() == 2

    def test_filtered(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.group("p2", "s2")
        assert g.get_grouping_count(pipeline_id="p1") == 1

    def test_empty(self):
        g = PipelineStepGrouper()
        assert g.get_grouping_count() == 0


class TestGetStats:
    def test_empty(self):
        g = PipelineStepGrouper()
        s = g.get_stats()
        assert s["total_groupings"] == 0

    def test_with_data(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.group("p2", "s2")
        s = g.get_stats()
        assert s["total_groupings"] == 2
        assert s["unique_pipelines"] == 2


class TestOnChangeCallback:
    def test_setter_getter(self):
        g = PipelineStepGrouper()
        cb = lambda a, d: None
        g.on_change = cb
        assert g.on_change is cb

    def test_fires(self):
        g = PipelineStepGrouper()
        events = []
        g.on_change = lambda a, d: events.append((a, d))
        g.group("p1", "s1")
        assert len(events) >= 1

    def test_fires_grouped_action(self):
        g = PipelineStepGrouper()
        events = []
        g.on_change = lambda a, d: events.append((a, d))
        g.group("p1", "s1")
        assert events[0][0] == "grouped"

    def test_clear(self):
        g = PipelineStepGrouper()
        g.on_change = lambda a, d: None
        g.on_change = None
        assert g.on_change is None

    def test_exception_suppressed(self):
        g = PipelineStepGrouper()
        g.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = g.group("p1", "s1")
        assert rid.startswith("psgr-")


class TestRemoveCallback:
    def test_remove_existing(self):
        g = PipelineStepGrouper()
        g._state.callbacks["test_cb"] = lambda a, d: None
        assert g.remove_callback("test_cb") is True

    def test_remove_nonexistent(self):
        g = PipelineStepGrouper()
        assert g.remove_callback("nope") is False

    def test_remove_stops_firing(self):
        g = PipelineStepGrouper()
        events = []
        g._state.callbacks["mycb"] = lambda a, d: events.append(1)
        g.group("p1", "s1")
        count_before = len(events)
        g.remove_callback("mycb")
        g.group("p1", "s2")
        assert len(events) == count_before


class TestPrune:
    def test_prune_at_max(self):
        g = PipelineStepGrouper()
        g.MAX_ENTRIES = 5
        for i in range(8):
            g.group("p1", f"s{i}")
        assert g.get_grouping_count() < 8

    def test_prune_removes_oldest(self):
        g = PipelineStepGrouper()
        g.MAX_ENTRIES = 5
        first_ids = []
        for i in range(8):
            rid = g.group("p1", f"s{i}")
            if i < 2:
                first_ids.append(rid)
        for old_id in first_ids:
            assert g.get_grouping(old_id) is None


class TestReset:
    def test_clears_entries(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.reset()
        assert g.get_grouping_count() == 0

    def test_clears_callbacks(self):
        g = PipelineStepGrouper()
        g.on_change = lambda a, d: None
        g.reset()
        assert g.on_change is None

    def test_resets_seq(self):
        g = PipelineStepGrouper()
        g.group("p1", "s1")
        g.reset()
        assert g._state._seq == 0
