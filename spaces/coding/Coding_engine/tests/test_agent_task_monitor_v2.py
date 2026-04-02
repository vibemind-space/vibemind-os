import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_monitor_v2 import AgentTaskMonitorV2

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskMonitorV2()
        rid = s.monitor_task_v2("v1", "v2")
        assert rid.startswith("atmnv-")
    def test_fields(self):
        s = AgentTaskMonitorV2()
        rid = s.monitor_task_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_task_monitor(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskMonitorV2()
        rid = s.monitor_task_v2("v1", "v2")
        assert s.get_task_monitor(rid)["interval"] == 30
    def test_metadata_deepcopy(self):
        s = AgentTaskMonitorV2()
        m = {"x": [1]}
        rid = s.monitor_task_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_task_monitor(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskMonitorV2()
        assert s.monitor_task_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskMonitorV2()
        assert s.monitor_task_v2("v1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskMonitorV2()
        rid = s.monitor_task_v2("v1", "v2")
        assert s.get_task_monitor(rid) is not None
    def test_not_found(self):
        s = AgentTaskMonitorV2()
        assert s.get_task_monitor("nope") is None
    def test_copy(self):
        s = AgentTaskMonitorV2()
        rid = s.monitor_task_v2("v1", "v2")
        assert s.get_task_monitor(rid) is not s.get_task_monitor(rid)
class TestList:
    def test_all(self):
        s = AgentTaskMonitorV2()
        s.monitor_task_v2("v1", "v2")
        s.monitor_task_v2("v3", "v4")
        assert len(s.get_task_monitors()) == 2
    def test_filter(self):
        s = AgentTaskMonitorV2()
        s.monitor_task_v2("v1", "v2")
        s.monitor_task_v2("v3", "v4")
        assert len(s.get_task_monitors(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskMonitorV2()
        s.monitor_task_v2("t1", "a1")
        s.monitor_task_v2("t2", "a1")
        items = s.get_task_monitors(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskMonitorV2()
        s.monitor_task_v2("v1", "v2")
        s.monitor_task_v2("v3", "v4")
        assert s.get_task_monitor_count() == 2
    def test_filtered(self):
        s = AgentTaskMonitorV2()
        s.monitor_task_v2("v1", "v2")
        s.monitor_task_v2("v3", "v4")
        assert s.get_task_monitor_count("v2") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskMonitorV2()
        s.monitor_task_v2("v1", "v2")
        assert s.get_stats()["total_task_monitors"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskMonitorV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.monitor_task_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskMonitorV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskMonitorV2()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskMonitorV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.monitor_task_v2(f"p{i}", f"v{i}")
        assert s.get_task_monitor_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskMonitorV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.monitor_task_v2("t1", "a1")
        assert captured[0]["action"] == "monitor_task_v2"
        assert captured[0]["record_id"].startswith("atmnv-")
class TestReset:
    def test_clears(self):
        s = AgentTaskMonitorV2()
        s.on_change = lambda a, d: None
        s.monitor_task_v2("v1", "v2")
        s.reset()
        assert s.get_task_monitor_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskMonitorV2()
        s.monitor_task_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
