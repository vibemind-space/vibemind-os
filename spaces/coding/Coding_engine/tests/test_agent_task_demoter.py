"""Tests for AgentTaskDemoter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_demoter import AgentTaskDemoter

class TestIdGeneration:
    def test_prefix(self):
        s = AgentTaskDemoter()
        assert s.demote("t1", "a1").startswith("atdm-")
    def test_unique(self):
        s = AgentTaskDemoter()
        ids = {s.demote(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestDemoteBasic:
    def test_returns_id(self):
        s = AgentTaskDemoter()
        assert len(s.demote("t1", "a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskDemoter()
        rid = s.demote("t1", "a1", new_priority=0, reason="low")
        e = s.get_demotion(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["new_priority"] == 0
        assert e["reason"] == "low"
    def test_with_metadata(self):
        s = AgentTaskDemoter()
        rid = s.demote("t1", "a1", metadata={"x": 1})
        assert s.get_demotion(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskDemoter()
        m = {"a": [1]}
        rid = s.demote("t1", "a1", metadata=m)
        m["a"].append(2)
        assert s.get_demotion(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskDemoter()
        before = time.time()
        rid = s.demote("t1", "a1")
        assert s.get_demotion(rid)["created_at"] >= before
    def test_empty_task_returns_empty(self):
        assert AgentTaskDemoter().demote("", "a1") == ""
    def test_empty_agent_returns_empty(self):
        assert AgentTaskDemoter().demote("t1", "") == ""

class TestGetDemotion:
    def test_found(self):
        s = AgentTaskDemoter()
        rid = s.demote("t1", "a1")
        assert s.get_demotion(rid) is not None
    def test_not_found(self):
        assert AgentTaskDemoter().get_demotion("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskDemoter()
        rid = s.demote("t1", "a1")
        assert s.get_demotion(rid) is not s.get_demotion(rid)

class TestGetDemotions:
    def test_all(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.demote("t2", "a2")
        assert len(s.get_demotions()) == 2
    def test_filter(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.demote("t2", "a2")
        assert len(s.get_demotions(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.demote("t2", "a1")
        assert s.get_demotions(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskDemoter()
        for i in range(10): s.demote(f"t{i}", "a1")
        assert len(s.get_demotions(limit=3)) == 3

class TestGetDemotionCount:
    def test_total(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.demote("t2", "a2")
        assert s.get_demotion_count() == 2
    def test_filtered(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.demote("t2", "a2")
        assert s.get_demotion_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskDemoter().get_demotion_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskDemoter().get_stats()["total_demotions"] == 0
    def test_with_data(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.demote("t2", "a2")
        st = s.get_stats()
        assert st["total_demotions"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskDemoter()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.demote("t1", "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskDemoter()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskDemoter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskDemoter()
        s.MAX_ENTRIES = 5
        for i in range(8): s.demote(f"t{i}", "a1")
        assert s.get_demotion_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.reset()
        assert s.get_demotion_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskDemoter()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskDemoter()
        s.demote("t1", "a1"); s.reset()
        assert s._state._seq == 0
