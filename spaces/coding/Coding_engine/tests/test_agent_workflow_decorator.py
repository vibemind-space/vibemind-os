from __future__ import annotations

import copy
import hashlib
import logging
import time

import pytest

from src.services.agent_workflow_decorator import (
    AgentWorkflowDecorator,
    AgentWorkflowDecoratorState,
)


# ======================================================================
# TestBasic
# ======================================================================

class TestBasic:
    def test_prefix(self):
        assert AgentWorkflowDecorator.PREFIX == "awdc-"

    def test_decorate_returns_id_with_prefix(self):
        dec = AgentWorkflowDecorator()
        rid = dec.decorate("agent-1", "wf-a")
        assert rid.startswith("awdc-")

    def test_decorate_fields(self):
        dec = AgentWorkflowDecorator()
        rid = dec.decorate("agent-1", "wf-a", metadata={"k": "v"})
        entry = dec.get_decoration(rid)
        assert entry is not None
        assert entry["agent_id"] == "agent-1"
        assert entry["workflow_name"] == "wf-a"
        assert entry["metadata"] == {"k": "v"}
        assert "created_at" in entry
        assert "_seq" in entry

    def test_default_decoration_value(self):
        dec = AgentWorkflowDecorator()
        rid = dec.decorate("agent-1", "wf-a")
        entry = dec.get_decoration(rid)
        assert entry["decoration"] == "default"

    def test_deepcopy_metadata(self):
        dec = AgentWorkflowDecorator()
        meta = {"nested": [1, 2]}
        rid = dec.decorate("agent-1", "wf-a", metadata=meta)
        meta["nested"].append(3)
        entry = dec.get_decoration(rid)
        assert entry["metadata"]["nested"] == [1, 2]

    def test_empty_agent_id_returns_empty(self):
        dec = AgentWorkflowDecorator()
        assert dec.decorate("", "wf-a") == ""

    def test_empty_workflow_returns_empty(self):
        dec = AgentWorkflowDecorator()
        assert dec.decorate("agent-1", "") == ""


# ======================================================================
# TestGet
# ======================================================================

class TestGet:
    def test_get_existing(self):
        dec = AgentWorkflowDecorator()
        rid = dec.decorate("a1", "wf")
        assert dec.get_decoration(rid) is not None

    def test_get_missing_returns_none(self):
        dec = AgentWorkflowDecorator()
        assert dec.get_decoration("awdc-nonexistent") is None

    def test_get_returns_deepcopy(self):
        dec = AgentWorkflowDecorator()
        rid = dec.decorate("a1", "wf", metadata={"x": 1})
        entry1 = dec.get_decoration(rid)
        entry2 = dec.get_decoration(rid)
        assert entry1 is not entry2
        entry1["metadata"]["x"] = 999
        assert dec.get_decoration(rid)["metadata"]["x"] == 1


# ======================================================================
# TestList
# ======================================================================

class TestList:
    def test_list_all(self):
        dec = AgentWorkflowDecorator()
        dec.decorate("a1", "wf1")
        dec.decorate("a2", "wf2")
        assert len(dec.get_decorations()) == 2

    def test_filter_by_agent_id(self):
        dec = AgentWorkflowDecorator()
        dec.decorate("a1", "wf1")
        dec.decorate("a2", "wf2")
        dec.decorate("a1", "wf3")
        result = dec.get_decorations(agent_id="a1")
        assert len(result) == 2
        assert all(e["agent_id"] == "a1" for e in result)

    def test_newest_first(self):
        dec = AgentWorkflowDecorator()
        r1 = dec.decorate("a1", "wf1")
        r2 = dec.decorate("a1", "wf2")
        result = dec.get_decorations()
        assert result[0]["record_id"] == r2
        assert result[1]["record_id"] == r1


# ======================================================================
# TestCount
# ======================================================================

class TestCount:
    def test_total_count(self):
        dec = AgentWorkflowDecorator()
        dec.decorate("a1", "wf1")
        dec.decorate("a2", "wf2")
        assert dec.get_decoration_count() == 2

    def test_count_by_agent(self):
        dec = AgentWorkflowDecorator()
        dec.decorate("a1", "wf1")
        dec.decorate("a2", "wf2")
        dec.decorate("a1", "wf3")
        assert dec.get_decoration_count(agent_id="a1") == 2
        assert dec.get_decoration_count(agent_id="a2") == 1


# ======================================================================
# TestStats
# ======================================================================

class TestStats:
    def test_stats_keys_and_values(self):
        dec = AgentWorkflowDecorator()
        stats = dec.get_stats()
        assert "total_decorations" in stats
        assert "unique_agents" in stats
        dec.decorate("a1", "wf1")
        dec.decorate("a2", "wf2")
        dec.decorate("a1", "wf3")
        stats = dec.get_stats()
        assert stats["total_decorations"] == 3
        assert stats["unique_agents"] == 2


# ======================================================================
# TestCallbacks
# ======================================================================

class TestCallbacks:
    def test_on_change_called(self):
        events = []
        dec = AgentWorkflowDecorator(_on_change=lambda action, data: events.append((action, data)))
        dec.decorate("a1", "wf1")
        assert len(events) == 1
        assert events[0][0] == "decorate"
        assert "record_id" in events[0][1]

    def test_state_callback(self):
        events = []
        dec = AgentWorkflowDecorator()
        dec._state.callbacks["my_cb"] = lambda action, data: events.append(action)
        dec.decorate("a1", "wf1")
        assert "decorate" in events


# ======================================================================
# TestPrune
# ======================================================================

class TestPrune:
    def test_prune_keeps_max(self):
        dec = AgentWorkflowDecorator()
        dec.MAX_ENTRIES = 5
        for i in range(7):
            dec.decorate(f"agent-{i}", f"wf-{i}")
        assert len(dec._state.entries) == 5

    def test_prune_removes_oldest(self):
        dec = AgentWorkflowDecorator()
        dec.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(dec.decorate(f"agent-{i}", f"wf-{i}"))
        # oldest two should be gone
        assert dec.get_decoration(ids[0]) is None
        assert dec.get_decoration(ids[1]) is None
        assert dec.get_decoration(ids[6]) is not None


# ======================================================================
# TestReset
# ======================================================================

class TestReset:
    def test_reset_clears_entries(self):
        dec = AgentWorkflowDecorator()
        dec.decorate("a1", "wf1")
        dec.reset()
        assert dec.get_decoration_count() == 0

    def test_reset_clears_on_change(self):
        dec = AgentWorkflowDecorator(_on_change=lambda a, d: None)
        dec.reset()
        assert dec._on_change is None
