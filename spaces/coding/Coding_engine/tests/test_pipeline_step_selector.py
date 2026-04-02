"""Tests for PipelineStepSelector service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_selector import PipelineStepSelector


class TestCreateSelector:
    def test_create_selector_returns_id(self):
        sel = PipelineStepSelector()
        result = sel.create_selector("pipe-1", ["step-a", "step-b"])
        assert result.startswith("psse-")
        assert len(result) > 5

    def test_create_selector_with_criteria_all(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a"], criteria="all")
        entry = sel.get_selector(sid)
        assert entry["criteria"] == "all"

    def test_create_selector_with_criteria_first(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a", "step-b"], criteria="first")
        entry = sel.get_selector(sid)
        assert entry["criteria"] == "first"

    def test_create_selector_with_criteria_random(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a", "step-b"], criteria="random")
        entry = sel.get_selector(sid)
        assert entry["criteria"] == "random"

    def test_create_selector_invalid_criteria(self):
        sel = PipelineStepSelector()
        result = sel.create_selector("pipe-1", ["step-a"], criteria="invalid")
        assert result == ""

    def test_create_selector_empty_pipeline_id(self):
        sel = PipelineStepSelector()
        result = sel.create_selector("", ["step-a"])
        assert result == ""

    def test_create_selector_empty_step_names(self):
        sel = PipelineStepSelector()
        result = sel.create_selector("pipe-1", [])
        assert result == ""

    def test_create_selector_unique_ids(self):
        sel = PipelineStepSelector()
        ids = set()
        for i in range(20):
            sid = sel.create_selector("pipe-1", [f"step-{i}"])
            ids.add(sid)
        assert len(ids) == 20

    def test_create_selector_stores_step_names(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a", "step-b", "step-c"])
        entry = sel.get_selector(sid)
        assert entry["step_names"] == ["step-a", "step-b", "step-c"]

    def test_create_selector_default_criteria_is_all(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a"])
        entry = sel.get_selector(sid)
        assert entry["criteria"] == "all"


class TestGetSelector:
    def test_get_selector_found(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a"])
        entry = sel.get_selector(sid)
        assert entry is not None
        assert entry["pipeline_id"] == "pipe-1"
        assert entry["selector_id"] == sid

    def test_get_selector_not_found(self):
        sel = PipelineStepSelector()
        assert sel.get_selector("nonexistent") is None

    def test_get_selector_has_created_at(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a"])
        entry = sel.get_selector(sid)
        assert "created_at" in entry
        assert entry["created_at"] > 0


class TestSelect:
    def test_select_all_returns_all_steps(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a", "step-b", "step-c"], criteria="all")
        result = sel.select(sid)
        assert result == ["step-a", "step-b", "step-c"]

    def test_select_first_returns_first_step(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a", "step-b", "step-c"], criteria="first")
        result = sel.select(sid)
        assert result == ["step-a"]

    def test_select_random_returns_one_step(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a", "step-b", "step-c"], criteria="random")
        result = sel.select(sid)
        assert len(result) == 1
        assert result[0] in ["step-a", "step-b", "step-c"]

    def test_select_not_found(self):
        sel = PipelineStepSelector()
        result = sel.select("nonexistent")
        assert result == []

    def test_select_increments_total_selections(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a"])
        sel.select(sid)
        sel.select(sid)
        entry = sel.get_selector(sid)
        assert entry["total_selections"] == 2

    def test_select_returns_list_of_strings(self):
        sel = PipelineStepSelector()
        sid = sel.create_selector("pipe-1", ["step-a", "step-b"])
        result = sel.select(sid)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)


class TestGetSelectors:
    def test_get_selectors_all(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.create_selector("pipe-2", ["step-b"])
        results = sel.get_selectors()
        assert len(results) == 2

    def test_get_selectors_filter_by_pipeline(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.create_selector("pipe-2", ["step-b"])
        sel.create_selector("pipe-1", ["step-c"])
        results = sel.get_selectors(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_get_selectors_newest_first(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.create_selector("pipe-1", ["step-b"])
        results = sel.get_selectors()
        assert results[0]["created_at"] >= results[1]["created_at"]

    def test_get_selectors_respects_limit(self):
        sel = PipelineStepSelector()
        for i in range(10):
            sel.create_selector("pipe-1", [f"step-{i}"])
        results = sel.get_selectors(limit=3)
        assert len(results) == 3

    def test_get_selectors_sorted_by_seq(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.create_selector("pipe-1", ["step-b"])
        sel.create_selector("pipe-1", ["step-c"])
        results = sel.get_selectors()
        seqs = [r["_seq"] for r in results]
        assert seqs == sorted(seqs, reverse=True)


class TestGetSelectorCount:
    def test_count_all(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.create_selector("pipe-2", ["step-b"])
        assert sel.get_selector_count() == 2

    def test_count_filtered(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.create_selector("pipe-2", ["step-b"])
        sel.create_selector("pipe-1", ["step-c"])
        assert sel.get_selector_count("pipe-1") == 2
        assert sel.get_selector_count("pipe-2") == 1

    def test_count_empty(self):
        sel = PipelineStepSelector()
        assert sel.get_selector_count() == 0


class TestGetStats:
    def test_stats_empty(self):
        sel = PipelineStepSelector()
        stats = sel.get_stats()
        assert stats["total_selectors"] == 0
        assert stats["unique_pipelines"] == 0
        assert stats["total_selections"] == 0

    def test_stats_populated(self):
        sel = PipelineStepSelector()
        sid1 = sel.create_selector("pipe-1", ["step-a"])
        sel.create_selector("pipe-2", ["step-b"])
        sel.select(sid1)
        sel.select(sid1)
        stats = sel.get_stats()
        assert stats["total_selectors"] == 2
        assert stats["unique_pipelines"] == 2
        assert stats["total_selections"] == 2

    def test_stats_returns_dict(self):
        sel = PipelineStepSelector()
        stats = sel.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    def test_reset_clears_entries(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.reset()
        assert sel.get_selector_count() == 0

    def test_reset_clears_callbacks(self):
        sel = PipelineStepSelector()
        sel._callbacks["test"] = lambda a, d: None
        sel.on_change = lambda a, d: None
        sel.reset()
        assert sel._callbacks == {}
        assert sel.on_change is None

    def test_reset_resets_seq(self):
        sel = PipelineStepSelector()
        sel.create_selector("pipe-1", ["step-a"])
        sel.reset()
        assert sel._state._seq == 0


class TestCallbacksAndEvents:
    def test_on_change_fires_on_create(self):
        sel = PipelineStepSelector()
        events = []
        sel.on_change = lambda action, data: events.append((action, data))
        sel.create_selector("pipe-1", ["step-a"])
        assert len(events) == 1
        assert events[0][0] == "selector_created"

    def test_on_change_fires_on_select(self):
        sel = PipelineStepSelector()
        events = []
        sid = sel.create_selector("pipe-1", ["step-a"])
        sel.on_change = lambda action, data: events.append((action, data))
        sel.select(sid)
        assert len(events) == 1
        assert events[0][0] == "selection_applied"

    def test_callback_exception_is_silent(self):
        sel = PipelineStepSelector()
        sel.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        sid = sel.create_selector("pipe-1", ["step-a"])
        assert sid != ""

    def test_remove_callback(self):
        sel = PipelineStepSelector()
        sel._callbacks["cb1"] = lambda a, d: None
        assert sel.remove_callback("cb1") is True
        assert sel.remove_callback("cb1") is False

    def test_named_callbacks_fire(self):
        sel = PipelineStepSelector()
        events = []
        sel._callbacks["my_cb"] = lambda a, d: events.append(a)
        sel.create_selector("pipe-1", ["step-a"])
        assert "selector_created" in events

    def test_select_event_contains_selected_steps(self):
        sel = PipelineStepSelector()
        events = []
        sel.on_change = lambda action, data: events.append((action, data))
        sid = sel.create_selector("pipe-1", ["step-a", "step-b"], criteria="all")
        sel.select(sid)
        select_event = [e for e in events if e[0] == "selection_applied"][0]
        assert select_event[1]["selected"] == ["step-a", "step-b"]


class TestPruning:
    def test_prune_removes_oldest(self):
        sel = PipelineStepSelector()
        sel.MAX_ENTRIES = 5
        for i in range(8):
            sel.create_selector("pipe-1", [f"step-{i}"])
        assert sel.get_selector_count() <= 6
