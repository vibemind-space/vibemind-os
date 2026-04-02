import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_deprioritizer import AgentWorkflowDeprioritizer

class TestBasic:
    def test_returns_id(self):
        assert AgentWorkflowDeprioritizer().deprioritize("a1", "wf1").startswith("awdp-")
    def test_fields(self):
        s = AgentWorkflowDeprioritizer(); rid = s.deprioritize("a1", "wf1", reason="low")
        e = s.get_deprioritization(rid)
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["reason"] == "low"
    def test_default_reason(self):
        s = AgentWorkflowDeprioritizer(); rid = s.deprioritize("a1", "wf1")
        assert s.get_deprioritization(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = AgentWorkflowDeprioritizer(); m = {"x": [1]}
        rid = s.deprioritize("a1", "wf1", metadata=m); m["x"].append(2)
        assert s.get_deprioritization(rid)["metadata"] == {"x": [1]}
    def test_empty_agent(self):
        assert AgentWorkflowDeprioritizer().deprioritize("", "wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowDeprioritizer().deprioritize("a1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentWorkflowDeprioritizer(); rid = s.deprioritize("a1", "wf1")
        assert s.get_deprioritization(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowDeprioritizer().get_deprioritization("nope") is None
    def test_copy(self):
        s = AgentWorkflowDeprioritizer(); rid = s.deprioritize("a1", "wf1")
        assert s.get_deprioritization(rid) is not s.get_deprioritization(rid)
class TestList:
    def test_all(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.deprioritize("a2", "wf2")
        assert len(s.get_deprioritizations()) == 2
    def test_filter(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.deprioritize("a2", "wf2")
        assert len(s.get_deprioritizations("a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.deprioritize("a1", "wf2")
        assert s.get_deprioritizations("a1")[0]["_seq"] > s.get_deprioritizations("a1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.deprioritize("a2", "wf2")
        assert s.get_deprioritization_count() == 2
    def test_filtered(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.deprioritize("a2", "wf2")
        assert s.get_deprioritization_count("a1") == 1
class TestStats:
    def test_data(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.deprioritize("a2", "wf2")
        assert s.get_stats()["total_deprioritizations"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowDeprioritizer(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.deprioritize("a1", "wf1")
        assert "deprioritized" in calls
    def test_remove_true(self):
        s = AgentWorkflowDeprioritizer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowDeprioritizer().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentWorkflowDeprioritizer(); s.MAX_ENTRIES = 5
        for i in range(8): s.deprioritize("a1", f"wf{i}")
        assert s.get_deprioritization_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.reset()
        assert s.get_deprioritization_count() == 0
    def test_seq(self):
        s = AgentWorkflowDeprioritizer(); s.deprioritize("a1", "wf1"); s.reset()
        assert s._state._seq == 0
