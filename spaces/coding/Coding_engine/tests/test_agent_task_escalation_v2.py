import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_escalation_v2 import AgentTaskEscalationV2

class TestBasic:
    def test_returns_id(self):
        assert AgentTaskEscalationV2().escalate_v2("t1", "a1").startswith("atev-")
    def test_fields(self):
        s = AgentTaskEscalationV2(); rid = s.escalate_v2("t1", "a1", level=3)
        e = s.get_escalation(rid)
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["level"] == 3
    def test_default_level(self):
        s = AgentTaskEscalationV2(); rid = s.escalate_v2("t1", "a1")
        assert s.get_escalation(rid)["level"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskEscalationV2(); m = {"x": [1]}
        rid = s.escalate_v2("t1", "a1", metadata=m); m["x"].append(2)
        assert s.get_escalation(rid)["metadata"] == {"x": [1]}
    def test_empty_task(self):
        assert AgentTaskEscalationV2().escalate_v2("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskEscalationV2().escalate_v2("t1", "") == ""
class TestGet:
    def test_found(self):
        s = AgentTaskEscalationV2(); rid = s.escalate_v2("t1", "a1")
        assert s.get_escalation(rid) is not None
    def test_not_found(self):
        assert AgentTaskEscalationV2().get_escalation("nope") is None
    def test_copy(self):
        s = AgentTaskEscalationV2(); rid = s.escalate_v2("t1", "a1")
        assert s.get_escalation(rid) is not s.get_escalation(rid)
class TestList:
    def test_all(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.escalate_v2("t2", "a2")
        assert len(s.get_escalations()) == 2
    def test_filter(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.escalate_v2("t2", "a2")
        assert len(s.get_escalations("a1")) == 1
    def test_newest_first(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.escalate_v2("t2", "a1")
        assert s.get_escalations("a1")[0]["_seq"] > s.get_escalations("a1")[1]["_seq"]
    def test_limit(self):
        s = AgentTaskEscalationV2()
        for i in range(5): s.escalate_v2(f"t{i}", "a1")
        assert len(s.get_escalations(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.escalate_v2("t2", "a2")
        assert s.get_escalation_count() == 2
    def test_filtered(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.escalate_v2("t2", "a2")
        assert s.get_escalation_count("a1") == 1
    def test_empty(self):
        assert AgentTaskEscalationV2().get_escalation_count() == 0
class TestStats:
    def test_data(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.escalate_v2("t2", "a2")
        assert s.get_stats()["total_escalations"] == 2 and s.get_stats()["unique_agents"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskEscalationV2(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.escalate_v2("t1", "a1")
        assert "escalated" in calls
    def test_remove_true(self):
        s = AgentTaskEscalationV2(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskEscalationV2().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = AgentTaskEscalationV2(); s.MAX_ENTRIES = 5
        for i in range(8): s.escalate_v2(f"t{i}", "a1")
        assert s.get_escalation_count() < 8
class TestReset:
    def test_clears(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.reset()
        assert s.get_escalation_count() == 0
    def test_seq(self):
        s = AgentTaskEscalationV2(); s.escalate_v2("t1", "a1"); s.reset()
        assert s._state._seq == 0
