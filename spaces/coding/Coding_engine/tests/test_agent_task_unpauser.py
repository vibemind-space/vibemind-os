"""Tests for AgentTaskUnpauser service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_unpauser import AgentTaskUnpauser

class TestId:
    def test_prefix(self):
        assert AgentTaskUnpauser().unpause("t1", "a1").startswith("atup-")
    def test_unique(self):
        s = AgentTaskUnpauser()
        assert len({s.unpause(f"t{i}", "a1") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentTaskUnpauser().unpause("t1", "a1")) > 0
    def test_fields(self):
        s = AgentTaskUnpauser()
        e = s.get_unpause(s.unpause("t1", "a1", reason="ready"))
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["reason"] == "ready"
    def test_deepcopy(self):
        s = AgentTaskUnpauser(); m = {"a": [1]}
        rid = s.unpause("t1", "a1", metadata=m); m["a"].append(2)
        assert s.get_unpause(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskUnpauser(); b = time.time()
        assert s.get_unpause(s.unpause("t1", "a1"))["created_at"] >= b
    def test_empty_task(self):
        assert AgentTaskUnpauser().unpause("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskUnpauser().unpause("t1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskUnpauser(); assert s.get_unpause(s.unpause("t1", "a1")) is not None
    def test_not_found(self):
        assert AgentTaskUnpauser().get_unpause("xxx") is None
    def test_copy(self):
        s = AgentTaskUnpauser(); rid = s.unpause("t1", "a1")
        assert s.get_unpause(rid) is not s.get_unpause(rid)

class TestList:
    def test_all(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.unpause("t2", "a2")
        assert len(s.get_unpauses()) == 2
    def test_filter(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.unpause("t2", "a2")
        assert len(s.get_unpauses(agent_id="a1")) == 1
    def test_newest(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.unpause("t2", "a1")
        assert s.get_unpauses(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskUnpauser()
        for i in range(10): s.unpause(f"t{i}", "a1")
        assert len(s.get_unpauses(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.unpause("t2", "a2")
        assert s.get_unpause_count() == 2
    def test_filtered(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.unpause("t2", "a2")
        assert s.get_unpause_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskUnpauser().get_unpause_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentTaskUnpauser().get_stats()["total_unpauses"] == 0
    def test_data(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.unpause("t2", "a2")
        assert s.get_stats()["total_unpauses"] == 2 and s.get_stats()["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskUnpauser(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.unpause("t1", "a1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = AgentTaskUnpauser(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskUnpauser().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskUnpauser(); s.MAX_ENTRIES = 5
        for i in range(8): s.unpause(f"t{i}", "a1")
        assert s.get_unpause_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.reset()
        assert s.get_unpause_count() == 0
    def test_callbacks(self):
        s = AgentTaskUnpauser(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskUnpauser(); s.unpause("t1", "a1"); s.reset()
        assert s._state._seq == 0
