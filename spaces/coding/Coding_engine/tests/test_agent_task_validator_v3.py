import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_validator_v3 import AgentTaskValidatorV3

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskValidatorV3()
        rid = s.validate_task_v3("v1", "v2")
        assert rid.startswith("atvl3-")
    def test_fields(self):
        s = AgentTaskValidatorV3()
        rid = s.validate_task_v3("v1", "v2", metadata={"k": "v"})
        e = s.get_task_validation(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskValidatorV3()
        rid = s.validate_task_v3("v1", "v2")
        assert s.get_task_validation(rid)["rules"] == "strict"
    def test_metadata_deepcopy(self):
        s = AgentTaskValidatorV3()
        m = {"x": [1]}
        rid = s.validate_task_v3("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_task_validation(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskValidatorV3()
        assert s.validate_task_v3("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskValidatorV3()
        assert s.validate_task_v3("v1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskValidatorV3()
        rid = s.validate_task_v3("v1", "v2")
        assert s.get_task_validation(rid) is not None
    def test_not_found(self):
        s = AgentTaskValidatorV3()
        assert s.get_task_validation("nope") is None
    def test_copy(self):
        s = AgentTaskValidatorV3()
        rid = s.validate_task_v3("v1", "v2")
        assert s.get_task_validation(rid) is not s.get_task_validation(rid)
class TestList:
    def test_all(self):
        s = AgentTaskValidatorV3()
        s.validate_task_v3("v1", "v2")
        s.validate_task_v3("v3", "v4")
        assert len(s.get_task_validations()) == 2
    def test_filter(self):
        s = AgentTaskValidatorV3()
        s.validate_task_v3("v1", "v2")
        s.validate_task_v3("v3", "v4")
        assert len(s.get_task_validations(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskValidatorV3()
        s.validate_task_v3("t1", "a1")
        s.validate_task_v3("t2", "a1")
        items = s.get_task_validations(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskValidatorV3()
        s.validate_task_v3("v1", "v2")
        s.validate_task_v3("v3", "v4")
        assert s.get_task_validation_count() == 2
    def test_filtered(self):
        s = AgentTaskValidatorV3()
        s.validate_task_v3("v1", "v2")
        s.validate_task_v3("v3", "v4")
        assert s.get_task_validation_count("v2") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskValidatorV3()
        s.validate_task_v3("v1", "v2")
        assert s.get_stats()["total_task_validations"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskValidatorV3()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.validate_task_v3("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskValidatorV3()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskValidatorV3()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskValidatorV3()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.validate_task_v3(f"p{i}", f"v{i}")
        assert s.get_task_validation_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskValidatorV3()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.validate_task_v3("t1", "a1")
        assert captured[0]["action"] == "validate_task_v3"
        assert captured[0]["record_id"].startswith("atvl3-")
class TestReset:
    def test_clears(self):
        s = AgentTaskValidatorV3()
        s.on_change = lambda a, d: None
        s.validate_task_v3("v1", "v2")
        s.reset()
        assert s.get_task_validation_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskValidatorV3()
        s.validate_task_v3("v1", "v2")
        s.reset()
        assert s._state._seq == 0
