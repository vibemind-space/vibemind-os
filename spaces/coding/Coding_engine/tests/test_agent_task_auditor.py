import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_auditor import AgentTaskAuditor


class TestBasic:
    def test_returns_id(self):
        s = AgentTaskAuditor()
        rid = s.audit("t1", "a1")
        assert rid.startswith("atau-")

    def test_prefix(self):
        assert AgentTaskAuditor.PREFIX == "atau-"

    def test_fields(self):
        s = AgentTaskAuditor()
        rid = s.audit("t1", "a1", finding="clean")
        e = s.get_audit(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["finding"] == "clean"

    def test_default_finding(self):
        s = AgentTaskAuditor()
        rid = s.audit("t1", "a1")
        assert s.get_audit(rid)["finding"] == ""

    def test_metadata(self):
        s = AgentTaskAuditor()
        rid = s.audit("t1", "a1", metadata={"x": 1})
        assert s.get_audit(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = AgentTaskAuditor()
        m = {"x": [1]}
        rid = s.audit("t1", "a1", metadata=m)
        m["x"].append(2)
        assert s.get_audit(rid)["metadata"] == {"x": [1]}

    def test_created_at(self):
        s = AgentTaskAuditor()
        rid = s.audit("t1", "a1")
        assert s.get_audit(rid)["created_at"] <= time.time()

    def test_empty_task(self):
        assert AgentTaskAuditor().audit("", "a1") == ""

    def test_empty_agent(self):
        assert AgentTaskAuditor().audit("t1", "") == ""


class TestGet:
    def test_found(self):
        s = AgentTaskAuditor()
        rid = s.audit("t1", "a1")
        assert s.get_audit(rid) is not None

    def test_not_found(self):
        assert AgentTaskAuditor().get_audit("nope") is None

    def test_copy(self):
        s = AgentTaskAuditor()
        rid = s.audit("t1", "a1")
        assert s.get_audit(rid) is not s.get_audit(rid)


class TestList:
    def test_all(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.audit("t2", "a2")
        assert len(s.get_audits()) == 2

    def test_filter(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.audit("t2", "a2")
        assert len(s.get_audits("a1")) == 1

    def test_newest_first(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.audit("t2", "a1")
        recs = s.get_audits("a1")
        assert recs[0]["_seq"] > recs[1]["_seq"]

    def test_limit(self):
        s = AgentTaskAuditor()
        for i in range(5):
            s.audit(f"t{i}", "a1")
        assert len(s.get_audits(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.audit("t2", "a2")
        assert s.get_audit_count() == 2

    def test_filtered(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.audit("t2", "a2")
        assert s.get_audit_count("a1") == 1

    def test_empty(self):
        assert AgentTaskAuditor().get_audit_count() == 0


class TestStats:
    def test_empty(self):
        st = AgentTaskAuditor().get_stats()
        assert st["total_audits"] == 0

    def test_data(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.audit("t2", "a2")
        st = s.get_stats()
        assert st["total_audits"] == 2
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskAuditor()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.audit("t1", "a1")
        assert "audited" in calls

    def test_named_callback(self):
        s = AgentTaskAuditor()
        calls = []
        s._state.callbacks["cb1"] = lambda a, d: calls.append(a)
        s.audit("t1", "a1")
        assert "audited" in calls

    def test_remove_true(self):
        s = AgentTaskAuditor()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert AgentTaskAuditor().remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = AgentTaskAuditor()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.audit(f"t{i}", "a1")
        assert s.get_audit_count() < 8


class TestReset:
    def test_clears(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.reset()
        assert s.get_audit_count() == 0

    def test_callbacks(self):
        s = AgentTaskAuditor()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = AgentTaskAuditor()
        s.audit("t1", "a1")
        s.reset()
        assert s._state._seq == 0
