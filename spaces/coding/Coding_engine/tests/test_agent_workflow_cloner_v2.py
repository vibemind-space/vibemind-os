import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_workflow_cloner_v2 import AgentWorkflowClonerV2

class TestBasic:
    def test_returns_id(self):
        s = AgentWorkflowClonerV2()
        rid = s.clone_v2("v1", "v2")
        assert rid.startswith("awcv-")
    def test_fields(self):
        s = AgentWorkflowClonerV2()
        rid = s.clone_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_clone(rid)
        assert e["agent_id"] == "v1"
        assert e["workflow_name"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentWorkflowClonerV2()
        rid = s.clone_v2("v1", "v2")
        assert s.get_clone(rid)["target"] == ""
    def test_metadata_deepcopy(self):
        s = AgentWorkflowClonerV2()
        m = {"x": [1]}
        rid = s.clone_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_clone(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentWorkflowClonerV2()
        assert s.clone_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentWorkflowClonerV2()
        assert s.clone_v2("v1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentWorkflowClonerV2()
        rid = s.clone_v2("v1", "v2")
        assert s.get_clone(rid) is not None
    def test_not_found(self):
        s = AgentWorkflowClonerV2()
        assert s.get_clone("nope") is None
    def test_copy(self):
        s = AgentWorkflowClonerV2()
        rid = s.clone_v2("v1", "v2")
        assert s.get_clone(rid) is not s.get_clone(rid)

class TestList:
    def test_all(self):
        s = AgentWorkflowClonerV2()
        s.clone_v2("v1", "v2")
        s.clone_v2("v3", "v4")
        assert len(s.get_clones()) == 2
    def test_filter(self):
        s = AgentWorkflowClonerV2()
        s.clone_v2("v1", "v2")
        s.clone_v2("v3", "v4")
        assert len(s.get_clones(agent_id="v1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowClonerV2()
        s.clone_v2("v1", "a1")
        s.clone_v2("v1", "a2")
        items = s.get_clones(agent_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = AgentWorkflowClonerV2()
        s.clone_v2("v1", "v2")
        s.clone_v2("v3", "v4")
        assert s.get_clone_count() == 2
    def test_filtered(self):
        s = AgentWorkflowClonerV2()
        s.clone_v2("v1", "v2")
        s.clone_v2("v3", "v4")
        assert s.get_clone_count("v1") == 1

class TestStats:
    def test_data(self):
        s = AgentWorkflowClonerV2()
        s.clone_v2("v1", "v2")
        st = s.get_stats()
        assert st["total_clones"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowClonerV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.clone_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentWorkflowClonerV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentWorkflowClonerV2()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowClonerV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.clone_v2(f"p{i}", f"v{i}")
        assert s.get_clone_count() <= 6

class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentWorkflowClonerV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.clone_v2("t1", "a1")
        assert captured[0]["action"] == "clone_v2"
        assert captured[0]["agent_id"] == "t1"

class TestReset:
    def test_clears(self):
        s = AgentWorkflowClonerV2()
        s.on_change = lambda a, d: None
        s.clone_v2("v1", "v2")
        s.reset()
        assert s.get_clone_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowClonerV2()
        s.clone_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
