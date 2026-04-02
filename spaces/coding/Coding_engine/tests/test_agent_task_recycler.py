"""Tests for AgentTaskRecycler service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_recycler import AgentTaskRecycler

class TestIdGeneration:
    def test_prefix(self):
        r = AgentTaskRecycler()
        assert r.recycle("t1", "a1").startswith("atrc-")
    def test_unique(self):
        r = AgentTaskRecycler()
        ids = {r.recycle(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestRecycleBasic:
    def test_returns_id(self):
        assert len(AgentTaskRecycler().recycle("t1", "a1")) > 0
    def test_stores_fields(self):
        r = AgentTaskRecycler()
        rid = r.recycle("t1", "a1", reason="retry")
        e = r.get_recycling(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["reason"] == "retry"
    def test_with_metadata(self):
        r = AgentTaskRecycler()
        rid = r.recycle("t1", "a1", metadata={"x": 1})
        assert r.get_recycling(rid)["metadata"]["x"] == 1

class TestRecycleValidation:
    def test_empty_task_id(self):
        assert AgentTaskRecycler().recycle("", "a1") == ""
    def test_empty_agent_id(self):
        assert AgentTaskRecycler().recycle("t1", "") == ""

class TestGetRecycling:
    def test_found(self):
        r = AgentTaskRecycler()
        rid = r.recycle("t1", "a1")
        assert r.get_recycling(rid) is not None
    def test_not_found(self):
        assert AgentTaskRecycler().get_recycling("xxx") is None
    def test_returns_copy(self):
        r = AgentTaskRecycler()
        rid = r.recycle("t1", "a1")
        assert r.get_recycling(rid) is not r.get_recycling(rid)

class TestGetRecyclings:
    def test_all(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.recycle("t2", "a2")
        assert len(r.get_recyclings()) == 2
    def test_filter(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.recycle("t2", "a2")
        assert len(r.get_recyclings(agent_id="a1")) == 1
    def test_newest_first(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.recycle("t2", "a1")
        assert r.get_recyclings(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        r = AgentTaskRecycler()
        for i in range(10): r.recycle(f"t{i}", "a1")
        assert len(r.get_recyclings(limit=3)) == 3

class TestGetRecyclingCount:
    def test_total(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.recycle("t2", "a2")
        assert r.get_recycling_count() == 2
    def test_filtered(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.recycle("t2", "a2")
        assert r.get_recycling_count(agent_id="a1") == 1

class TestGetStats:
    def test_empty(self):
        assert AgentTaskRecycler().get_stats()["total_recyclings"] == 0
    def test_with_data(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.recycle("t2", "a2")
        st = r.get_stats()
        assert st["total_recyclings"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        r = AgentTaskRecycler()
        evts = []
        r.on_change = lambda a, d: evts.append(a)
        r.recycle("t1", "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        r = AgentTaskRecycler()
        r._state.callbacks["cb1"] = lambda a, d: None
        assert r.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskRecycler().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        r = AgentTaskRecycler()
        r.MAX_ENTRIES = 5
        for i in range(8): r.recycle(f"t{i}", "a1")
        assert r.get_recycling_count() < 8

class TestReset:
    def test_clears(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.reset()
        assert r.get_recycling_count() == 0
    def test_resets_seq(self):
        r = AgentTaskRecycler()
        r.recycle("t1", "a1"); r.reset()
        assert r._state._seq == 0
