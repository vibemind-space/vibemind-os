"""Tests for AgentTaskFailover service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_failover import AgentTaskFailover

class TestIdGeneration:
    def test_prefix(self):
        s = AgentTaskFailover()
        assert s.failover("t1", "a1", "a2").startswith("atfo-")
    def test_unique(self):
        s = AgentTaskFailover()
        ids = {s.failover(f"t{i}", "a1", "a2") for i in range(20)}
        assert len(ids) == 20

class TestFailoverBasic:
    def test_returns_id(self):
        s = AgentTaskFailover()
        assert len(s.failover("t1", "a1", "a2")) > 0
    def test_stores_fields(self):
        s = AgentTaskFailover()
        rid = s.failover("t1", "a1", "a2", reason="crashed")
        e = s.get_failover(rid)
        assert e["task_id"] == "t1"
        assert e["from_agent"] == "a1"
        assert e["to_agent"] == "a2"
        assert e["reason"] == "crashed"
    def test_with_metadata(self):
        s = AgentTaskFailover()
        rid = s.failover("t1", "a1", "a2", metadata={"x": 1})
        assert s.get_failover(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskFailover()
        m = {"a": [1]}
        rid = s.failover("t1", "a1", "a2", metadata=m)
        m["a"].append(2)
        assert s.get_failover(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskFailover()
        before = time.time()
        rid = s.failover("t1", "a1", "a2")
        assert s.get_failover(rid)["created_at"] >= before
    def test_empty_task_returns_empty(self):
        assert AgentTaskFailover().failover("", "a1", "a2") == ""
    def test_empty_from_returns_empty(self):
        assert AgentTaskFailover().failover("t1", "", "a2") == ""
    def test_empty_to_returns_empty(self):
        assert AgentTaskFailover().failover("t1", "a1", "") == ""

class TestGetFailover:
    def test_found(self):
        s = AgentTaskFailover()
        rid = s.failover("t1", "a1", "a2")
        assert s.get_failover(rid) is not None
    def test_not_found(self):
        assert AgentTaskFailover().get_failover("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskFailover()
        rid = s.failover("t1", "a1", "a2")
        assert s.get_failover(rid) is not s.get_failover(rid)

class TestGetFailovers:
    def test_all(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.failover("t2", "a3", "a4")
        assert len(s.get_failovers()) == 2
    def test_filter(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.failover("t2", "a3", "a4")
        assert len(s.get_failovers(from_agent="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.failover("t2", "a1", "a3")
        assert s.get_failovers(from_agent="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskFailover()
        for i in range(10): s.failover(f"t{i}", "a1", "a2")
        assert len(s.get_failovers(limit=3)) == 3

class TestGetFailoverCount:
    def test_total(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.failover("t2", "a3", "a4")
        assert s.get_failover_count() == 2
    def test_filtered(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.failover("t2", "a3", "a4")
        assert s.get_failover_count(from_agent="a1") == 1
    def test_empty(self):
        assert AgentTaskFailover().get_failover_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskFailover().get_stats()["total_failovers"] == 0
    def test_with_data(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.failover("t2", "a3", "a4")
        st = s.get_stats()
        assert st["total_failovers"] == 2
        assert st["unique_agents"] == 4

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskFailover()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.failover("t1", "a1", "a2")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskFailover()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskFailover().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskFailover()
        s.MAX_ENTRIES = 5
        for i in range(8): s.failover(f"t{i}", "a1", "a2")
        assert s.get_failover_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.reset()
        assert s.get_failover_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskFailover()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskFailover()
        s.failover("t1", "a1", "a2"); s.reset()
        assert s._state._seq == 0
