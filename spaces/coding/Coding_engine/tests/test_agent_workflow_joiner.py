"""Tests for agent_workflow_joiner module."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from src.services.agent_workflow_joiner import AgentWorkflowJoiner


# ---------------------------------------------------------------------------
# TestBasic
# ---------------------------------------------------------------------------

class TestBasic:
    def test_join_returns_id_with_prefix(self):
        j = AgentWorkflowJoiner()
        rid = j.join("a1", "wf1")
        assert rid.startswith("awjn-")

    def test_join_fields_correct(self):
        j = AgentWorkflowJoiner()
        rid = j.join("a1", "wf1")
        entry = j.get_join(rid)
        assert entry["record_id"] == rid
        assert entry["agent_id"] == "a1"
        assert entry["workflow_name"] == "wf1"
        assert "created_at" in entry
        assert "updated_at" in entry

    def test_default_strategy_is_merge(self):
        j = AgentWorkflowJoiner()
        rid = j.join("a1", "wf1")
        entry = j.get_join(rid)
        assert entry["strategy"] == "merge"

    def test_custom_strategy(self):
        j = AgentWorkflowJoiner()
        rid = j.join("a1", "wf1", strategy="replace")
        entry = j.get_join(rid)
        assert entry["strategy"] == "replace"

    def test_metadata_deepcopy(self):
        j = AgentWorkflowJoiner()
        meta = {"key": [1, 2, 3]}
        rid = j.join("a1", "wf1", metadata=meta)
        meta["key"].append(4)
        entry = j.get_join(rid)
        assert entry["metadata"]["key"] == [1, 2, 3]

    def test_empty_agent_id_returns_empty_string(self):
        j = AgentWorkflowJoiner()
        assert j.join("", "wf1") == ""

    def test_empty_workflow_name_returns_empty_string(self):
        j = AgentWorkflowJoiner()
        assert j.join("a1", "") == ""


# ---------------------------------------------------------------------------
# TestGet
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_found(self):
        j = AgentWorkflowJoiner()
        rid = j.join("a1", "wf1")
        entry = j.get_join(rid)
        assert entry is not None
        assert entry["record_id"] == rid

    def test_get_not_found_returns_none(self):
        j = AgentWorkflowJoiner()
        assert j.get_join("nonexistent") is None

    def test_get_returns_copy(self):
        j = AgentWorkflowJoiner()
        rid = j.join("a1", "wf1")
        entry = j.get_join(rid)
        entry["agent_id"] = "modified"
        original = j.get_join(rid)
        assert original["agent_id"] == "a1"


# ---------------------------------------------------------------------------
# TestList
# ---------------------------------------------------------------------------

class TestList:
    def test_get_joins_all_entries(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.join("a2", "wf2")
        j.join("a3", "wf3")
        results = j.get_joins()
        assert len(results) == 3

    def test_get_joins_filter_by_agent_id(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.join("a1", "wf2")
        j.join("a2", "wf3")
        results = j.get_joins(agent_id="a1")
        assert len(results) == 2
        assert all(e["agent_id"] == "a1" for e in results)

    def test_get_joins_newest_first(self):
        j = AgentWorkflowJoiner()
        r1 = j.join("a1", "wf1")
        r2 = j.join("a1", "wf2")
        r3 = j.join("a1", "wf3")
        results = j.get_joins(agent_id="a1")
        assert results[0]["record_id"] == r3
        assert results[-1]["record_id"] == r1


# ---------------------------------------------------------------------------
# TestCount
# ---------------------------------------------------------------------------

class TestCount:
    def test_total_count(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.join("a2", "wf2")
        assert j.get_join_count() == 2

    def test_filtered_count(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.join("a1", "wf2")
        j.join("a2", "wf3")
        assert j.get_join_count(agent_id="a1") == 2
        assert j.get_join_count(agent_id="a2") == 1


# ---------------------------------------------------------------------------
# TestStats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_keys(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.join("a2", "wf2")
        stats = j.get_stats()
        assert "total_joins" in stats
        assert "unique_agents" in stats

    def test_stats_values(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.join("a1", "wf2")
        j.join("a2", "wf3")
        stats = j.get_stats()
        assert stats["total_joins"] == 3
        assert stats["unique_agents"] == 2


# ---------------------------------------------------------------------------
# TestCallbacks
# ---------------------------------------------------------------------------

class TestCallbacks:
    def test_on_change_fires(self):
        j = AgentWorkflowJoiner()
        fired = []
        j.on_change = lambda action, data: fired.append((action, data))
        j.join("a1", "wf1")
        assert len(fired) == 1
        assert fired[0][0] == "join"

    def test_remove_callback_returns_true(self):
        j = AgentWorkflowJoiner()
        j._state.callbacks["cb1"] = lambda a, d: None
        assert j.remove_callback("cb1") is True
        assert "cb1" not in j._state.callbacks

    def test_remove_callback_unknown_returns_false(self):
        j = AgentWorkflowJoiner()
        assert j.remove_callback("nonexistent") is False


# ---------------------------------------------------------------------------
# TestPrune
# ---------------------------------------------------------------------------

class TestPrune:
    def test_prune_reduces_entries(self):
        j = AgentWorkflowJoiner()
        j.MAX_ENTRIES = 5
        for i in range(7):
            j.join(f"agent_{i}", f"wf_{i}")
        # After adding 7 with MAX_ENTRIES=5, prune should have removed some
        assert j.get_join_count() < 7


# ---------------------------------------------------------------------------
# TestReset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_entries(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.join("a2", "wf2")
        j.reset()
        assert j.get_join_count() == 0

    def test_reset_on_change_is_none(self):
        j = AgentWorkflowJoiner()
        j.on_change = lambda a, d: None
        j.reset()
        assert j.on_change is None

    def test_reset_seq_resets_to_zero(self):
        j = AgentWorkflowJoiner()
        j.join("a1", "wf1")
        j.reset()
        assert j._state._seq == 0
