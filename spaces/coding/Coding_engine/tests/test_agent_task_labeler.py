import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_labeler import AgentTaskLabeler

class TestBasic:
    def test_returns_id(self):
        assert AgentTaskLabeler().label("t1", "a1").startswith("atlb-")
    def test_fields(self):
        s = AgentTaskLabeler(); rid = s.label("t1", "a1", label_name="urgent")
        e = s.get_label(rid)
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["label_name"] == "urgent"
    def test_default_label(self):
        s = AgentTaskLabeler(); rid = s.label("t1", "a1")
        assert s.get_label(rid)["label_name"] == ""
    def test_metadata_deepcopy(self):
        s = AgentTaskLabeler(); m = {"x": [1]}
        rid = s.label("t1", "a1", metadata=m); m["x"].append(2)
        assert s.get_label(rid)["metadata"] == {"x": [1]}
    def test_empty_task(self):
        assert AgentTaskLabeler().label("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskLabeler().label("t1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskLabeler(); rid = s.label("t1", "a1")
        assert s.get_label(rid) is not None
    def test_not_found(self):
        assert AgentTaskLabeler().get_label("nope") is None
    def test_copy(self):
        s = AgentTaskLabeler(); rid = s.label("t1", "a1")
        assert s.get_label(rid) is not s.get_label(rid)
class TestList:
    def test_all(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.label("t2", "a2")
        assert len(s.get_labels()) == 2
    def test_filter(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.label("t2", "a2")
        assert len(s.get_labels("a1")) == 1
    def test_newest_first(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.label("t2", "a1")
        assert s.get_labels("a1")[0]["_seq"] > s.get_labels("a1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.label("t2", "a2")
        assert s.get_label_count() == 2
    def test_filtered(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.label("t2", "a2")
        assert s.get_label_count("a1") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.label("t2", "a2")
        assert s.get_stats()["total_labels"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskLabeler(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.label("t1", "a1")
        assert "labeled" in calls
    def test_remove_true(self):
        s = AgentTaskLabeler(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskLabeler().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskLabeler(); s.MAX_ENTRIES = 5
        for i in range(8): s.label(f"t{i}", "a1")
        assert s.get_label_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.reset()
        assert s.get_label_count() == 0
    def test_seq(self):
        s = AgentTaskLabeler(); s.label("t1", "a1"); s.reset()
        assert s._state._seq == 0
