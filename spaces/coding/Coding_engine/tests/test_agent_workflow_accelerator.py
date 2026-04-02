from __future__ import annotations

import copy
import time
from unittest.mock import MagicMock

import pytest

from src.services.agent_workflow_accelerator import (
    AgentWorkflowAccelerator,
    AgentWorkflowAcceleratorState,
)


# ======================================================================
# TestBasic
# ======================================================================
class TestBasic:
    def test_prefix(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("a1", "wf1")
        assert rid.startswith("awac-")

    def test_accelerate_returns_id(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("a1", "wf1")
        assert isinstance(rid, str)
        assert len(rid) > len(AgentWorkflowAccelerator.PREFIX)

    def test_fields_stored(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("agent-x", "build", factor=3.0, metadata={"k": "v"})
        entry = acc.get_acceleration(rid)
        assert entry["agent_id"] == "agent-x"
        assert entry["workflow_name"] == "build"
        assert entry["factor"] == 3.0
        assert entry["metadata"] == {"k": "v"}
        assert "created_at" in entry
        assert "_seq" in entry

    def test_default_factor(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("a1", "wf1")
        entry = acc.get_acceleration(rid)
        assert entry["factor"] == 2.0

    def test_deepcopy_returned(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("a1", "wf1", metadata={"x": [1, 2]})
        entry = acc.get_acceleration(rid)
        entry["metadata"]["x"].append(3)
        original = acc.get_acceleration(rid)
        assert original["metadata"]["x"] == [1, 2]

    def test_empty_agent_id_returns_empty(self):
        acc = AgentWorkflowAccelerator()
        assert acc.accelerate("", "wf1") == ""

    def test_empty_workflow_returns_empty(self):
        acc = AgentWorkflowAccelerator()
        assert acc.accelerate("a1", "") == ""

    def test_metadata_defaults_to_empty_dict(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("a1", "wf1")
        entry = acc.get_acceleration(rid)
        assert entry["metadata"] == {}


# ======================================================================
# TestGet
# ======================================================================
class TestGet:
    def test_get_existing(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("a1", "wf1")
        entry = acc.get_acceleration(rid)
        assert entry is not None
        assert entry["record_id"] == rid

    def test_get_missing_returns_none(self):
        acc = AgentWorkflowAccelerator()
        assert acc.get_acceleration("nonexistent") is None

    def test_get_returns_deepcopy(self):
        acc = AgentWorkflowAccelerator()
        rid = acc.accelerate("a1", "wf1")
        e1 = acc.get_acceleration(rid)
        e2 = acc.get_acceleration(rid)
        assert e1 == e2
        assert e1 is not e2


# ======================================================================
# TestList
# ======================================================================
class TestList:
    def test_list_all(self):
        acc = AgentWorkflowAccelerator()
        acc.accelerate("a1", "wf1")
        acc.accelerate("a2", "wf2")
        results = acc.get_accelerations()
        assert len(results) == 2

    def test_filter_by_agent_id(self):
        acc = AgentWorkflowAccelerator()
        acc.accelerate("a1", "wf1")
        acc.accelerate("a2", "wf2")
        acc.accelerate("a1", "wf3")
        results = acc.get_accelerations(agent_id="a1")
        assert len(results) == 2
        assert all(e["agent_id"] == "a1" for e in results)

    def test_newest_first(self):
        acc = AgentWorkflowAccelerator()
        r1 = acc.accelerate("a1", "wf1")
        r2 = acc.accelerate("a1", "wf2")
        r3 = acc.accelerate("a1", "wf3")
        results = acc.get_accelerations(agent_id="a1")
        assert results[0]["record_id"] == r3
        assert results[-1]["record_id"] == r1

    def test_limit(self):
        acc = AgentWorkflowAccelerator()
        for i in range(10):
            acc.accelerate("a1", f"wf{i}")
        results = acc.get_accelerations(limit=3)
        assert len(results) == 3


# ======================================================================
# TestCount
# ======================================================================
class TestCount:
    def test_count_all(self):
        acc = AgentWorkflowAccelerator()
        acc.accelerate("a1", "wf1")
        acc.accelerate("a2", "wf2")
        assert acc.get_acceleration_count() == 2

    def test_count_by_agent(self):
        acc = AgentWorkflowAccelerator()
        acc.accelerate("a1", "wf1")
        acc.accelerate("a2", "wf2")
        acc.accelerate("a1", "wf3")
        assert acc.get_acceleration_count(agent_id="a1") == 2
        assert acc.get_acceleration_count(agent_id="a2") == 1

    def test_count_empty(self):
        acc = AgentWorkflowAccelerator()
        assert acc.get_acceleration_count() == 0


# ======================================================================
# TestStats
# ======================================================================
class TestStats:
    def test_stats_keys(self):
        acc = AgentWorkflowAccelerator()
        stats = acc.get_stats()
        assert "total_accelerations" in stats
        assert "unique_agents" in stats

    def test_stats_values(self):
        acc = AgentWorkflowAccelerator()
        acc.accelerate("a1", "wf1")
        acc.accelerate("a2", "wf2")
        acc.accelerate("a1", "wf3")
        stats = acc.get_stats()
        assert stats["total_accelerations"] == 3
        assert stats["unique_agents"] == 2

    def test_stats_empty(self):
        acc = AgentWorkflowAccelerator()
        stats = acc.get_stats()
        assert stats["total_accelerations"] == 0
        assert stats["unique_agents"] == 0


# ======================================================================
# TestCallbacks
# ======================================================================
class TestCallbacks:
    def test_on_change_called(self):
        captured = []
        acc = AgentWorkflowAccelerator(_on_change=lambda action, data: captured.append((action, data)))
        acc.accelerate("a1", "wf1")
        assert len(captured) == 1
        assert captured[0][0] == "accelerate"
        assert captured[0][1]["action"] == "accelerate"

    def test_state_callback(self):
        captured = []
        acc = AgentWorkflowAccelerator()
        acc._state.callbacks["cb1"] = lambda action, data: captured.append((action, data))
        acc.accelerate("a1", "wf1")
        assert len(captured) == 1
        assert captured[0][0] == "accelerate"

    def test_both_callbacks_fire(self):
        on_change_calls = []
        state_cb_calls = []
        acc = AgentWorkflowAccelerator(
            _on_change=lambda action, data: on_change_calls.append(action),
        )
        acc._state.callbacks["cb1"] = lambda action, data: state_cb_calls.append(action)
        acc.accelerate("a1", "wf1")
        assert len(on_change_calls) == 1
        assert len(state_cb_calls) == 1


# ======================================================================
# TestPrune
# ======================================================================
class TestPrune:
    def test_prune_keeps_max(self):
        acc = AgentWorkflowAccelerator()
        acc.MAX_ENTRIES = 5
        for i in range(7):
            acc.accelerate(f"a{i}", f"wf{i}")
        assert acc.get_acceleration_count() == 5

    def test_prune_removes_oldest(self):
        acc = AgentWorkflowAccelerator()
        acc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            rid = acc.accelerate(f"a{i}", f"wf{i}")
            ids.append(rid)
        # oldest two should be gone
        assert acc.get_acceleration(ids[0]) is None
        assert acc.get_acceleration(ids[1]) is None
        # newest should remain
        assert acc.get_acceleration(ids[6]) is not None


# ======================================================================
# TestReset
# ======================================================================
class TestReset:
    def test_reset_clears_entries(self):
        acc = AgentWorkflowAccelerator()
        acc.accelerate("a1", "wf1")
        acc.reset()
        assert acc.get_acceleration_count() == 0

    def test_reset_clears_on_change(self):
        acc = AgentWorkflowAccelerator(_on_change=lambda a, d: None)
        acc.reset()
        assert acc._on_change is None

    def test_reset_clears_callbacks(self):
        acc = AgentWorkflowAccelerator()
        acc._state.callbacks["cb1"] = lambda a, d: None
        acc.reset()
        assert len(acc._state.callbacks) == 0

    def test_usable_after_reset(self):
        acc = AgentWorkflowAccelerator()
        acc.accelerate("a1", "wf1")
        acc.reset()
        rid = acc.accelerate("a2", "wf2")
        assert rid.startswith("awac-")
        assert acc.get_acceleration_count() == 1
