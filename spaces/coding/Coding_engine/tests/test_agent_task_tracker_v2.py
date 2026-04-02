import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_tracker_v2 import AgentTaskTrackerV2

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskTrackerV2()
        rid = s.track_v2("v1", "v2")
        assert rid.startswith("attv-")
    def test_fields(self):
        s = AgentTaskTrackerV2()
        rid = s.track_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_tracking(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskTrackerV2()
        rid = s.track_v2("v1", "v2")
        assert s.get_tracking(rid)["status"] == "active"
    def test_metadata_deepcopy(self):
        s = AgentTaskTrackerV2()
        m = {"x": [1]}
        rid = s.track_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_tracking(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskTrackerV2()
        assert s.track_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskTrackerV2()
        assert s.track_v2("v1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskTrackerV2()
        rid = s.track_v2("v1", "v2")
        assert s.get_tracking(rid) is not None
    def test_not_found(self):
        s = AgentTaskTrackerV2()
        assert s.get_tracking("nope") is None
    def test_copy(self):
        s = AgentTaskTrackerV2()
        rid = s.track_v2("v1", "v2")
        assert s.get_tracking(rid) is not s.get_tracking(rid)

class TestList:
    def test_all(self):
        s = AgentTaskTrackerV2()
        s.track_v2("v1", "v2")
        s.track_v2("v3", "v4")
        assert len(s.get_trackings()) == 2
    def test_filter(self):
        s = AgentTaskTrackerV2()
        s.track_v2("v1", "v2")
        s.track_v2("v3", "v4")
        assert len(s.get_trackings(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskTrackerV2()
        s.track_v2("t1", "a1")
        s.track_v2("t2", "a1")
        items = s.get_trackings(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = AgentTaskTrackerV2()
        s.track_v2("v1", "v2")
        s.track_v2("v3", "v4")
        assert s.get_tracking_count() == 2
    def test_filtered(self):
        s = AgentTaskTrackerV2()
        s.track_v2("v1", "v2")
        s.track_v2("v3", "v4")
        assert s.get_tracking_count("v2") == 1

class TestStats:
    def test_data(self):
        s = AgentTaskTrackerV2()
        s.track_v2("v1", "v2")
        st = s.get_stats()
        assert st["total_trackings"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskTrackerV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.track_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskTrackerV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskTrackerV2()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskTrackerV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.track_v2(f"p{i}", f"v{i}")
        assert s.get_tracking_count() <= 6

class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskTrackerV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.track_v2("t1", "a1")
        assert captured[0]["action"] == "track_v2"
        assert captured[0]["task_id"] == "t1"

class TestReset:
    def test_clears(self):
        s = AgentTaskTrackerV2()
        s.on_change = lambda a, d: None
        s.track_v2("v1", "v2")
        s.reset()
        assert s.get_tracking_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskTrackerV2()
        s.track_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
