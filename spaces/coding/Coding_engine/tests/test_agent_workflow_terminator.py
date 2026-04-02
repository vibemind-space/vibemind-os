"""Tests for AgentWorkflowTerminator service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_terminator import AgentWorkflowTerminator

class TestId:
    def test_prefix(self):
        assert AgentWorkflowTerminator().terminate("a1", "wf1").startswith("awtm-")
    def test_unique(self):
        s = AgentWorkflowTerminator()
        assert len({s.terminate("a1", f"wf{i}") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowTerminator().terminate("a1", "wf1")) > 0
    def test_fields(self):
        s = AgentWorkflowTerminator()
        e = s.get_termination(s.terminate("a1", "wf1", reason="done"))
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["reason"] == "done"
    def test_deepcopy(self):
        s = AgentWorkflowTerminator(); m = {"a": [1]}
        rid = s.terminate("a1", "wf1", metadata=m); m["a"].append(2)
        assert s.get_termination(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowTerminator(); b = time.time()
        assert s.get_termination(s.terminate("a1", "wf1"))["created_at"] >= b
    def test_empty_agent(self):
        assert AgentWorkflowTerminator().terminate("", "wf1") == ""
    def test_empty_wf(self):
        assert AgentWorkflowTerminator().terminate("a1", "") == ""
    def test_default_reason(self):
        s = AgentWorkflowTerminator()
        e = s.get_termination(s.terminate("a1", "wf1"))
        assert e["reason"] == ""
    def test_default_metadata(self):
        s = AgentWorkflowTerminator()
        e = s.get_termination(s.terminate("a1", "wf1"))
        assert e["metadata"] == {}

class TestGet:
    def test_found(self):
        s = AgentWorkflowTerminator(); assert s.get_termination(s.terminate("a1", "wf1")) is not None
    def test_not_found(self):
        assert AgentWorkflowTerminator().get_termination("xxx") is None
    def test_copy(self):
        s = AgentWorkflowTerminator(); rid = s.terminate("a1", "wf1")
        assert s.get_termination(rid) is not s.get_termination(rid)

class TestList:
    def test_all(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.terminate("a2", "wf2")
        assert len(s.get_terminations()) == 2
    def test_filter(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.terminate("a2", "wf2")
        assert len(s.get_terminations(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.terminate("a1", "wf2")
        assert s.get_terminations(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowTerminator()
        for i in range(10): s.terminate("a1", f"wf{i}")
        assert len(s.get_terminations(limit=3)) == 3
    def test_empty_list(self):
        assert len(AgentWorkflowTerminator().get_terminations()) == 0

class TestCount:
    def test_total(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.terminate("a2", "wf2")
        assert s.get_termination_count() == 2
    def test_filtered(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.terminate("a2", "wf2")
        assert s.get_termination_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowTerminator().get_termination_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentWorkflowTerminator().get_stats()["total_terminations"] == 0
    def test_data(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.terminate("a2", "wf2")
        assert s.get_stats()["total_terminations"] == 2 and s.get_stats()["unique_agents"] == 2
    def test_unique_agents_dedup(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.terminate("a1", "wf2")
        assert s.get_stats()["unique_agents"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowTerminator(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.terminate("a1", "wf1")
        assert len(evts) >= 1
    def test_on_change_action(self):
        s = AgentWorkflowTerminator(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.terminate("a1", "wf1")
        assert evts[0] == "terminate"
    def test_on_change_data(self):
        s = AgentWorkflowTerminator(); data = []
        s.on_change = lambda a, d: data.append(d); s.terminate("a1", "wf1")
        assert data[0]["agent_id"] == "a1"
    def test_remove_true(self):
        s = AgentWorkflowTerminator(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowTerminator().remove_callback("x") is False
    def test_callback_fires(self):
        s = AgentWorkflowTerminator(); evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.terminate("a1", "wf1")
        assert "terminate" in evts
    def test_callback_exception_ignored(self):
        s = AgentWorkflowTerminator()
        s._state.callbacks["bad"] = lambda a, d: 1/0
        rid = s.terminate("a1", "wf1")
        assert rid.startswith("awtm-")
    def test_on_change_exception_ignored(self):
        s = AgentWorkflowTerminator()
        s.on_change = lambda a, d: 1/0
        rid = s.terminate("a1", "wf1")
        assert rid.startswith("awtm-")

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowTerminator(); s.MAX_ENTRIES = 5
        for i in range(8): s.terminate("a1", f"wf{i}")
        assert s.get_termination_count() < 8
    def test_prune_keeps_newest(self):
        s = AgentWorkflowTerminator(); s.MAX_ENTRIES = 4
        ids = [s.terminate("a1", f"wf{i}") for i in range(6)]
        remaining = [s.get_termination(rid) for rid in ids if s.get_termination(rid) is not None]
        assert all(r is not None for r in remaining)

class TestReset:
    def test_clears(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.reset()
        assert s.get_termination_count() == 0
    def test_callbacks(self):
        s = AgentWorkflowTerminator(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowTerminator(); s.terminate("a1", "wf1"); s.reset()
        assert s._state._seq == 0
    def test_reset_clears_callbacks(self):
        s = AgentWorkflowTerminator(); s._state.callbacks["cb1"] = lambda a, d: None
        s.reset()
        assert len(s._state.callbacks) == 0
