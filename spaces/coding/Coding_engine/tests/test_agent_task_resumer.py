"""Tests for AgentTaskResumer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_resumer import AgentTaskResumer

class TestIdGeneration:
    def test_prefix(self):
        r = AgentTaskResumer()
        assert r.resume("t1", "a1").startswith("atre-")
    def test_unique(self):
        r = AgentTaskResumer()
        ids = {r.resume(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestResumeBasic:
    def test_returns_id(self):
        r = AgentTaskResumer()
        assert len(r.resume("t1", "a1")) > 0
    def test_stores_fields(self):
        r = AgentTaskResumer()
        rid = r.resume("t1", "a1", reason="retry")
        e = r.get_resumption(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["reason"] == "retry"
    def test_with_metadata(self):
        r = AgentTaskResumer()
        rid = r.resume("t1", "a1", metadata={"x": 1})
        assert r.get_resumption(rid)["metadata"]["x"] == 1
    def test_created_at(self):
        r = AgentTaskResumer()
        before = time.time()
        rid = r.resume("t1", "a1")
        assert r.get_resumption(rid)["created_at"] >= before

class TestResumeValidation:
    def test_empty_task_id(self):
        assert AgentTaskResumer().resume("", "a1") == ""
    def test_empty_agent_id(self):
        assert AgentTaskResumer().resume("t1", "") == ""

class TestGetResumption:
    def test_found(self):
        r = AgentTaskResumer()
        rid = r.resume("t1", "a1")
        assert r.get_resumption(rid) is not None
    def test_not_found(self):
        assert AgentTaskResumer().get_resumption("xxx") is None
    def test_returns_copy(self):
        r = AgentTaskResumer()
        rid = r.resume("t1", "a1")
        assert r.get_resumption(rid) is not r.get_resumption(rid)

class TestGetResumptions:
    def test_all(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.resume("t2", "a2")
        assert len(r.get_resumptions()) == 2
    def test_filter(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.resume("t2", "a2")
        assert len(r.get_resumptions(agent_id="a1")) == 1
    def test_newest_first(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.resume("t2", "a1")
        assert r.get_resumptions(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        r = AgentTaskResumer()
        for i in range(10): r.resume(f"t{i}", "a1")
        assert len(r.get_resumptions(limit=3)) == 3

class TestGetResumptionCount:
    def test_total(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.resume("t2", "a2")
        assert r.get_resumption_count() == 2
    def test_filtered(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.resume("t2", "a2")
        assert r.get_resumption_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskResumer().get_resumption_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskResumer().get_stats()["total_resumptions"] == 0
    def test_with_data(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.resume("t2", "a2")
        st = r.get_stats()
        assert st["total_resumptions"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        r = AgentTaskResumer()
        evts = []
        r.on_change = lambda a, d: evts.append(a)
        r.resume("t1", "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        r = AgentTaskResumer()
        r._state.callbacks["cb1"] = lambda a, d: None
        assert r.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskResumer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        r = AgentTaskResumer()
        r.MAX_ENTRIES = 5
        for i in range(8): r.resume(f"t{i}", "a1")
        assert r.get_resumption_count() < 8

class TestReset:
    def test_clears(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.reset()
        assert r.get_resumption_count() == 0
    def test_clears_callbacks(self):
        r = AgentTaskResumer()
        r.on_change = lambda a, d: None
        r.reset()
        assert r.on_change is None
    def test_resets_seq(self):
        r = AgentTaskResumer()
        r.resume("t1", "a1"); r.reset()
        assert r._state._seq == 0
