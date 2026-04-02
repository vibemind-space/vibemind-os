import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_resumer import AgentWorkflowResumer

class TestBasic:
    def test_returns_id(self):
        assert AgentWorkflowResumer().resume_workflow("a1", "wf1").startswith("awrs-")
    def test_fields(self):
        s = AgentWorkflowResumer(); rid = s.resume_workflow("a1", "wf1", reason="ready")
        e = s.get_resumption(rid)
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["reason"] == "ready"
    def test_default_reason(self):
        s = AgentWorkflowResumer(); rid = s.resume_workflow("a1", "wf1")
        assert s.get_resumption(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = AgentWorkflowResumer(); m = {"x": [1]}
        rid = s.resume_workflow("a1", "wf1", metadata=m); m["x"].append(2)
        assert s.get_resumption(rid)["metadata"] == {"x": [1]}
    def test_empty_agent(self):
        assert AgentWorkflowResumer().resume_workflow("", "wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowResumer().resume_workflow("a1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentWorkflowResumer(); rid = s.resume_workflow("a1", "wf1")
        assert s.get_resumption(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowResumer().get_resumption("nope") is None
    def test_copy(self):
        s = AgentWorkflowResumer(); rid = s.resume_workflow("a1", "wf1")
        assert s.get_resumption(rid) is not s.get_resumption(rid)
class TestList:
    def test_all(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert len(s.get_resumptions()) == 2
    def test_filter(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert len(s.get_resumptions("a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.resume_workflow("a1", "wf2")
        assert s.get_resumptions("a1")[0]["_seq"] > s.get_resumptions("a1")[1]["_seq"]
    def test_limit(self):
        s = AgentWorkflowResumer()
        for i in range(5): s.resume_workflow("a1", f"wf{i}")
        assert len(s.get_resumptions(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert s.get_resumption_count() == 2
    def test_filtered(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert s.get_resumption_count("a1") == 1
    def test_empty(self):
        assert AgentWorkflowResumer().get_resumption_count() == 0
class TestStats:
    def test_data(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.resume_workflow("a2", "wf2")
        assert s.get_stats()["total_resumptions"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowResumer(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.resume_workflow("a1", "wf1")
        assert "resumed" in calls
    def test_remove_true(self):
        s = AgentWorkflowResumer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowResumer().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentWorkflowResumer(); s.MAX_ENTRIES = 5
        for i in range(8): s.resume_workflow("a1", f"wf{i}")
        assert s.get_resumption_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.reset()
        assert s.get_resumption_count() == 0
    def test_seq(self):
        s = AgentWorkflowResumer(); s.resume_workflow("a1", "wf1"); s.reset()
        assert s._state._seq == 0
