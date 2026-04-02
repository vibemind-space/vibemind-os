import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_rejector import AgentTaskRejector

class TestBasic:
    def test_returns_id(self):
        assert AgentTaskRejector().reject("t1", "a1").startswith("atrj-")
    def test_fields(self):
        s = AgentTaskRejector(); rid = s.reject("t1", "a1", reason="invalid")
        e = s.get_rejection(rid)
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["reason"] == "invalid"
    def test_default_reason(self):
        s = AgentTaskRejector(); rid = s.reject("t1", "a1")
        assert s.get_rejection(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = AgentTaskRejector(); m = {"x": [1]}
        rid = s.reject("t1", "a1", metadata=m); m["x"].append(2)
        assert s.get_rejection(rid)["metadata"] == {"x": [1]}
    def test_empty_task(self):
        assert AgentTaskRejector().reject("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskRejector().reject("t1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskRejector(); rid = s.reject("t1", "a1")
        assert s.get_rejection(rid) is not None
    def test_not_found(self):
        assert AgentTaskRejector().get_rejection("nope") is None
    def test_copy(self):
        s = AgentTaskRejector(); rid = s.reject("t1", "a1")
        assert s.get_rejection(rid) is not s.get_rejection(rid)
class TestList:
    def test_all(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reject("t2", "a2")
        assert len(s.get_rejections()) == 2
    def test_filter(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reject("t2", "a2")
        assert len(s.get_rejections("a1")) == 1
    def test_newest_first(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reject("t2", "a1")
        assert s.get_rejections("a1")[0]["_seq"] > s.get_rejections("a1")[1]["_seq"]
    def test_limit(self):
        s = AgentTaskRejector()
        for i in range(5): s.reject(f"t{i}", "a1")
        assert len(s.get_rejections(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reject("t2", "a2")
        assert s.get_rejection_count() == 2
    def test_filtered(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reject("t2", "a2")
        assert s.get_rejection_count("a1") == 1
    def test_empty(self):
        assert AgentTaskRejector().get_rejection_count() == 0
class TestStats:
    def test_empty(self):
        assert AgentTaskRejector().get_stats()["total_rejections"] == 0
    def test_data(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reject("t2", "a2")
        assert s.get_stats()["total_rejections"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskRejector(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.reject("t1", "a1")
        assert "rejected" in calls
    def test_remove_true(self):
        s = AgentTaskRejector(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskRejector().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskRejector(); s.MAX_ENTRIES = 5
        for i in range(8): s.reject(f"t{i}", "a1")
        assert s.get_rejection_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reset()
        assert s.get_rejection_count() == 0
    def test_callbacks(self):
        s = AgentTaskRejector(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskRejector(); s.reject("t1", "a1"); s.reset()
        assert s._state._seq == 0
