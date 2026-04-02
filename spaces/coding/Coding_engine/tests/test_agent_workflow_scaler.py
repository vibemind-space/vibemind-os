"""Tests for AgentWorkflowScaler service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_scaler import AgentWorkflowScaler

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowScaler()
        assert s.scale("a1", "wf1").startswith("awsc-")
    def test_unique(self):
        s = AgentWorkflowScaler()
        ids = {s.scale("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestScaleBasic:
    def test_returns_id(self):
        s = AgentWorkflowScaler()
        assert len(s.scale("a1", "wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowScaler()
        rid = s.scale("a1", "wf1", factor=2.5)
        e = s.get_scaling(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["factor"] == 2.5
    def test_default_factor(self):
        s = AgentWorkflowScaler()
        rid = s.scale("a1", "wf1")
        assert s.get_scaling(rid)["factor"] == 1.0
    def test_with_metadata(self):
        s = AgentWorkflowScaler()
        rid = s.scale("a1", "wf1", metadata={"x": 1})
        assert s.get_scaling(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowScaler()
        m = {"a": [1]}
        rid = s.scale("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_scaling(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowScaler()
        before = time.time()
        rid = s.scale("a1", "wf1")
        assert s.get_scaling(rid)["created_at"] >= before
    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowScaler().scale("", "wf1") == ""
    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowScaler().scale("a1", "") == ""

class TestGetScaling:
    def test_found(self):
        s = AgentWorkflowScaler()
        rid = s.scale("a1", "wf1")
        assert s.get_scaling(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowScaler().get_scaling("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowScaler()
        rid = s.scale("a1", "wf1")
        assert s.get_scaling(rid) is not s.get_scaling(rid)

class TestGetScalings:
    def test_all(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.scale("a2", "wf2")
        assert len(s.get_scalings()) == 2
    def test_filter(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.scale("a2", "wf2")
        assert len(s.get_scalings(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.scale("a1", "wf2")
        assert s.get_scalings(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowScaler()
        for i in range(10): s.scale("a1", f"wf{i}")
        assert len(s.get_scalings(limit=3)) == 3

class TestGetScalingCount:
    def test_total(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.scale("a2", "wf2")
        assert s.get_scaling_count() == 2
    def test_filtered(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.scale("a2", "wf2")
        assert s.get_scaling_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowScaler().get_scaling_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowScaler().get_stats()["total_scalings"] == 0
    def test_with_data(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.scale("a2", "wf2")
        st = s.get_stats()
        assert st["total_scalings"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowScaler()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.scale("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowScaler()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowScaler().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowScaler()
        s.MAX_ENTRIES = 5
        for i in range(8): s.scale("a1", f"wf{i}")
        assert s.get_scaling_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.reset()
        assert s.get_scaling_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowScaler()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowScaler()
        s.scale("a1", "wf1"); s.reset()
        assert s._state._seq == 0
