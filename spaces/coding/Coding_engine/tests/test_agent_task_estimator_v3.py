import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_estimator_v3 import AgentTaskEstimatorV3

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskEstimatorV3()
        rid = s.estimate_v3("v1", "v2")
        assert rid.startswith("ate3-")
    def test_fields(self):
        s = AgentTaskEstimatorV3()
        rid = s.estimate_v3("v1", "v2", metadata={"k": "v"})
        e = s.get_estimate(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskEstimatorV3()
        rid = s.estimate_v3("v1", "v2")
        assert s.get_estimate(rid)["confidence"] == "medium"
    def test_metadata_deepcopy(self):
        s = AgentTaskEstimatorV3()
        m = {"x": [1]}
        rid = s.estimate_v3("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_estimate(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskEstimatorV3()
        assert s.estimate_v3("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskEstimatorV3()
        assert s.estimate_v3("v1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskEstimatorV3()
        rid = s.estimate_v3("v1", "v2")
        assert s.get_estimate(rid) is not None
    def test_not_found(self):
        s = AgentTaskEstimatorV3()
        assert s.get_estimate("nope") is None
    def test_copy(self):
        s = AgentTaskEstimatorV3()
        rid = s.estimate_v3("v1", "v2")
        assert s.get_estimate(rid) is not s.get_estimate(rid)
class TestList:
    def test_all(self):
        s = AgentTaskEstimatorV3()
        s.estimate_v3("v1", "v2")
        s.estimate_v3("v3", "v4")
        assert len(s.get_estimates()) == 2
    def test_filter(self):
        s = AgentTaskEstimatorV3()
        s.estimate_v3("v1", "v2")
        s.estimate_v3("v3", "v4")
        assert len(s.get_estimates(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskEstimatorV3()
        s.estimate_v3("t1", "a1")
        s.estimate_v3("t2", "a1")
        items = s.get_estimates(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskEstimatorV3()
        s.estimate_v3("v1", "v2")
        s.estimate_v3("v3", "v4")
        assert s.get_estimate_count() == 2
    def test_filtered(self):
        s = AgentTaskEstimatorV3()
        s.estimate_v3("v1", "v2")
        s.estimate_v3("v3", "v4")
        assert s.get_estimate_count("v2") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskEstimatorV3()
        s.estimate_v3("v1", "v2")
        assert s.get_stats()["total_estimates"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskEstimatorV3()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.estimate_v3("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskEstimatorV3()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskEstimatorV3()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskEstimatorV3()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.estimate_v3(f"p{i}", f"v{i}")
        assert s.get_estimate_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskEstimatorV3()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.estimate_v3("t1", "a1")
        assert captured[0]["action"] == "estimate_v3"
        assert captured[0]["record_id"].startswith("ate3-")
class TestReset:
    def test_clears(self):
        s = AgentTaskEstimatorV3()
        s.on_change = lambda a, d: None
        s.estimate_v3("v1", "v2")
        s.reset()
        assert s.get_estimate_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskEstimatorV3()
        s.estimate_v3("v1", "v2")
        s.reset()
        assert s._state._seq == 0
