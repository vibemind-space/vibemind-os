"""Tests for AgentWorkflowBrancher service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_brancher import AgentWorkflowBrancher

class TestIdGeneration:
    def test_prefix(self):
        b = AgentWorkflowBrancher()
        assert b.branch("a1", "wf1", "br1").startswith("awbr-")
    def test_unique(self):
        b = AgentWorkflowBrancher()
        ids = {b.branch("a1", "wf1", f"br{i}") for i in range(20)}
        assert len(ids) == 20

class TestBranchBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowBrancher().branch("a1", "wf1", "br1")) > 0
    def test_stores_fields(self):
        b = AgentWorkflowBrancher()
        rid = b.branch("a1", "wf1", "br1", condition="x>5")
        e = b.get_branch(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["branch_name"] == "br1"
        assert e["condition"] == "x>5"
    def test_with_metadata(self):
        b = AgentWorkflowBrancher()
        rid = b.branch("a1", "wf1", "br1", metadata={"x": 1})
        assert b.get_branch(rid)["metadata"]["x"] == 1

class TestGetBranch:
    def test_found(self):
        b = AgentWorkflowBrancher()
        rid = b.branch("a1", "wf1", "br1")
        assert b.get_branch(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowBrancher().get_branch("xxx") is None
    def test_returns_copy(self):
        b = AgentWorkflowBrancher()
        rid = b.branch("a1", "wf1", "br1")
        assert b.get_branch(rid) is not b.get_branch(rid)

class TestGetBranches:
    def test_all(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.branch("a2", "wf2", "br2")
        assert len(b.get_branches()) == 2
    def test_filter(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.branch("a2", "wf2", "br2")
        assert len(b.get_branches(agent_id="a1")) == 1
    def test_newest_first(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.branch("a1", "wf2", "br2")
        assert b.get_branches(agent_id="a1")[0]["branch_name"] == "br2"
    def test_limit(self):
        b = AgentWorkflowBrancher()
        for i in range(10): b.branch("a1", f"wf{i}", f"br{i}")
        assert len(b.get_branches(limit=3)) == 3

class TestGetBranchCount:
    def test_total(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.branch("a2", "wf2", "br2")
        assert b.get_branch_count() == 2
    def test_filtered(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.branch("a2", "wf2", "br2")
        assert b.get_branch_count(agent_id="a1") == 1

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowBrancher().get_stats()["total_branches"] == 0
    def test_with_data(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.branch("a2", "wf2", "br2")
        st = b.get_stats()
        assert st["total_branches"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        b = AgentWorkflowBrancher()
        evts = []
        b.on_change = lambda a, d: evts.append(a)
        b.branch("a1", "wf1", "br1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        b = AgentWorkflowBrancher()
        b._state.callbacks["cb1"] = lambda a, d: None
        assert b.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowBrancher().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        b = AgentWorkflowBrancher()
        b.MAX_ENTRIES = 5
        for i in range(8): b.branch("a1", f"wf{i}", f"br{i}")
        assert b.get_branch_count() < 8

class TestReset:
    def test_clears(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.reset()
        assert b.get_branch_count() == 0
    def test_resets_seq(self):
        b = AgentWorkflowBrancher()
        b.branch("a1", "wf1", "br1"); b.reset()
        assert b._state._seq == 0
