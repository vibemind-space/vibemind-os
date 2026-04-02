import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_task_forker_v2 import AgentTaskForkerV2

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskForkerV2()
        rid = s.fork_v2("v1", "v2")
        assert rid.startswith("atfk-")
    def test_fields(self):
        s = AgentTaskForkerV2()
        rid = s.fork_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_fork(rid)
        assert e["task_id"] == "v1"
        assert e["agent_id"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = AgentTaskForkerV2()
        rid = s.fork_v2("v1", "v2")
        assert s.get_fork(rid)["branch"] == "default"
    def test_metadata_deepcopy(self):
        s = AgentTaskForkerV2()
        m = {"x": [1]}
        rid = s.fork_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_fork(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = AgentTaskForkerV2()
        assert s.fork_v2("", "v2") == ""
    def test_empty_p2(self):
        s = AgentTaskForkerV2()
        assert s.fork_v2("v1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskForkerV2()
        rid = s.fork_v2("v1", "v2")
        assert s.get_fork(rid) is not None
    def test_not_found(self):
        s = AgentTaskForkerV2()
        assert s.get_fork("nope") is None
    def test_copy(self):
        s = AgentTaskForkerV2()
        rid = s.fork_v2("v1", "v2")
        assert s.get_fork(rid) is not s.get_fork(rid)

class TestList:
    def test_all(self):
        s = AgentTaskForkerV2()
        s.fork_v2("v1", "v2")
        s.fork_v2("v3", "v4")
        assert len(s.get_forks()) == 2
    def test_filter(self):
        s = AgentTaskForkerV2()
        s.fork_v2("v1", "v2")
        s.fork_v2("v3", "v4")
        assert len(s.get_forks(agent_id="v2")) == 1
    def test_newest_first(self):
        s = AgentTaskForkerV2()
        s.fork_v2("t1", "a1")
        s.fork_v2("t2", "a1")
        items = s.get_forks(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = AgentTaskForkerV2()
        s.fork_v2("v1", "v2")
        s.fork_v2("v3", "v4")
        assert s.get_fork_count() == 2
    def test_filtered(self):
        s = AgentTaskForkerV2()
        s.fork_v2("v1", "v2")
        s.fork_v2("v3", "v4")
        assert s.get_fork_count("v2") == 1

class TestStats:
    def test_data(self):
        s = AgentTaskForkerV2()
        s.fork_v2("v1", "v2")
        st = s.get_stats()
        assert st["total_forks"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskForkerV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.fork_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = AgentTaskForkerV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = AgentTaskForkerV2()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskForkerV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.fork_v2(f"p{i}", f"v{i}")
        assert s.get_fork_count() <= 6

class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = AgentTaskForkerV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.fork_v2("t1", "a1")
        assert captured[0]["action"] == "fork_v2"
        assert captured[0]["record_id"].startswith("atfk-")

class TestReset:
    def test_clears(self):
        s = AgentTaskForkerV2()
        s.on_change = lambda a, d: None
        s.fork_v2("v1", "v2")
        s.reset()
        assert s.get_fork_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskForkerV2()
        s.fork_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
