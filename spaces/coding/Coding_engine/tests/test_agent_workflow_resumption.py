"""Tests for AgentWorkflowResumption service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_resumption import AgentWorkflowResumption

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowResumption()
        assert s.resume_workflow("a1", "wf1").startswith("awrs-")
    def test_unique(self):
        s = AgentWorkflowResumption()
        ids = {s.resume_workflow("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestResumeWorkflowBasic:
    def test_returns_id(self):
        s = AgentWorkflowResumption()
        assert len(s.resume_workflow("a1", "wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowResumption()
        rid = s.resume_workflow("a1", "wf1", checkpoint="cp1")
        e = s.get_resumption(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["checkpoint"] == "cp1"
    def test_with_metadata(self):
        s = AgentWorkflowResumption()
        rid = s.resume_workflow("a1", "wf1", metadata={"x": 1})
        assert s.get_resumption(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowResumption()
        m = {"a": [1]}
        rid = s.resume_workflow("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_resumption(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowResumption()
        before = time.time()
        rid = s.resume_workflow("a1", "wf1")
        assert s.get_resumption(rid)["created_at"] >= before
    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowResumption().resume_workflow("", "wf1") == ""
    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowResumption().resume_workflow("a1", "") == ""

class TestGetResumption:
    def test_found(self):
        s = AgentWorkflowResumption()
        rid = s.resume_workflow("a1", "wf1")
        assert s.get_resumption(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowResumption().get_resumption("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowResumption()
        rid = s.resume_workflow("a1", "wf1")
        assert s.get_resumption(rid) is not s.get_resumption(rid)

class TestGetResumptions:
    def test_all(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert len(s.get_resumptions()) == 2
    def test_filter(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert len(s.get_resumptions(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.resume_workflow("a1", "wf2")
        assert s.get_resumptions(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowResumption()
        for i in range(10): s.resume_workflow("a1", f"wf{i}")
        assert len(s.get_resumptions(limit=3)) == 3

class TestGetResumptionCount:
    def test_total(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert s.get_resumption_count() == 2
    def test_filtered(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert s.get_resumption_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowResumption().get_resumption_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowResumption().get_stats()["total_resumptions"] == 0
    def test_with_data(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        st = s.get_stats()
        assert st["total_resumptions"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowResumption()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.resume_workflow("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowResumption()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowResumption().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowResumption()
        s.MAX_ENTRIES = 5
        for i in range(8): s.resume_workflow("a1", f"wf{i}")
        assert s.get_resumption_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.reset()
        assert s.get_resumption_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowResumption()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowResumption()
        s.resume_workflow("a1", "wf1"); s.reset()
        assert s._state._seq == 0
