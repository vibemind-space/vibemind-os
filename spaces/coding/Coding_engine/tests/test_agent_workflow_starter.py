"""Tests for AgentWorkflowStarter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_starter import AgentWorkflowStarter

class TestId:
    def test_prefix(self):
        assert AgentWorkflowStarter().start_workflow("a1", "wf1").startswith("awst-")
    def test_unique(self):
        s = AgentWorkflowStarter()
        assert len({s.start_workflow("a1", f"wf{i}") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowStarter().start_workflow("a1", "wf1")) > 0
    def test_fields(self):
        s = AgentWorkflowStarter()
        e = s.get_start(s.start_workflow("a1", "wf1", config="cfg"))
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["config"] == "cfg"
    def test_deepcopy(self):
        s = AgentWorkflowStarter(); m = {"a": [1]}
        rid = s.start_workflow("a1", "wf1", metadata=m); m["a"].append(2)
        assert s.get_start(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowStarter(); b = time.time()
        assert s.get_start(s.start_workflow("a1", "wf1"))["created_at"] >= b
    def test_empty_agent(self):
        assert AgentWorkflowStarter().start_workflow("", "wf1") == ""
    def test_empty_wf(self):
        assert AgentWorkflowStarter().start_workflow("a1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentWorkflowStarter(); assert s.get_start(s.start_workflow("a1", "wf1")) is not None
    def test_not_found(self):
        assert AgentWorkflowStarter().get_start("xxx") is None
    def test_copy(self):
        s = AgentWorkflowStarter(); rid = s.start_workflow("a1", "wf1")
        assert s.get_start(rid) is not s.get_start(rid)

class TestList:
    def test_all(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.start_workflow("a2", "wf2")
        assert len(s.get_starts()) == 2
    def test_filter(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.start_workflow("a2", "wf2")
        assert len(s.get_starts(agent_id="a1")) == 1
    def test_newest(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.start_workflow("a1", "wf2")
        assert s.get_starts(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowStarter()
        for i in range(10): s.start_workflow("a1", f"wf{i}")
        assert len(s.get_starts(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.start_workflow("a2", "wf2")
        assert s.get_start_count() == 2
    def test_filtered(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.start_workflow("a2", "wf2")
        assert s.get_start_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowStarter().get_start_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentWorkflowStarter().get_stats()["total_starts"] == 0
    def test_data(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.start_workflow("a2", "wf2")
        assert s.get_stats()["total_starts"] == 2 and s.get_stats()["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowStarter(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.start_workflow("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = AgentWorkflowStarter(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowStarter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowStarter(); s.MAX_ENTRIES = 5
        for i in range(8): s.start_workflow("a1", f"wf{i}")
        assert s.get_start_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.reset()
        assert s.get_start_count() == 0
    def test_callbacks(self):
        s = AgentWorkflowStarter(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowStarter(); s.start_workflow("a1", "wf1"); s.reset()
        assert s._state._seq == 0
