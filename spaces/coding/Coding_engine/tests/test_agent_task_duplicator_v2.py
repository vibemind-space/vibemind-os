import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_duplicator_v2 import AgentTaskDuplicatorV2

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskDuplicatorV2()
        rid = s.duplicate_v2("v1", "v2")
        assert rid.startswith("atdpv-")
    def test_fields(self):
        s = AgentTaskDuplicatorV2()
        rid = s.duplicate_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_duplicate(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskDuplicatorV2()
        rid = s.duplicate_v2("v1", "v2")
        assert s.get_duplicate(rid)["count"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskDuplicatorV2()
        m = {"x": [1]}
        rid = s.duplicate_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_duplicate(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskDuplicatorV2()
        assert s.duplicate_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskDuplicatorV2()
        assert s.duplicate_v2("v1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskDuplicatorV2()
        rid = s.duplicate_v2("v1", "v2")
        assert s.get_duplicate(rid) is not None
    def test_not_found(self):
        s = AgentTaskDuplicatorV2()
        assert s.get_duplicate("nope") is None
    def test_copy(self):
        s = AgentTaskDuplicatorV2()
        rid = s.duplicate_v2("v1", "v2")
        assert s.get_duplicate(rid) is not s.get_duplicate(rid)
class TestList:
    def test_all(self):
        s = AgentTaskDuplicatorV2()
        s.duplicate_v2("v1", "v2")
        s.duplicate_v2("v3", "v4")
        assert len(s.get_duplicates()) == 2
    def test_filter(self):
        s = AgentTaskDuplicatorV2()
        s.duplicate_v2("v1", "v2")
        s.duplicate_v2("v3", "v4")
        assert len(s.get_duplicates(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskDuplicatorV2()
        s.duplicate_v2("t1", "a1")
        s.duplicate_v2("t2", "a1")
        items = s.get_duplicates(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskDuplicatorV2()
        s.duplicate_v2("v1", "v2")
        s.duplicate_v2("v3", "v4")
        assert s.get_duplicate_count() == 2
    def test_filtered(self):
        s = AgentTaskDuplicatorV2()
        s.duplicate_v2("v1", "v2")
        s.duplicate_v2("v3", "v4")
        assert s.get_duplicate_count("v2") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskDuplicatorV2()
        s.duplicate_v2("v1", "v2")
        assert s.get_stats()["total_duplicates"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskDuplicatorV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.duplicate_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskDuplicatorV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskDuplicatorV2()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskDuplicatorV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.duplicate_v2(f"p{i}", f"v{i}")
        assert s.get_duplicate_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskDuplicatorV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.duplicate_v2("t1", "a1")
        assert captured[0]["action"] == "duplicate_v2"
        assert captured[0]["record_id"].startswith("atdpv-")
class TestReset:
    def test_clears(self):
        s = AgentTaskDuplicatorV2()
        s.on_change = lambda a, d: None
        s.duplicate_v2("v1", "v2")
        s.reset()
        assert s.get_duplicate_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskDuplicatorV2()
        s.duplicate_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
