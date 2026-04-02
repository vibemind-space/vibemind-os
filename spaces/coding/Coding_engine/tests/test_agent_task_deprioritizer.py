"""Tests for AgentTaskDeprioritizer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_deprioritizer import AgentTaskDeprioritizer

class TestIdGeneration:
    def test_prefix(self):
        s = AgentTaskDeprioritizer()
        assert s.deprioritize("t1", "a1").startswith("atdp-")
    def test_unique(self):
        s = AgentTaskDeprioritizer()
        ids = {s.deprioritize(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestDeprioritizeBasic:
    def test_returns_id(self):
        s = AgentTaskDeprioritizer()
        assert len(s.deprioritize("t1", "a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskDeprioritizer()
        rid = s.deprioritize("t1", "a1", reason="low")
        e = s.get_deprioritization(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["reason"] == "low"
    def test_with_metadata(self):
        s = AgentTaskDeprioritizer()
        rid = s.deprioritize("t1", "a1", metadata={"x": 1})
        assert s.get_deprioritization(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskDeprioritizer()
        m = {"a": [1]}
        rid = s.deprioritize("t1", "a1", metadata=m)
        m["a"].append(2)
        assert s.get_deprioritization(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskDeprioritizer()
        before = time.time()
        rid = s.deprioritize("t1", "a1")
        assert s.get_deprioritization(rid)["created_at"] >= before
    def test_empty_task_returns_empty(self):
        assert AgentTaskDeprioritizer().deprioritize("", "a1") == ""
    def test_empty_agent_returns_empty(self):
        assert AgentTaskDeprioritizer().deprioritize("t1", "") == ""

class TestGetDeprioritization:
    def test_found(self):
        s = AgentTaskDeprioritizer()
        rid = s.deprioritize("t1", "a1")
        assert s.get_deprioritization(rid) is not None
    def test_not_found(self):
        assert AgentTaskDeprioritizer().get_deprioritization("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskDeprioritizer()
        rid = s.deprioritize("t1", "a1")
        assert s.get_deprioritization(rid) is not s.get_deprioritization(rid)

class TestGetDeprioritizations:
    def test_all(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.deprioritize("t2", "a2")
        assert len(s.get_deprioritizations()) == 2
    def test_filter(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.deprioritize("t2", "a2")
        assert len(s.get_deprioritizations(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.deprioritize("t2", "a1")
        assert s.get_deprioritizations(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskDeprioritizer()
        for i in range(10): s.deprioritize(f"t{i}", "a1")
        assert len(s.get_deprioritizations(limit=3)) == 3

class TestGetDeprioritizationCount:
    def test_total(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.deprioritize("t2", "a2")
        assert s.get_deprioritization_count() == 2
    def test_filtered(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.deprioritize("t2", "a2")
        assert s.get_deprioritization_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskDeprioritizer().get_deprioritization_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskDeprioritizer().get_stats()["total_deprioritizations"] == 0
    def test_with_data(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.deprioritize("t2", "a2")
        st = s.get_stats()
        assert st["total_deprioritizations"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskDeprioritizer()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.deprioritize("t1", "a1")
        assert len(evts) >= 1
    def test_named_callback(self):
        s = AgentTaskDeprioritizer()
        evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.deprioritize("t1", "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskDeprioritizer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskDeprioritizer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskDeprioritizer()
        s.MAX_ENTRIES = 5
        for i in range(8): s.deprioritize(f"t{i}", "a1")
        assert s.get_deprioritization_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.reset()
        assert s.get_deprioritization_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskDeprioritizer()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskDeprioritizer()
        s.deprioritize("t1", "a1"); s.reset()
        assert s._state._seq == 0
