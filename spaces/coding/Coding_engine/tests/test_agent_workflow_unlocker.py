"""Tests for AgentWorkflowUnlocker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_unlocker import AgentWorkflowUnlocker

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowUnlocker()
        assert s.unlock("a1", "wf1").startswith("awul-")
    def test_unique(self):
        s = AgentWorkflowUnlocker()
        ids = {s.unlock("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestUnlockBasic:
    def test_returns_id(self):
        s = AgentWorkflowUnlocker()
        assert len(s.unlock("a1", "wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowUnlocker()
        rid = s.unlock("a1", "wf1", reason="ready")
        e = s.get_unlock(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["reason"] == "ready"
    def test_with_metadata(self):
        s = AgentWorkflowUnlocker()
        rid = s.unlock("a1", "wf1", metadata={"x": 1})
        assert s.get_unlock(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowUnlocker()
        m = {"a": [1]}
        rid = s.unlock("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_unlock(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowUnlocker()
        before = time.time()
        rid = s.unlock("a1", "wf1")
        assert s.get_unlock(rid)["created_at"] >= before
    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowUnlocker().unlock("", "wf1") == ""
    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowUnlocker().unlock("a1", "") == ""

class TestGetUnlock:
    def test_found(self):
        s = AgentWorkflowUnlocker()
        rid = s.unlock("a1", "wf1")
        assert s.get_unlock(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowUnlocker().get_unlock("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowUnlocker()
        rid = s.unlock("a1", "wf1")
        assert s.get_unlock(rid) is not s.get_unlock(rid)

class TestGetUnlocks:
    def test_all(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.unlock("a2", "wf2")
        assert len(s.get_unlocks()) == 2
    def test_filter(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.unlock("a2", "wf2")
        assert len(s.get_unlocks(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.unlock("a1", "wf2")
        assert s.get_unlocks(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowUnlocker()
        for i in range(10): s.unlock("a1", f"wf{i}")
        assert len(s.get_unlocks(limit=3)) == 3

class TestGetUnlockCount:
    def test_total(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.unlock("a2", "wf2")
        assert s.get_unlock_count() == 2
    def test_filtered(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.unlock("a2", "wf2")
        assert s.get_unlock_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowUnlocker().get_unlock_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowUnlocker().get_stats()["total_unlocks"] == 0
    def test_with_data(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.unlock("a2", "wf2")
        st = s.get_stats()
        assert st["total_unlocks"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowUnlocker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.unlock("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowUnlocker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowUnlocker().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowUnlocker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.unlock("a1", f"wf{i}")
        assert s.get_unlock_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.reset()
        assert s.get_unlock_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowUnlocker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowUnlocker()
        s.unlock("a1", "wf1"); s.reset()
        assert s._state._seq == 0
