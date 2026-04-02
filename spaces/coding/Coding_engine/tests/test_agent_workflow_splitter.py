"""Tests for AgentWorkflowSplitter service."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_splitter import AgentWorkflowSplitter


class TestBasic:
    """Basic split creation tests."""

    def test_prefix(self) -> None:
        svc = AgentWorkflowSplitter()
        rid = svc.split("a1", "wf1")
        assert rid.startswith("awsp-")

    def test_id_length(self) -> None:
        svc = AgentWorkflowSplitter()
        rid = svc.split("a1", "wf1")
        assert len(rid) > len("awsp-")

    def test_fields_present(self) -> None:
        svc = AgentWorkflowSplitter()
        rid = svc.split("a1", "wf1", parts=3, metadata={"k": "v"})
        rec = svc.get_split(rid)
        assert rec is not None
        assert rec["agent_id"] == "a1"
        assert rec["workflow_name"] == "wf1"
        assert rec["parts"] == 3
        assert rec["metadata"] == {"k": "v"}
        assert "created_at" in rec
        assert "updated_at" in rec
        assert "_seq" in rec
        assert "record_id" in rec

    def test_default_parts_is_two(self) -> None:
        svc = AgentWorkflowSplitter()
        rid = svc.split("a1", "wf1")
        rec = svc.get_split(rid)
        assert rec["parts"] == 2

    def test_metadata_deepcopy(self) -> None:
        svc = AgentWorkflowSplitter()
        meta = {"nested": [1, 2, 3]}
        rid = svc.split("a1", "wf1", metadata=meta)
        meta["nested"].append(4)
        rec = svc.get_split(rid)
        assert rec["metadata"]["nested"] == [1, 2, 3]

    def test_empty_agent_id_returns_empty(self) -> None:
        svc = AgentWorkflowSplitter()
        result = svc.split("", "wf1")
        assert result == ""

    def test_empty_workflow_name_returns_empty(self) -> None:
        svc = AgentWorkflowSplitter()
        result = svc.split("a1", "")
        assert result == ""

    def test_both_empty_returns_empty(self) -> None:
        svc = AgentWorkflowSplitter()
        result = svc.split("", "")
        assert result == ""


class TestGet:
    """Tests for get_split."""

    def test_get_existing(self) -> None:
        svc = AgentWorkflowSplitter()
        rid = svc.split("a1", "wf1")
        rec = svc.get_split(rid)
        assert rec is not None
        assert rec["record_id"] == rid

    def test_get_nonexistent_returns_none(self) -> None:
        svc = AgentWorkflowSplitter()
        assert svc.get_split("awsp-doesnotexist") is None

    def test_get_returns_copy(self) -> None:
        svc = AgentWorkflowSplitter()
        rid = svc.split("a1", "wf1")
        rec1 = svc.get_split(rid)
        rec1["agent_id"] = "modified"
        rec2 = svc.get_split(rid)
        assert rec2["agent_id"] == "a1"


class TestList:
    """Tests for get_splits."""

    def test_list_all(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.split("a2", "wf2")
        results = svc.get_splits()
        assert len(results) == 2

    def test_filter_by_agent(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.split("a2", "wf2")
        svc.split("a1", "wf3")
        results = svc.get_splits(agent_id="a1")
        assert len(results) == 2
        for r in results:
            assert r["agent_id"] == "a1"

    def test_newest_first(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.split("a1", "wf2")
        results = svc.get_splits(agent_id="a1")
        assert results[0]["_seq"] >= results[1]["_seq"]

    def test_limit(self) -> None:
        svc = AgentWorkflowSplitter()
        for i in range(10):
            svc.split("a1", f"wf{i}")
        results = svc.get_splits(limit=3)
        assert len(results) == 3


class TestCount:
    """Tests for get_split_count."""

    def test_count_all(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.split("a2", "wf2")
        assert svc.get_split_count() == 2

    def test_count_by_agent(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.split("a2", "wf2")
        svc.split("a1", "wf3")
        assert svc.get_split_count(agent_id="a1") == 2

    def test_count_empty(self) -> None:
        svc = AgentWorkflowSplitter()
        assert svc.get_split_count() == 0


class TestStats:
    """Tests for get_stats."""

    def test_stats_empty(self) -> None:
        svc = AgentWorkflowSplitter()
        stats = svc.get_stats()
        assert stats["total_splits"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_with_data(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.split("a2", "wf2")
        svc.split("a1", "wf3")
        stats = svc.get_stats()
        assert stats["total_splits"] == 3
        assert stats["unique_agents"] == 2


class TestCallbacks:
    """Tests for on_change and callbacks."""

    def test_on_change_property_default_none(self) -> None:
        svc = AgentWorkflowSplitter()
        assert svc.on_change is None

    def test_on_change_setter(self) -> None:
        svc = AgentWorkflowSplitter()
        cb = lambda action, **kw: None
        svc.on_change = cb
        assert svc.on_change is cb

    def test_on_change_fires_on_split(self) -> None:
        svc = AgentWorkflowSplitter()
        calls = []
        svc.on_change = lambda action, **kw: calls.append((action, kw))
        svc.split("a1", "wf1")
        assert len(calls) == 1
        assert calls[0][0] == "split"

    def test_state_callback_fires(self) -> None:
        svc = AgentWorkflowSplitter()
        calls = []
        svc._state.callbacks["test_cb"] = lambda action, **kw: calls.append(action)
        svc.split("a1", "wf1")
        assert "split" in calls

    def test_remove_callback(self) -> None:
        svc = AgentWorkflowSplitter()
        svc._state.callbacks["cb1"] = lambda action, **kw: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_remove_nonexistent_callback(self) -> None:
        svc = AgentWorkflowSplitter()
        assert svc.remove_callback("nope") is False

    def test_on_change_called_before_state_callbacks(self) -> None:
        svc = AgentWorkflowSplitter()
        order = []
        svc.on_change = lambda action, **kw: order.append("on_change")
        svc._state.callbacks["cb"] = lambda action, **kw: order.append("cb")
        svc.split("a1", "wf1")
        assert order == ["on_change", "cb"]


class TestPrune:
    """Tests for pruning behavior."""

    def test_prune_removes_oldest_quarter(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            rid = svc.split("a1", f"wf{i}")
            ids.append(rid)
        total = svc.get_split_count()
        assert total < 7

    def test_prune_keeps_newest(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.MAX_ENTRIES = 5
        for i in range(7):
            svc.split("a1", f"wf{i}")
        results = svc.get_splits()
        assert len(results) > 0
        names = [r["workflow_name"] for r in results]
        assert "wf6" in names


class TestReset:
    """Tests for reset."""

    def test_reset_clears_entries(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.split("a2", "wf2")
        svc.reset()
        assert svc.get_split_count() == 0

    def test_reset_clears_on_change(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.on_change = lambda action, **kw: None
        svc.reset()
        assert svc.on_change is None

    def test_reset_clears_callbacks(self) -> None:
        svc = AgentWorkflowSplitter()
        svc._state.callbacks["cb1"] = lambda action, **kw: None
        svc.reset()
        assert len(svc._state.callbacks) == 0

    def test_reset_resets_seq(self) -> None:
        svc = AgentWorkflowSplitter()
        svc.split("a1", "wf1")
        svc.reset()
        assert svc._state._seq == 0
