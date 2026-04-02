from __future__ import annotations

import copy
import time

import pytest

from src.services.pipeline_step_deactivator import (
    PipelineStepDeactivator,
    PipelineStepDeactivatorState,
)


# ======================================================================
# TestBasic
# ======================================================================

class TestBasic:
    def test_prefix(self):
        d = PipelineStepDeactivator()
        rid = d.deactivate("p1", "step1")
        assert rid.startswith("psda-")

    def test_fields_present(self):
        d = PipelineStepDeactivator()
        rid = d.deactivate("p1", "step1", reason="bad", metadata={"k": "v"})
        entry = d.get_deactivation(rid)
        assert entry["record_id"] == rid
        assert entry["pipeline_id"] == "p1"
        assert entry["step_name"] == "step1"
        assert entry["reason"] == "bad"
        assert entry["metadata"] == {"k": "v"}
        assert "created_at" in entry
        assert "_seq" in entry

    def test_default_reason_empty(self):
        d = PipelineStepDeactivator()
        rid = d.deactivate("p1", "s1")
        entry = d.get_deactivation(rid)
        assert entry["reason"] == ""

    def test_deepcopy_returned(self):
        d = PipelineStepDeactivator()
        rid = d.deactivate("p1", "s1", metadata={"x": [1]})
        entry = d.get_deactivation(rid)
        entry["metadata"]["x"].append(2)
        original = d.get_deactivation(rid)
        assert original["metadata"]["x"] == [1]

    def test_empty_pipeline_id_returns_empty(self):
        d = PipelineStepDeactivator()
        assert d.deactivate("", "step") == ""

    def test_empty_step_name_returns_empty(self):
        d = PipelineStepDeactivator()
        assert d.deactivate("p1", "") == ""


# ======================================================================
# TestGet
# ======================================================================

class TestGet:
    def test_get_existing(self):
        d = PipelineStepDeactivator()
        rid = d.deactivate("p1", "s1")
        assert d.get_deactivation(rid) is not None

    def test_get_missing(self):
        d = PipelineStepDeactivator()
        assert d.get_deactivation("psda-nonexistent") is None


# ======================================================================
# TestList
# ======================================================================

class TestList:
    def test_filter_by_pipeline_id(self):
        d = PipelineStepDeactivator()
        d.deactivate("p1", "s1")
        d.deactivate("p2", "s2")
        d.deactivate("p1", "s3")
        results = d.get_deactivations(pipeline_id="p1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "p1" for r in results)

    def test_newest_first(self):
        d = PipelineStepDeactivator()
        r1 = d.deactivate("p1", "s1")
        r2 = d.deactivate("p1", "s2")
        r3 = d.deactivate("p1", "s3")
        results = d.get_deactivations(pipeline_id="p1")
        ids = [r["record_id"] for r in results]
        assert ids == [r3, r2, r1]

    def test_limit(self):
        d = PipelineStepDeactivator()
        for i in range(10):
            d.deactivate("p1", f"s{i}")
        results = d.get_deactivations(limit=3)
        assert len(results) == 3

    def test_all_pipelines(self):
        d = PipelineStepDeactivator()
        d.deactivate("p1", "s1")
        d.deactivate("p2", "s2")
        results = d.get_deactivations()
        assert len(results) == 2


# ======================================================================
# TestCount
# ======================================================================

class TestCount:
    def test_total_count(self):
        d = PipelineStepDeactivator()
        d.deactivate("p1", "s1")
        d.deactivate("p2", "s2")
        assert d.get_deactivation_count() == 2

    def test_count_by_pipeline(self):
        d = PipelineStepDeactivator()
        d.deactivate("p1", "s1")
        d.deactivate("p1", "s2")
        d.deactivate("p2", "s3")
        assert d.get_deactivation_count(pipeline_id="p1") == 2
        assert d.get_deactivation_count(pipeline_id="p2") == 1


# ======================================================================
# TestStats
# ======================================================================

class TestStats:
    def test_stats_keys(self):
        d = PipelineStepDeactivator()
        stats = d.get_stats()
        assert "total_deactivations" in stats
        assert "unique_pipelines" in stats

    def test_stats_values(self):
        d = PipelineStepDeactivator()
        d.deactivate("p1", "s1")
        d.deactivate("p1", "s2")
        d.deactivate("p2", "s3")
        stats = d.get_stats()
        assert stats["total_deactivations"] == 3
        assert stats["unique_pipelines"] == 2


# ======================================================================
# TestCallbacks
# ======================================================================

class TestCallbacks:
    def test_on_change_called(self):
        events: list[tuple] = []
        d = PipelineStepDeactivator(_on_change=lambda action, data: events.append((action, data)))
        d.deactivate("p1", "s1")
        assert len(events) == 1
        assert events[0][0] == "deactivate"
        assert events[0][1]["action"] == "deactivate"

    def test_registered_callback(self):
        events: list[tuple] = []
        d = PipelineStepDeactivator()
        d._state.callbacks["cb1"] = lambda action, data: events.append((action, data))
        d.deactivate("p1", "s1")
        assert len(events) == 1
        assert events[0][0] == "deactivate"


# ======================================================================
# TestPrune
# ======================================================================

class TestPrune:
    def test_prune_removes_oldest(self):
        d = PipelineStepDeactivator()
        d.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            rid = d.deactivate("p1", f"s{i}")
            ids.append(rid)
        assert len(d._state.entries) == 5
        # oldest two should be gone
        assert d.get_deactivation(ids[0]) is None
        assert d.get_deactivation(ids[1]) is None
        # newest should remain
        assert d.get_deactivation(ids[6]) is not None


# ======================================================================
# TestReset
# ======================================================================

class TestReset:
    def test_reset_clears_entries(self):
        d = PipelineStepDeactivator()
        d.deactivate("p1", "s1")
        d.reset()
        assert d.get_deactivation_count() == 0

    def test_reset_clears_on_change(self):
        called = []
        d = PipelineStepDeactivator(_on_change=lambda a, d: called.append(1))
        d.reset()
        assert d._on_change is None

    def test_reset_clears_callbacks(self):
        d = PipelineStepDeactivator()
        d._state.callbacks["x"] = lambda a, d: None
        d.reset()
        assert len(d._state.callbacks) == 0
