"""Tests for AgentWorkflowFinalizer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_finalizer import AgentWorkflowFinalizer

class TestIdGeneration:
    def test_prefix(self):
        f = AgentWorkflowFinalizer()
        assert f.finalize("a1", "wf1").startswith("awfn-")
    def test_unique(self):
        f = AgentWorkflowFinalizer()
        ids = {f.finalize("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestFinalizeBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowFinalizer().finalize("a1", "wf1")) > 0
    def test_stores_fields(self):
        f = AgentWorkflowFinalizer()
        rid = f.finalize("a1", "wf1", status="done")
        e = f.get_finalization(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["status"] == "done"
    def test_with_metadata(self):
        f = AgentWorkflowFinalizer()
        rid = f.finalize("a1", "wf1", metadata={"x": 1})
        assert f.get_finalization(rid)["metadata"]["x"] == 1

class TestGetFinalization:
    def test_found(self):
        f = AgentWorkflowFinalizer()
        rid = f.finalize("a1", "wf1")
        assert f.get_finalization(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowFinalizer().get_finalization("xxx") is None
    def test_returns_copy(self):
        f = AgentWorkflowFinalizer()
        rid = f.finalize("a1", "wf1")
        assert f.get_finalization(rid) is not f.get_finalization(rid)

class TestGetFinalizations:
    def test_all(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.finalize("a2", "wf2")
        assert len(f.get_finalizations()) == 2
    def test_filter(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.finalize("a2", "wf2")
        assert len(f.get_finalizations(agent_id="a1")) == 1
    def test_newest_first(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.finalize("a1", "wf2")
        assert f.get_finalizations(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        f = AgentWorkflowFinalizer()
        for i in range(10): f.finalize("a1", f"wf{i}")
        assert len(f.get_finalizations(limit=3)) == 3

class TestGetFinalizationCount:
    def test_total(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.finalize("a2", "wf2")
        assert f.get_finalization_count() == 2
    def test_filtered(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.finalize("a2", "wf2")
        assert f.get_finalization_count(agent_id="a1") == 1

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowFinalizer().get_stats()["total_finalizations"] == 0
    def test_with_data(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.finalize("a2", "wf2")
        st = f.get_stats()
        assert st["total_finalizations"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        f = AgentWorkflowFinalizer()
        evts = []
        f.on_change = lambda a, d: evts.append(a)
        f.finalize("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        f = AgentWorkflowFinalizer()
        f._callbacks["cb1"] = lambda a, d: None
        assert f.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowFinalizer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        f = AgentWorkflowFinalizer()
        f.MAX_ENTRIES = 5
        for i in range(8): f.finalize("a1", f"wf{i}")
        assert f.get_finalization_count() < 8

class TestReset:
    def test_clears(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.reset()
        assert f.get_finalization_count() == 0
    def test_resets_seq(self):
        f = AgentWorkflowFinalizer()
        f.finalize("a1", "wf1"); f.reset()
        assert f._state._seq == 0
