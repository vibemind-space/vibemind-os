import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_scheduler_v3 import AgentTaskSchedulerV3

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskSchedulerV3()
        rid = s.schedule_v3("v1", "v2")
        assert rid.startswith("ats3-")
    def test_fields(self):
        s = AgentTaskSchedulerV3()
        rid = s.schedule_v3("v1", "v2", metadata={"k": "v"})
        e = s.get_schedule(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskSchedulerV3()
        rid = s.schedule_v3("v1", "v2")
        assert s.get_schedule(rid)["priority"] == "normal"
    def test_metadata_deepcopy(self):
        s = AgentTaskSchedulerV3()
        m = {"x": [1]}
        rid = s.schedule_v3("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_schedule(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskSchedulerV3()
        assert s.schedule_v3("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskSchedulerV3()
        assert s.schedule_v3("v1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskSchedulerV3()
        rid = s.schedule_v3("v1", "v2")
        assert s.get_schedule(rid) is not None
    def test_not_found(self):
        s = AgentTaskSchedulerV3()
        assert s.get_schedule("nope") is None
    def test_copy(self):
        s = AgentTaskSchedulerV3()
        rid = s.schedule_v3("v1", "v2")
        assert s.get_schedule(rid) is not s.get_schedule(rid)
class TestList:
    def test_all(self):
        s = AgentTaskSchedulerV3()
        s.schedule_v3("v1", "v2")
        s.schedule_v3("v3", "v4")
        assert len(s.get_schedules()) == 2
    def test_filter(self):
        s = AgentTaskSchedulerV3()
        s.schedule_v3("v1", "v2")
        s.schedule_v3("v3", "v4")
        assert len(s.get_schedules(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskSchedulerV3()
        s.schedule_v3("t1", "a1")
        s.schedule_v3("t2", "a1")
        items = s.get_schedules(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskSchedulerV3()
        s.schedule_v3("v1", "v2")
        s.schedule_v3("v3", "v4")
        assert s.get_schedule_count() == 2
    def test_filtered(self):
        s = AgentTaskSchedulerV3()
        s.schedule_v3("v1", "v2")
        s.schedule_v3("v3", "v4")
        assert s.get_schedule_count("v2") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskSchedulerV3()
        s.schedule_v3("v1", "v2")
        assert s.get_stats()["total_schedules"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskSchedulerV3()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.schedule_v3("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskSchedulerV3()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskSchedulerV3()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskSchedulerV3()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.schedule_v3(f"p{i}", f"v{i}")
        assert s.get_schedule_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskSchedulerV3()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.schedule_v3("t1", "a1")
        assert captured[0]["action"] == "schedule_v3"
        assert captured[0]["record_id"].startswith("ats3-")
class TestReset:
    def test_clears(self):
        s = AgentTaskSchedulerV3()
        s.on_change = lambda a, d: None
        s.schedule_v3("v1", "v2")
        s.reset()
        assert s.get_schedule_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskSchedulerV3()
        s.schedule_v3("v1", "v2")
        s.reset()
        assert s._state._seq == 0
