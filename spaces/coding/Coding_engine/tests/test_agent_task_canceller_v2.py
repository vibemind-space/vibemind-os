import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_canceller_v2 import AgentTaskCancellerV2

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskCancellerV2()
        rid = s.cancel_v2("v1", "v2")
        assert rid.startswith("atcv-")
    def test_fields(self):
        s = AgentTaskCancellerV2()
        rid = s.cancel_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_cancellation(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskCancellerV2()
        rid = s.cancel_v2("v1", "v2")
        assert s.get_cancellation(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = AgentTaskCancellerV2()
        m = {"x": [1]}
        rid = s.cancel_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_cancellation(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskCancellerV2()
        assert s.cancel_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskCancellerV2()
        assert s.cancel_v2("v1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskCancellerV2()
        rid = s.cancel_v2("v1", "v2")
        assert s.get_cancellation(rid) is not None
    def test_not_found(self):
        s = AgentTaskCancellerV2()
        assert s.get_cancellation("nope") is None
    def test_copy(self):
        s = AgentTaskCancellerV2()
        rid = s.cancel_v2("v1", "v2")
        assert s.get_cancellation(rid) is not s.get_cancellation(rid)

class TestList:
    def test_all(self):
        s = AgentTaskCancellerV2()
        s.cancel_v2("v1", "v2")
        s.cancel_v2("v3", "v4")
        assert len(s.get_cancellations()) == 2
    def test_filter(self):
        s = AgentTaskCancellerV2()
        s.cancel_v2("v1", "v2")
        s.cancel_v2("v3", "v4")
        assert len(s.get_cancellations(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskCancellerV2()
        s.cancel_v2("t1", "a1")
        s.cancel_v2("t2", "a1")
        items = s.get_cancellations(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = AgentTaskCancellerV2()
        s.cancel_v2("v1", "v2")
        s.cancel_v2("v3", "v4")
        assert s.get_cancellation_count() == 2
    def test_filtered(self):
        s = AgentTaskCancellerV2()
        s.cancel_v2("v1", "v2")
        s.cancel_v2("v3", "v4")
        assert s.get_cancellation_count("v2") == 1

class TestStats:
    def test_data(self):
        s = AgentTaskCancellerV2()
        s.cancel_v2("v1", "v2")
        st = s.get_stats()
        assert st["total_cancellations"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskCancellerV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.cancel_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskCancellerV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskCancellerV2()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskCancellerV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.cancel_v2(f"p{i}", f"v{i}")
        assert s.get_cancellation_count() <= 6

class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskCancellerV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.cancel_v2("t1", "a1")
        assert captured[0]["action"] == "cancel_v2"
        assert captured[0]["task_id"] == "t1"

class TestReset:
    def test_clears(self):
        s = AgentTaskCancellerV2()
        s.on_change = lambda a, d: None
        s.cancel_v2("v1", "v2")
        s.reset()
        assert s.get_cancellation_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskCancellerV2()
        s.cancel_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
