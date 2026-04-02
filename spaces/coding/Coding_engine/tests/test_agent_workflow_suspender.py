import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_suspender import AgentWorkflowSuspender

class TestBasic:
    def test_returns_id(self):
        assert AgentWorkflowSuspender().suspend("a1", "wf1").startswith("awsu-")
    def test_fields(self):
        s = AgentWorkflowSuspender(); rid = s.suspend("a1", "wf1", reason="pause")
        e = s.get_suspension(rid)
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["reason"] == "pause"
    def test_default_reason(self):
        s = AgentWorkflowSuspender(); rid = s.suspend("a1", "wf1")
        assert s.get_suspension(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = AgentWorkflowSuspender(); m = {"x": [1]}
        rid = s.suspend("a1", "wf1", metadata=m); m["x"].append(2)
        assert s.get_suspension(rid)["metadata"] == {"x": [1]}
    def test_empty_agent(self):
        assert AgentWorkflowSuspender().suspend("", "wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowSuspender().suspend("a1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentWorkflowSuspender(); rid = s.suspend("a1", "wf1")
        assert s.get_suspension(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowSuspender().get_suspension("nope") is None
    def test_copy(self):
        s = AgentWorkflowSuspender(); rid = s.suspend("a1", "wf1")
        assert s.get_suspension(rid) is not s.get_suspension(rid)
class TestList:
    def test_all(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.suspend("a2", "wf2")
        assert len(s.get_suspensions()) == 2
    def test_filter(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.suspend("a2", "wf2")
        assert len(s.get_suspensions("a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.suspend("a1", "wf2")
        assert s.get_suspensions("a1")[0]["_seq"] > s.get_suspensions("a1")[1]["_seq"]
    def test_limit(self):
        s = AgentWorkflowSuspender()
        for i in range(5): s.suspend("a1", f"wf{i}")
        assert len(s.get_suspensions(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.suspend("a2", "wf2")
        assert s.get_suspension_count() == 2
    def test_filtered(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.suspend("a2", "wf2")
        assert s.get_suspension_count("a1") == 1
    def test_empty(self):
        assert AgentWorkflowSuspender().get_suspension_count() == 0
class TestStats:
    def test_empty(self):
        assert AgentWorkflowSuspender().get_stats()["total_suspensions"] == 0
    def test_data(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.suspend("a2", "wf2")
        assert s.get_stats()["total_suspensions"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowSuspender(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.suspend("a1", "wf1")
        assert "suspended" in calls
    def test_remove_true(self):
        s = AgentWorkflowSuspender(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowSuspender().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentWorkflowSuspender(); s.MAX_ENTRIES = 5
        for i in range(8): s.suspend("a1", f"wf{i}")
        assert s.get_suspension_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.reset()
        assert s.get_suspension_count() == 0
    def test_callbacks(self):
        s = AgentWorkflowSuspender(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowSuspender(); s.suspend("a1", "wf1"); s.reset()
        assert s._state._seq == 0
