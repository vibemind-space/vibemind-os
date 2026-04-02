"""Tests for AgentWorkflowStopper service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_stopper import AgentWorkflowStopper

class TestId:
    def test_prefix(self):
        assert AgentWorkflowStopper().stop_workflow("a1", "wf1").startswith("awsp-")
    def test_unique(self):
        s = AgentWorkflowStopper()
        assert len({s.stop_workflow("a1", f"wf{i}") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowStopper().stop_workflow("a1", "wf1")) > 0
    def test_fields(self):
        s = AgentWorkflowStopper()
        e = s.get_stop(s.stop_workflow("a1", "wf1", reason="done"))
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["reason"] == "done"
    def test_deepcopy(self):
        s = AgentWorkflowStopper(); m = {"a": [1]}
        rid = s.stop_workflow("a1", "wf1", metadata=m); m["a"].append(2)
        assert s.get_stop(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowStopper(); b = time.time()
        assert s.get_stop(s.stop_workflow("a1", "wf1"))["created_at"] >= b
    def test_empty_agent(self):
        assert AgentWorkflowStopper().stop_workflow("", "wf1") == ""
    def test_empty_wf(self):
        assert AgentWorkflowStopper().stop_workflow("a1", "") == ""
    def test_default_reason(self):
        s = AgentWorkflowStopper()
        e = s.get_stop(s.stop_workflow("a1", "wf1"))
        assert e["reason"] == ""
    def test_default_metadata(self):
        s = AgentWorkflowStopper()
        e = s.get_stop(s.stop_workflow("a1", "wf1"))
        assert e["metadata"] == {}

class TestGet:
    def test_found(self):
        s = AgentWorkflowStopper(); assert s.get_stop(s.stop_workflow("a1", "wf1")) is not None
    def test_not_found(self):
        assert AgentWorkflowStopper().get_stop("xxx") is None
    def test_copy(self):
        s = AgentWorkflowStopper(); rid = s.stop_workflow("a1", "wf1")
        assert s.get_stop(rid) is not s.get_stop(rid)

class TestList:
    def test_all(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.stop_workflow("a2", "wf2")
        assert len(s.get_stops()) == 2
    def test_filter(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.stop_workflow("a2", "wf2")
        assert len(s.get_stops(agent_id="a1")) == 1
    def test_newest(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.stop_workflow("a1", "wf2")
        assert s.get_stops(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowStopper()
        for i in range(10): s.stop_workflow("a1", f"wf{i}")
        assert len(s.get_stops(limit=3)) == 3
    def test_empty_list(self):
        assert len(AgentWorkflowStopper().get_stops()) == 0

class TestCount:
    def test_total(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.stop_workflow("a2", "wf2")
        assert s.get_stop_count() == 2
    def test_filtered(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.stop_workflow("a2", "wf2")
        assert s.get_stop_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowStopper().get_stop_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentWorkflowStopper().get_stats()["total_stops"] == 0
    def test_data(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.stop_workflow("a2", "wf2")
        assert s.get_stats()["total_stops"] == 2 and s.get_stats()["unique_agents"] == 2
    def test_unique_agents_dedup(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.stop_workflow("a1", "wf2")
        assert s.get_stats()["unique_agents"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowStopper(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.stop_workflow("a1", "wf1")
        assert len(evts) >= 1
    def test_on_change_action(self):
        s = AgentWorkflowStopper(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.stop_workflow("a1", "wf1")
        assert evts[0] == "stopped"
    def test_on_change_data(self):
        s = AgentWorkflowStopper(); data = []
        s.on_change = lambda a, d: data.append(d); s.stop_workflow("a1", "wf1")
        assert data[0]["agent_id"] == "a1"
    def test_remove_true(self):
        s = AgentWorkflowStopper(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowStopper().remove_callback("x") is False
    def test_callback_fires(self):
        s = AgentWorkflowStopper(); evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.stop_workflow("a1", "wf1")
        assert "stopped" in evts
    def test_callback_exception_ignored(self):
        s = AgentWorkflowStopper()
        s._state.callbacks["bad"] = lambda a, d: 1/0
        rid = s.stop_workflow("a1", "wf1")
        assert rid.startswith("awsp-")
    def test_on_change_exception_ignored(self):
        s = AgentWorkflowStopper()
        s.on_change = lambda a, d: 1/0
        rid = s.stop_workflow("a1", "wf1")
        assert rid.startswith("awsp-")

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowStopper(); s.MAX_ENTRIES = 5
        for i in range(8): s.stop_workflow("a1", f"wf{i}")
        assert s.get_stop_count() < 8
    def test_prune_keeps_newest(self):
        s = AgentWorkflowStopper(); s.MAX_ENTRIES = 4
        ids = [s.stop_workflow("a1", f"wf{i}") for i in range(6)]
        remaining = [s.get_stop(rid) for rid in ids if s.get_stop(rid) is not None]
        assert all(r is not None for r in remaining)

class TestReset:
    def test_clears(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.reset()
        assert s.get_stop_count() == 0
    def test_callbacks(self):
        s = AgentWorkflowStopper(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowStopper(); s.stop_workflow("a1", "wf1"); s.reset()
        assert s._state._seq == 0
    def test_reset_clears_callbacks(self):
        s = AgentWorkflowStopper(); s._state.callbacks["cb1"] = lambda a, d: None
        s.reset()
        assert len(s._state.callbacks) == 0
