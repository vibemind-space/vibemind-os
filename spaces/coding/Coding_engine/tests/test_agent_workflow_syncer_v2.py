import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_workflow_syncer_v2 import AgentWorkflowSyncerV2

class TestBasic:
    def test_returns_id(self):
        s = AgentWorkflowSyncerV2()
        rid = s.sync_v2("v1", "v2")
        assert rid.startswith("awsyv-")
    def test_fields(self):
        s = AgentWorkflowSyncerV2()
        rid = s.sync_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_sync(rid)
        assert e["agent_id"] == "v1"
        assert e["workflow_name"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentWorkflowSyncerV2()
        rid = s.sync_v2("v1", "v2")
        assert s.get_sync(rid)["target"] == "primary"
    def test_metadata_deepcopy(self):
        s = AgentWorkflowSyncerV2()
        m = {"x": [1]}
        rid = s.sync_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_sync(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentWorkflowSyncerV2()
        assert s.sync_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentWorkflowSyncerV2()
        assert s.sync_v2("v1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentWorkflowSyncerV2()
        rid = s.sync_v2("v1", "v2")
        assert s.get_sync(rid) is not None
    def test_not_found(self):
        s = AgentWorkflowSyncerV2()
        assert s.get_sync("nope") is None
    def test_copy(self):
        s = AgentWorkflowSyncerV2()
        rid = s.sync_v2("v1", "v2")
        assert s.get_sync(rid) is not s.get_sync(rid)
class TestList:
    def test_all(self):
        s = AgentWorkflowSyncerV2()
        s.sync_v2("v1", "v2")
        s.sync_v2("v3", "v4")
        assert len(s.get_syncs()) == 2
    def test_filter(self):
        s = AgentWorkflowSyncerV2()
        s.sync_v2("v1", "v2")
        s.sync_v2("v3", "v4")
        assert len(s.get_syncs(agent_id="v1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowSyncerV2()
        s.sync_v2("v1", "w1")
        s.sync_v2("v1", "w2")
        items = s.get_syncs(agent_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentWorkflowSyncerV2()
        s.sync_v2("v1", "v2")
        s.sync_v2("v3", "v4")
        assert s.get_sync_count() == 2
    def test_filtered(self):
        s = AgentWorkflowSyncerV2()
        s.sync_v2("v1", "v2")
        s.sync_v2("v3", "v4")
        assert s.get_sync_count("v1") == 1
class TestStats:
    def test_data(self):
        s = AgentWorkflowSyncerV2()
        s.sync_v2("v1", "v2")
        assert s.get_stats()["total_syncs"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowSyncerV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.sync_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentWorkflowSyncerV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentWorkflowSyncerV2()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentWorkflowSyncerV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.sync_v2(f"p{i}", f"v{i}")
        assert s.get_sync_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentWorkflowSyncerV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.sync_v2("t1", "a1")
        assert captured[0]["action"] == "sync_v2"
        assert captured[0]["record_id"].startswith("awsyv-")
class TestReset:
    def test_clears(self):
        s = AgentWorkflowSyncerV2()
        s.on_change = lambda a, d: None
        s.sync_v2("v1", "v2")
        s.reset()
        assert s.get_sync_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowSyncerV2()
        s.sync_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
