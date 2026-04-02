import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_approver import AgentTaskApprover

class TestBasic:
    def test_returns_id(self):
        assert AgentTaskApprover().approve("t1", "a1").startswith("atap-")
    def test_fields(self):
        s = AgentTaskApprover(); rid = s.approve("t1", "a1", decision="rejected")
        e = s.get_approval(rid)
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["decision"] == "rejected"
    def test_default_decision(self):
        s = AgentTaskApprover(); rid = s.approve("t1", "a1")
        assert s.get_approval(rid)["decision"] == "approved"
    def test_metadata(self):
        s = AgentTaskApprover(); rid = s.approve("t1", "a1", metadata={"x": 1})
        assert s.get_approval(rid)["metadata"] == {"x": 1}
    def test_metadata_deepcopy(self):
        s = AgentTaskApprover(); m = {"x": [1]}
        rid = s.approve("t1", "a1", metadata=m); m["x"].append(2)
        assert s.get_approval(rid)["metadata"] == {"x": [1]}
    def test_empty_task(self):
        assert AgentTaskApprover().approve("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskApprover().approve("t1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskApprover(); rid = s.approve("t1", "a1")
        assert s.get_approval(rid) is not None
    def test_not_found(self):
        assert AgentTaskApprover().get_approval("nope") is None
    def test_copy(self):
        s = AgentTaskApprover(); rid = s.approve("t1", "a1")
        assert s.get_approval(rid) is not s.get_approval(rid)

class TestList:
    def test_all(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.approve("t2", "a2")
        assert len(s.get_approvals()) == 2
    def test_filter(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.approve("t2", "a2")
        assert len(s.get_approvals("a1")) == 1
    def test_newest_first(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.approve("t2", "a1")
        assert s.get_approvals("a1")[0]["_seq"] > s.get_approvals("a1")[1]["_seq"]
    def test_limit(self):
        s = AgentTaskApprover()
        for i in range(5): s.approve(f"t{i}", "a1")
        assert len(s.get_approvals(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.approve("t2", "a2")
        assert s.get_approval_count() == 2
    def test_filtered(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.approve("t2", "a2")
        assert s.get_approval_count("a1") == 1
    def test_empty(self):
        assert AgentTaskApprover().get_approval_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentTaskApprover().get_stats()["total_approvals"] == 0
    def test_data(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.approve("t2", "a2")
        st = s.get_stats()
        assert st["total_approvals"] == 2 and st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskApprover(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.approve("t1", "a1")
        assert "approved" in calls
    def test_remove_true(self):
        s = AgentTaskApprover(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskApprover().remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskApprover(); s.MAX_ENTRIES = 5
        for i in range(8): s.approve(f"t{i}", "a1")
        assert s.get_approval_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.reset()
        assert s.get_approval_count() == 0
    def test_callbacks(self):
        s = AgentTaskApprover(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskApprover(); s.approve("t1", "a1"); s.reset()
        assert s._state._seq == 0
