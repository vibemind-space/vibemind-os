"""Tests for AgentWorkflowForker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_forker import AgentWorkflowForker

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowForker()
        assert s.fork("a1", "wf1", "br1").startswith("awfk-")
    def test_unique(self):
        s = AgentWorkflowForker()
        ids = {s.fork("a1", f"wf{i}", f"br{i}") for i in range(20)}
        assert len(ids) == 20

class TestForkBasic:
    def test_returns_id(self):
        s = AgentWorkflowForker()
        assert len(s.fork("a1", "wf1", "br1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowForker()
        rid = s.fork("a1", "wf1", "br1")
        e = s.get_fork(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["branch_name"] == "br1"
    def test_with_metadata(self):
        s = AgentWorkflowForker()
        rid = s.fork("a1", "wf1", "br1", metadata={"x": 1})
        assert s.get_fork(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowForker()
        m = {"a": [1]}
        rid = s.fork("a1", "wf1", "br1", metadata=m)
        m["a"].append(2)
        assert s.get_fork(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowForker()
        before = time.time()
        rid = s.fork("a1", "wf1", "br1")
        assert s.get_fork(rid)["created_at"] >= before
    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowForker().fork("", "wf1", "br1") == ""
    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowForker().fork("a1", "", "br1") == ""
    def test_empty_branch_returns_empty(self):
        assert AgentWorkflowForker().fork("a1", "wf1", "") == ""

class TestGetFork:
    def test_found(self):
        s = AgentWorkflowForker()
        rid = s.fork("a1", "wf1", "br1")
        assert s.get_fork(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowForker().get_fork("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowForker()
        rid = s.fork("a1", "wf1", "br1")
        assert s.get_fork(rid) is not s.get_fork(rid)

class TestGetForks:
    def test_all(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.fork("a2", "wf2", "br2")
        assert len(s.get_forks()) == 2
    def test_filter(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.fork("a2", "wf2", "br2")
        assert len(s.get_forks(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.fork("a1", "wf2", "br2")
        assert s.get_forks(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowForker()
        for i in range(10): s.fork("a1", f"wf{i}", f"br{i}")
        assert len(s.get_forks(limit=3)) == 3

class TestGetForkCount:
    def test_total(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.fork("a2", "wf2", "br2")
        assert s.get_fork_count() == 2
    def test_filtered(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.fork("a2", "wf2", "br2")
        assert s.get_fork_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowForker().get_fork_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowForker().get_stats()["total_forks"] == 0
    def test_with_data(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.fork("a2", "wf2", "br2")
        st = s.get_stats()
        assert st["total_forks"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowForker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.fork("a1", "wf1", "br1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowForker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowForker().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowForker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.fork("a1", f"wf{i}", f"br{i}")
        assert s.get_fork_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.reset()
        assert s.get_fork_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowForker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowForker()
        s.fork("a1", "wf1", "br1"); s.reset()
        assert s._state._seq == 0
