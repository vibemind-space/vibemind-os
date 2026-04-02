import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_descheduler import AgentWorkflowDescheduler

class TestBasic:
    def test_returns_id(self):
        s = AgentWorkflowDescheduler()
        assert s.deschedule("a1", "wf1").startswith("awds-")
    def test_fields(self):
        s = AgentWorkflowDescheduler()
        rid = s.deschedule("a1", "wf1", reason="timeout")
        e = s.get_deschedule(rid)
        assert e["agent_id"] == "a1" and e["workflow_name"] == "wf1" and e["reason"] == "timeout"
    def test_default_reason(self):
        s = AgentWorkflowDescheduler()
        rid = s.deschedule("a1", "wf1")
        assert s.get_deschedule(rid)["reason"] == ""
    def test_metadata(self):
        s = AgentWorkflowDescheduler()
        rid = s.deschedule("a1", "wf1", metadata={"x": 1})
        assert s.get_deschedule(rid)["metadata"] == {"x": 1}
    def test_metadata_deepcopy(self):
        s = AgentWorkflowDescheduler(); m = {"x": [1]}
        rid = s.deschedule("a1", "wf1", metadata=m); m["x"].append(2)
        assert s.get_deschedule(rid)["metadata"] == {"x": [1]}
    def test_empty_agent(self):
        assert AgentWorkflowDescheduler().deschedule("", "wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowDescheduler().deschedule("a1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentWorkflowDescheduler(); rid = s.deschedule("a1", "wf1")
        assert s.get_deschedule(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowDescheduler().get_deschedule("nope") is None
    def test_copy(self):
        s = AgentWorkflowDescheduler(); rid = s.deschedule("a1", "wf1")
        assert s.get_deschedule(rid) is not s.get_deschedule(rid)

class TestList:
    def test_all(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.deschedule("a2", "wf2")
        assert len(s.get_deschedules()) == 2
    def test_filter(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.deschedule("a2", "wf2")
        assert len(s.get_deschedules("a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.deschedule("a1", "wf2")
        assert s.get_deschedules("a1")[0]["_seq"] > s.get_deschedules("a1")[1]["_seq"]
    def test_limit(self):
        s = AgentWorkflowDescheduler()
        for i in range(5): s.deschedule("a1", f"wf{i}")
        assert len(s.get_deschedules(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.deschedule("a2", "wf2")
        assert s.get_deschedule_count() == 2
    def test_filtered(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.deschedule("a2", "wf2")
        assert s.get_deschedule_count("a1") == 1
    def test_empty(self):
        assert AgentWorkflowDescheduler().get_deschedule_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentWorkflowDescheduler().get_stats()["total_deschedules"] == 0
    def test_data(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.deschedule("a2", "wf2")
        st = s.get_stats()
        assert st["total_deschedules"] == 2 and st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowDescheduler(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.deschedule("a1", "wf1")
        assert "descheduled" in calls
    def test_remove_true(self):
        s = AgentWorkflowDescheduler(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowDescheduler().remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowDescheduler(); s.MAX_ENTRIES = 5
        for i in range(8): s.deschedule("a1", f"wf{i}")
        assert s.get_deschedule_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.reset()
        assert s.get_deschedule_count() == 0
    def test_callbacks(self):
        s = AgentWorkflowDescheduler(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowDescheduler(); s.deschedule("a1", "wf1"); s.reset()
        assert s._state._seq == 0
