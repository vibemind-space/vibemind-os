import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_assignee import AgentTaskAssignee

class TestBasic:
    def test_returns_id(self):
        assert AgentTaskAssignee().assign("t1", "a1").startswith("atas-")
    def test_fields(self):
        s = AgentTaskAssignee(); rid = s.assign("t1", "a1", assignee="bob")
        e = s.get_assignment(rid)
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["assignee"] == "bob"
    def test_default_assignee(self):
        s = AgentTaskAssignee(); rid = s.assign("t1", "a1")
        assert s.get_assignment(rid)["assignee"] == ""
    def test_metadata_deepcopy(self):
        s = AgentTaskAssignee(); m = {"x": [1]}
        rid = s.assign("t1", "a1", metadata=m); m["x"].append(2)
        assert s.get_assignment(rid)["metadata"] == {"x": [1]}
    def test_empty_task(self):
        assert AgentTaskAssignee().assign("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskAssignee().assign("t1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskAssignee(); rid = s.assign("t1", "a1")
        assert s.get_assignment(rid) is not None
    def test_not_found(self):
        assert AgentTaskAssignee().get_assignment("nope") is None
    def test_copy(self):
        s = AgentTaskAssignee(); rid = s.assign("t1", "a1")
        assert s.get_assignment(rid) is not s.get_assignment(rid)
class TestList:
    def test_all(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.assign("t2", "a2")
        assert len(s.get_assignments()) == 2
    def test_filter(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.assign("t2", "a2")
        assert len(s.get_assignments("a1")) == 1
    def test_newest_first(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.assign("t2", "a1")
        assert s.get_assignments("a1")[0]["_seq"] > s.get_assignments("a1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.assign("t2", "a2")
        assert s.get_assignment_count() == 2
    def test_filtered(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.assign("t2", "a2")
        assert s.get_assignment_count("a1") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.assign("t2", "a2")
        assert s.get_stats()["total_assignments"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskAssignee(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.assign("t1", "a1")
        assert "assigned" in calls
    def test_remove_true(self):
        s = AgentTaskAssignee(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskAssignee().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskAssignee(); s.MAX_ENTRIES = 5
        for i in range(8): s.assign(f"t{i}", "a1")
        assert s.get_assignment_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.reset()
        assert s.get_assignment_count() == 0
    def test_seq(self):
        s = AgentTaskAssignee(); s.assign("t1", "a1"); s.reset()
        assert s._state._seq == 0
