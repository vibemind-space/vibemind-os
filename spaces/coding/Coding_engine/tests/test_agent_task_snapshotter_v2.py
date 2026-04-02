import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_snapshotter_v2 import AgentTaskSnapshotterV2

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskSnapshotterV2()
        rid = s.snapshot_v2("v1", "v2")
        assert rid.startswith("atsnv-")
    def test_fields(self):
        s = AgentTaskSnapshotterV2()
        rid = s.snapshot_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_snapshot(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskSnapshotterV2()
        rid = s.snapshot_v2("v1", "v2")
        assert s.get_snapshot(rid)["label"] == "auto"
    def test_metadata_deepcopy(self):
        s = AgentTaskSnapshotterV2()
        m = {"x": [1]}
        rid = s.snapshot_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_snapshot(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskSnapshotterV2()
        assert s.snapshot_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskSnapshotterV2()
        assert s.snapshot_v2("v1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskSnapshotterV2()
        rid = s.snapshot_v2("v1", "v2")
        assert s.get_snapshot(rid) is not None
    def test_not_found(self):
        s = AgentTaskSnapshotterV2()
        assert s.get_snapshot("nope") is None
    def test_copy(self):
        s = AgentTaskSnapshotterV2()
        rid = s.snapshot_v2("v1", "v2")
        assert s.get_snapshot(rid) is not s.get_snapshot(rid)
class TestList:
    def test_all(self):
        s = AgentTaskSnapshotterV2()
        s.snapshot_v2("v1", "v2")
        s.snapshot_v2("v3", "v4")
        assert len(s.get_snapshots()) == 2
    def test_filter(self):
        s = AgentTaskSnapshotterV2()
        s.snapshot_v2("v1", "v2")
        s.snapshot_v2("v3", "v4")
        assert len(s.get_snapshots(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskSnapshotterV2()
        s.snapshot_v2("t1", "a1")
        s.snapshot_v2("t2", "a1")
        items = s.get_snapshots(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = AgentTaskSnapshotterV2()
        s.snapshot_v2("v1", "v2")
        s.snapshot_v2("v3", "v4")
        assert s.get_snapshot_count() == 2
    def test_filtered(self):
        s = AgentTaskSnapshotterV2()
        s.snapshot_v2("v1", "v2")
        s.snapshot_v2("v3", "v4")
        assert s.get_snapshot_count("v2") == 1
class TestStats:
    def test_data(self):
        s = AgentTaskSnapshotterV2()
        s.snapshot_v2("v1", "v2")
        assert s.get_stats()["total_snapshots"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskSnapshotterV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.snapshot_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskSnapshotterV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskSnapshotterV2()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskSnapshotterV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.snapshot_v2(f"p{i}", f"v{i}")
        assert s.get_snapshot_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskSnapshotterV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.snapshot_v2("t1", "a1")
        assert captured[0]["action"] == "snapshot_v2"
        assert captured[0]["record_id"].startswith("atsnv-")
class TestReset:
    def test_clears(self):
        s = AgentTaskSnapshotterV2()
        s.on_change = lambda a, d: None
        s.snapshot_v2("v1", "v2")
        s.reset()
        assert s.get_snapshot_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskSnapshotterV2()
        s.snapshot_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
