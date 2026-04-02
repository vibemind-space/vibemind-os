import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_demotioner import AgentWorkflowDemotioner

class TestBasic:
    def test_returns_id(self):
        assert AgentWorkflowDemotioner().demote("a1", "wf1").startswith("awdm-")
    def test_fields(self):
        s = AgentWorkflowDemotioner(); rid = s.demote("a1", "wf1", reason="underperform")
        e = s.get_demotion(rid)
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["reason"] == "underperform"
    def test_default_reason(self):
        s = AgentWorkflowDemotioner(); rid = s.demote("a1", "wf1")
        assert s.get_demotion(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = AgentWorkflowDemotioner(); m = {"x": [1]}
        rid = s.demote("a1", "wf1", metadata=m); m["x"].append(2)
        assert s.get_demotion(rid)["metadata"] == {"x": [1]}
    def test_empty_agent(self):
        assert AgentWorkflowDemotioner().demote("", "wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowDemotioner().demote("a1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentWorkflowDemotioner(); rid = s.demote("a1", "wf1")
        assert s.get_demotion(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowDemotioner().get_demotion("nope") is None
    def test_copy(self):
        s = AgentWorkflowDemotioner(); rid = s.demote("a1", "wf1")
        assert s.get_demotion(rid) is not s.get_demotion(rid)
class TestList:
    def test_all(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.demote("a2", "wf2")
        assert len(s.get_demotions()) == 2
    def test_filter(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.demote("a2", "wf2")
        assert len(s.get_demotions("a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.demote("a1", "wf2")
        assert s.get_demotions("a1")[0]["_seq"] > s.get_demotions("a1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.demote("a2", "wf2")
        assert s.get_demotion_count() == 2
    def test_filtered(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.demote("a2", "wf2")
        assert s.get_demotion_count("a1") == 1
class TestStats:
    def test_data(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.demote("a2", "wf2")
        assert s.get_stats()["total_demotions"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowDemotioner(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.demote("a1", "wf1")
        assert "demoted" in calls
    def test_remove_true(self):
        s = AgentWorkflowDemotioner(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowDemotioner().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentWorkflowDemotioner(); s.MAX_ENTRIES = 5
        for i in range(8): s.demote("a1", f"wf{i}")
        assert s.get_demotion_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.reset()
        assert s.get_demotion_count() == 0
    def test_seq(self):
        s = AgentWorkflowDemotioner(); s.demote("a1", "wf1"); s.reset()
        assert s._state._seq == 0
