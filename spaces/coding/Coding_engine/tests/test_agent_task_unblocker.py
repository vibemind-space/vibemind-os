"""Tests for AgentTaskUnblocker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_unblocker import AgentTaskUnblocker

class TestIdGeneration:
    def test_prefix(self):
        s = AgentTaskUnblocker()
        assert s.unblock("t1", "a1").startswith("atub-")
    def test_unique(self):
        s = AgentTaskUnblocker()
        ids = {s.unblock(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestUnblockBasic:
    def test_returns_id(self):
        s = AgentTaskUnblocker()
        assert len(s.unblock("t1", "a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskUnblocker()
        rid = s.unblock("t1", "a1", reason="resolved")
        e = s.get_unblock(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["reason"] == "resolved"
    def test_with_metadata(self):
        s = AgentTaskUnblocker()
        rid = s.unblock("t1", "a1", metadata={"x": 1})
        assert s.get_unblock(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskUnblocker()
        m = {"a": [1]}
        rid = s.unblock("t1", "a1", metadata=m)
        m["a"].append(2)
        assert s.get_unblock(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskUnblocker()
        before = time.time()
        rid = s.unblock("t1", "a1")
        assert s.get_unblock(rid)["created_at"] >= before
    def test_empty_task_returns_empty(self):
        assert AgentTaskUnblocker().unblock("", "a1") == ""
    def test_empty_agent_returns_empty(self):
        assert AgentTaskUnblocker().unblock("t1", "") == ""

class TestGetUnblock:
    def test_found(self):
        s = AgentTaskUnblocker()
        rid = s.unblock("t1", "a1")
        assert s.get_unblock(rid) is not None
    def test_not_found(self):
        assert AgentTaskUnblocker().get_unblock("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskUnblocker()
        rid = s.unblock("t1", "a1")
        assert s.get_unblock(rid) is not s.get_unblock(rid)

class TestGetUnblocks:
    def test_all(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.unblock("t2", "a2")
        assert len(s.get_unblocks()) == 2
    def test_filter(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.unblock("t2", "a2")
        assert len(s.get_unblocks(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.unblock("t2", "a1")
        assert s.get_unblocks(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskUnblocker()
        for i in range(10): s.unblock(f"t{i}", "a1")
        assert len(s.get_unblocks(limit=3)) == 3

class TestGetUnblockCount:
    def test_total(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.unblock("t2", "a2")
        assert s.get_unblock_count() == 2
    def test_filtered(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.unblock("t2", "a2")
        assert s.get_unblock_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskUnblocker().get_unblock_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskUnblocker().get_stats()["total_unblocks"] == 0
    def test_with_data(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.unblock("t2", "a2")
        st = s.get_stats()
        assert st["total_unblocks"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskUnblocker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.unblock("t1", "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskUnblocker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskUnblocker().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskUnblocker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.unblock(f"t{i}", "a1")
        assert s.get_unblock_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.reset()
        assert s.get_unblock_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskUnblocker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskUnblocker()
        s.unblock("t1", "a1"); s.reset()
        assert s._state._seq == 0
