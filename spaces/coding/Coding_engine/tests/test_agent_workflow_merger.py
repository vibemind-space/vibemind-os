"""Tests for AgentWorkflowMerger."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_merger import AgentWorkflowMerger


class TestIdGeneration:
    def test_id_has_prefix(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf1")
        assert rid.startswith("awmg-")

    def test_ids_are_unique(self):
        merger = AgentWorkflowMerger()
        ids = {merger.merge("a1", "wf1") for _ in range(20)}
        assert len(ids) == 20


class TestBasicMerge:
    def test_merge_returns_string(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("agent-1", "deploy")
        assert isinstance(rid, str)

    def test_merge_stores_entry(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("agent-1", "deploy")
        entry = merger.get_merge(rid)
        assert entry is not None
        assert entry["agent_id"] == "agent-1"
        assert entry["workflow_name"] == "deploy"

    def test_merge_default_strategy(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf")
        entry = merger.get_merge(rid)
        assert entry["strategy"] == "combine"

    def test_merge_custom_strategy(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf", strategy="rebase")
        entry = merger.get_merge(rid)
        assert entry["strategy"] == "rebase"

    def test_merge_default_branches_empty(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf")
        entry = merger.get_merge(rid)
        assert entry["branches"] == []


class TestMetadataAndBranches:
    def test_merge_with_branches(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf", branches=["main", "feature"])
        entry = merger.get_merge(rid)
        assert entry["branches"] == ["main", "feature"]

    def test_merge_with_metadata(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf", metadata={"priority": "high"})
        entry = merger.get_merge(rid)
        assert entry["metadata"] == {"priority": "high"}

    def test_metadata_default_empty(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf")
        entry = merger.get_merge(rid)
        assert entry["metadata"] == {}


class TestGetMerge:
    def test_get_merge_found(self):
        merger = AgentWorkflowMerger()
        rid = merger.merge("a1", "wf")
        result = merger.get_merge(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_merge_not_found(self):
        merger = AgentWorkflowMerger()
        result = merger.get_merge("awmg-nonexistent")
        assert result is None


class TestGetMerges:
    def test_list_all(self):
        merger = AgentWorkflowMerger()
        merger.merge("a1", "wf1")
        merger.merge("a2", "wf2")
        results = merger.get_merges()
        assert len(results) == 2

    def test_filter_by_agent(self):
        merger = AgentWorkflowMerger()
        merger.merge("a1", "wf1")
        merger.merge("a2", "wf2")
        merger.merge("a1", "wf3")
        results = merger.get_merges(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_ordering_newest_first(self):
        merger = AgentWorkflowMerger()
        r1 = merger.merge("a1", "wf1")
        r2 = merger.merge("a1", "wf2")
        r3 = merger.merge("a1", "wf3")
        results = merger.get_merges()
        assert results[0]["record_id"] == r3
        assert results[-1]["record_id"] == r1

    def test_limit(self):
        merger = AgentWorkflowMerger()
        for i in range(10):
            merger.merge("a1", f"wf{i}")
        results = merger.get_merges(limit=3)
        assert len(results) == 3


class TestGetMergeCount:
    def test_count_all(self):
        merger = AgentWorkflowMerger()
        merger.merge("a1", "wf1")
        merger.merge("a2", "wf2")
        assert merger.get_merge_count() == 2

    def test_count_filtered(self):
        merger = AgentWorkflowMerger()
        merger.merge("a1", "wf1")
        merger.merge("a2", "wf2")
        merger.merge("a1", "wf3")
        assert merger.get_merge_count(agent_id="a1") == 2


class TestGetStats:
    def test_stats_empty(self):
        merger = AgentWorkflowMerger()
        stats = merger.get_stats()
        assert stats["total_merges"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_with_data(self):
        merger = AgentWorkflowMerger()
        merger.merge("a1", "wf1")
        merger.merge("a2", "wf2")
        merger.merge("a1", "wf3")
        stats = merger.get_stats()
        assert stats["total_merges"] == 3
        assert stats["unique_agents"] == 2


class TestOnChange:
    def test_on_change_fires(self):
        merger = AgentWorkflowMerger()
        events = []
        merger.on_change = lambda action, data: events.append((action, data))
        merger.merge("a1", "wf1")
        assert len(events) == 1
        assert events[0][0] == "merged"

    def test_on_change_getter(self):
        merger = AgentWorkflowMerger()
        assert merger.on_change is None
        cb = lambda a, d: None
        merger.on_change = cb
        assert merger.on_change is cb

    def test_on_change_set_none_removes(self):
        merger = AgentWorkflowMerger()
        merger.on_change = lambda a, d: None
        assert merger.on_change is not None
        merger.on_change = None
        assert merger.on_change is None

    def test_exception_in_callback_swallowed(self):
        merger = AgentWorkflowMerger()
        merger.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        # Should not raise
        rid = merger.merge("a1", "wf1")
        assert rid.startswith("awmg-")


class TestRemoveCallback:
    def test_remove_existing(self):
        merger = AgentWorkflowMerger()
        merger._state.callbacks["my_cb"] = lambda a, d: None
        assert merger.remove_callback("my_cb") is True

    def test_remove_nonexistent(self):
        merger = AgentWorkflowMerger()
        assert merger.remove_callback("no_such") is False


class TestPrune:
    def test_prune_removes_excess(self):
        merger = AgentWorkflowMerger()
        original_max = AgentWorkflowMerger.MAX_ENTRIES
        AgentWorkflowMerger.MAX_ENTRIES = 5
        try:
            for i in range(8):
                merger.merge("a1", f"wf{i}")
            assert len(merger._state.entries) == 5
        finally:
            AgentWorkflowMerger.MAX_ENTRIES = original_max

    def test_prune_keeps_newest(self):
        merger = AgentWorkflowMerger()
        original_max = AgentWorkflowMerger.MAX_ENTRIES
        AgentWorkflowMerger.MAX_ENTRIES = 3
        try:
            ids = []
            for i in range(5):
                ids.append(merger.merge("a1", f"wf{i}"))
            # Oldest should be gone, newest should remain
            assert merger.get_merge(ids[-1]) is not None
            assert merger.get_merge(ids[0]) is None
        finally:
            AgentWorkflowMerger.MAX_ENTRIES = original_max


class TestReset:
    def test_reset_clears_entries(self):
        merger = AgentWorkflowMerger()
        merger.merge("a1", "wf1")
        merger.merge("a2", "wf2")
        merger.reset()
        assert merger.get_merge_count() == 0
        assert merger.get_merges() == []

    def test_reset_clears_callbacks(self):
        merger = AgentWorkflowMerger()
        merger.on_change = lambda a, d: None
        merger.reset()
        assert merger.on_change is None

    def test_reset_resets_seq(self):
        merger = AgentWorkflowMerger()
        merger.merge("a1", "wf1")
        merger.reset()
        assert merger._state._seq == 0
