"""Tests for AgentTaskDispatcher service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_dispatcher import AgentTaskDispatcher

class TestIdGeneration:
    def test_prefix(self):
        s = AgentTaskDispatcher()
        assert s.dispatch("t1", "a1").startswith("atds-")
    def test_unique(self):
        s = AgentTaskDispatcher()
        ids = {s.dispatch(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestDispatchBasic:
    def test_returns_id(self):
        s = AgentTaskDispatcher()
        assert len(s.dispatch("t1", "a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskDispatcher()
        rid = s.dispatch("t1", "a1", priority=3)
        e = s.get_dispatch(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["priority"] == 3
    def test_default_priority(self):
        s = AgentTaskDispatcher()
        rid = s.dispatch("t1", "a1")
        assert s.get_dispatch(rid)["priority"] == 5
    def test_with_metadata(self):
        s = AgentTaskDispatcher()
        rid = s.dispatch("t1", "a1", metadata={"x": 1})
        assert s.get_dispatch(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskDispatcher()
        m = {"a": [1]}
        rid = s.dispatch("t1", "a1", metadata=m)
        m["a"].append(2)
        assert s.get_dispatch(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskDispatcher()
        before = time.time()
        rid = s.dispatch("t1", "a1")
        assert s.get_dispatch(rid)["created_at"] >= before
    def test_empty_task_returns_empty(self):
        assert AgentTaskDispatcher().dispatch("", "a1") == ""
    def test_empty_agent_returns_empty(self):
        assert AgentTaskDispatcher().dispatch("t1", "") == ""

class TestGetDispatch:
    def test_found(self):
        s = AgentTaskDispatcher()
        rid = s.dispatch("t1", "a1")
        assert s.get_dispatch(rid) is not None
    def test_not_found(self):
        assert AgentTaskDispatcher().get_dispatch("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskDispatcher()
        rid = s.dispatch("t1", "a1")
        assert s.get_dispatch(rid) is not s.get_dispatch(rid)

class TestGetDispatches:
    def test_all(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.dispatch("t2", "a2")
        assert len(s.get_dispatches()) == 2
    def test_filter(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.dispatch("t2", "a2")
        assert len(s.get_dispatches(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.dispatch("t2", "a1")
        assert s.get_dispatches(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskDispatcher()
        for i in range(10): s.dispatch(f"t{i}", "a1")
        assert len(s.get_dispatches(limit=3)) == 3

class TestGetDispatchCount:
    def test_total(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.dispatch("t2", "a2")
        assert s.get_dispatch_count() == 2
    def test_filtered(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.dispatch("t2", "a2")
        assert s.get_dispatch_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskDispatcher().get_dispatch_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskDispatcher().get_stats()["total_dispatches"] == 0
    def test_with_data(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.dispatch("t2", "a2")
        st = s.get_stats()
        assert st["total_dispatches"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskDispatcher()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.dispatch("t1", "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskDispatcher()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskDispatcher().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskDispatcher()
        s.MAX_ENTRIES = 5
        for i in range(8): s.dispatch(f"t{i}", "a1")
        assert s.get_dispatch_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.reset()
        assert s.get_dispatch_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskDispatcher()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskDispatcher()
        s.dispatch("t1", "a1"); s.reset()
        assert s._state._seq == 0
