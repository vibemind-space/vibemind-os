"""Tests for AgentTaskEscalator service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_escalator import AgentTaskEscalator

class TestIdGeneration:
    def test_prefix(self):
        s = AgentTaskEscalator()
        assert s.escalate("t1", "a1", "a2").startswith("ates-")
    def test_unique(self):
        s = AgentTaskEscalator()
        ids = {s.escalate(f"t{i}", "a1", "a2") for i in range(20)}
        assert len(ids) == 20

class TestEscalateBasic:
    def test_returns_id(self):
        s = AgentTaskEscalator()
        assert len(s.escalate("t1", "a1", "a2")) > 0
    def test_stores_fields(self):
        s = AgentTaskEscalator()
        rid = s.escalate("t1", "a1", "a2", severity="high")
        e = s.get_escalation(rid)
        assert e["task_id"] == "t1"
        assert e["from_agent"] == "a1"
        assert e["to_agent"] == "a2"
        assert e["severity"] == "high"
    def test_default_severity(self):
        s = AgentTaskEscalator()
        rid = s.escalate("t1", "a1", "a2")
        assert s.get_escalation(rid)["severity"] == "medium"
    def test_with_metadata(self):
        s = AgentTaskEscalator()
        rid = s.escalate("t1", "a1", "a2", metadata={"x": 1})
        assert s.get_escalation(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskEscalator()
        m = {"a": [1]}
        rid = s.escalate("t1", "a1", "a2", metadata=m)
        m["a"].append(2)
        assert s.get_escalation(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskEscalator()
        before = time.time()
        rid = s.escalate("t1", "a1", "a2")
        assert s.get_escalation(rid)["created_at"] >= before
    def test_empty_task_returns_empty(self):
        assert AgentTaskEscalator().escalate("", "a1", "a2") == ""
    def test_empty_from_returns_empty(self):
        assert AgentTaskEscalator().escalate("t1", "", "a2") == ""
    def test_empty_to_returns_empty(self):
        assert AgentTaskEscalator().escalate("t1", "a1", "") == ""

class TestGetEscalation:
    def test_found(self):
        s = AgentTaskEscalator()
        rid = s.escalate("t1", "a1", "a2")
        assert s.get_escalation(rid) is not None
    def test_not_found(self):
        assert AgentTaskEscalator().get_escalation("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskEscalator()
        rid = s.escalate("t1", "a1", "a2")
        assert s.get_escalation(rid) is not s.get_escalation(rid)

class TestGetEscalations:
    def test_all(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.escalate("t2", "a3", "a4")
        assert len(s.get_escalations()) == 2
    def test_filter(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.escalate("t2", "a3", "a4")
        assert len(s.get_escalations(from_agent="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.escalate("t2", "a1", "a3")
        assert s.get_escalations(from_agent="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskEscalator()
        for i in range(10): s.escalate(f"t{i}", "a1", "a2")
        assert len(s.get_escalations(limit=3)) == 3

class TestGetEscalationCount:
    def test_total(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.escalate("t2", "a3", "a4")
        assert s.get_escalation_count() == 2
    def test_filtered(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.escalate("t2", "a3", "a4")
        assert s.get_escalation_count(from_agent="a1") == 1
    def test_empty(self):
        assert AgentTaskEscalator().get_escalation_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskEscalator().get_stats()["total_escalations"] == 0
    def test_with_data(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.escalate("t2", "a3", "a4")
        st = s.get_stats()
        assert st["total_escalations"] == 2
        assert st["unique_agents"] == 4

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskEscalator()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.escalate("t1", "a1", "a2")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskEscalator()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskEscalator().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskEscalator()
        s.MAX_ENTRIES = 5
        for i in range(8): s.escalate(f"t{i}", "a1", "a2")
        assert s.get_escalation_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.reset()
        assert s.get_escalation_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskEscalator()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskEscalator()
        s.escalate("t1", "a1", "a2"); s.reset()
        assert s._state._seq == 0
