"""Tests for AgentTaskPauser service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_pauser import AgentTaskPauser

class TestIdGeneration:
    def test_prefix(self):
        assert AgentTaskPauser().pause("t1", "a1").startswith("atpa-")
    def test_unique(self):
        s = AgentTaskPauser()
        ids = {s.pause(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestPauseBasic:
    def test_returns_id(self):
        assert len(AgentTaskPauser().pause("t1", "a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskPauser()
        rid = s.pause("t1", "a1", reason="waiting")
        e = s.get_pause(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["reason"] == "waiting"
    def test_metadata_deepcopy(self):
        s = AgentTaskPauser()
        m = {"a": [1]}
        rid = s.pause("t1", "a1", metadata=m)
        m["a"].append(2)
        assert s.get_pause(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskPauser()
        before = time.time()
        assert s.get_pause(s.pause("t1", "a1"))["created_at"] >= before
    def test_empty_task(self):
        assert AgentTaskPauser().pause("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskPauser().pause("t1", "") == ""

class TestGetPause:
    def test_found(self):
        s = AgentTaskPauser()
        assert s.get_pause(s.pause("t1", "a1")) is not None
    def test_not_found(self):
        assert AgentTaskPauser().get_pause("xxx") is None
    def test_copy(self):
        s = AgentTaskPauser()
        rid = s.pause("t1", "a1")
        assert s.get_pause(rid) is not s.get_pause(rid)

class TestGetPauses:
    def test_all(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.pause("t2", "a2")
        assert len(s.get_pauses()) == 2
    def test_filter(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.pause("t2", "a2")
        assert len(s.get_pauses(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.pause("t2", "a1")
        assert s.get_pauses(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskPauser()
        for i in range(10): s.pause(f"t{i}", "a1")
        assert len(s.get_pauses(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.pause("t2", "a2")
        assert s.get_pause_count() == 2
    def test_filtered(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.pause("t2", "a2")
        assert s.get_pause_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskPauser().get_pause_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentTaskPauser().get_stats()["total_pauses"] == 0
    def test_data(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.pause("t2", "a2")
        assert s.get_stats()["total_pauses"] == 2
        assert s.get_stats()["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskPauser()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.pause("t1", "a1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = AgentTaskPauser()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskPauser().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskPauser()
        s.MAX_ENTRIES = 5
        for i in range(8): s.pause(f"t{i}", "a1")
        assert s.get_pause_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.reset()
        assert s.get_pause_count() == 0
    def test_callbacks(self):
        s = AgentTaskPauser()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskPauser()
        s.pause("t1", "a1"); s.reset()
        assert s._state._seq == 0
