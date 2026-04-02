import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest
from src.services.agent_task_watcher import AgentTaskWatcher


class TestBasic:
    def test_returns_id(self):
        s = AgentTaskWatcher()
        rid = s.watch("t1", "a1")
        assert rid.startswith("atwt-")

    def test_fields(self):
        s = AgentTaskWatcher()
        rid = s.watch("t1", "a1", interval=120, metadata={"k": "v"})
        e = s.get_watch(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["interval"] == 120
        assert e["metadata"] == {"k": "v"}
        assert "created_at" in e

    def test_default_interval(self):
        s = AgentTaskWatcher()
        rid = s.watch("t1", "a1")
        assert s.get_watch(rid)["interval"] == 60

    def test_metadata_deepcopy(self):
        s = AgentTaskWatcher()
        m = {"x": [1]}
        rid = s.watch("t1", "a1", metadata=m)
        m["x"].append(2)
        assert s.get_watch(rid)["metadata"]["x"] == [1]

    def test_empty_task(self):
        s = AgentTaskWatcher()
        assert s.watch("", "a1") == ""

    def test_empty_agent(self):
        s = AgentTaskWatcher()
        assert s.watch("t1", "") == ""


class TestGet:
    def test_found(self):
        s = AgentTaskWatcher()
        rid = s.watch("t1", "a1")
        assert s.get_watch(rid) is not None

    def test_not_found(self):
        s = AgentTaskWatcher()
        assert s.get_watch("nope") is None

    def test_copy(self):
        s = AgentTaskWatcher()
        rid = s.watch("t1", "a1")
        e1 = s.get_watch(rid)
        e2 = s.get_watch(rid)
        assert e1 is not e2


class TestList:
    def test_all(self):
        s = AgentTaskWatcher()
        s.watch("t1", "a1")
        s.watch("t2", "a2")
        assert len(s.get_watches()) == 2

    def test_filter(self):
        s = AgentTaskWatcher()
        s.watch("t1", "a1")
        s.watch("t2", "a2")
        assert len(s.get_watches(agent_id="a1")) == 1

    def test_newest_first(self):
        s = AgentTaskWatcher()
        s.watch("t1", "a1")
        s.watch("t2", "a1")
        items = s.get_watches(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]


class TestCount:
    def test_total(self):
        s = AgentTaskWatcher()
        s.watch("t1", "a1")
        s.watch("t2", "a2")
        assert s.get_watch_count() == 2

    def test_filtered(self):
        s = AgentTaskWatcher()
        s.watch("t1", "a1")
        s.watch("t2", "a2")
        assert s.get_watch_count("a1") == 1


class TestStats:
    def test_data(self):
        s = AgentTaskWatcher()
        s.watch("t1", "a1")
        s.watch("t2", "a2")
        st = s.get_stats()
        assert st["total_watches"] == 2
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskWatcher()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.watch("t1", "a1")
        assert len(calls) == 1

    def test_remove_true(self):
        s = AgentTaskWatcher()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = AgentTaskWatcher()
        assert s.remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = AgentTaskWatcher()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.watch(f"t{i}", f"a{i}")
        assert s.get_watch_count() <= 6


class TestReset:
    def test_clears(self):
        s = AgentTaskWatcher()
        s.on_change = lambda a, d: None
        s.watch("t1", "a1")
        s.reset()
        assert s.get_watch_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = AgentTaskWatcher()
        s.watch("t1", "a1")
        s.reset()
        assert s._state._seq == 0
