import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_verifier import AgentTaskVerifier


class TestBasic:
    def test_returns_id(self):
        s = AgentTaskVerifier()
        assert s.verify("t1", "a1").startswith("atve-")

    def test_fields(self):
        s = AgentTaskVerifier()
        rid = s.verify("t1", "a1", verdict="failed")
        e = s.get_verification(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["verdict"] == "failed"

    def test_default_verdict(self):
        s = AgentTaskVerifier()
        rid = s.verify("t1", "a1")
        assert s.get_verification(rid)["verdict"] == "passed"

    def test_metadata(self):
        s = AgentTaskVerifier()
        rid = s.verify("t1", "a1", metadata={"x": 1})
        assert s.get_verification(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = AgentTaskVerifier()
        m = {"x": [1]}
        rid = s.verify("t1", "a1", metadata=m)
        m["x"].append(2)
        assert s.get_verification(rid)["metadata"] == {"x": [1]}

    def test_empty_task(self):
        assert AgentTaskVerifier().verify("", "a1") == ""

    def test_empty_agent(self):
        assert AgentTaskVerifier().verify("t1", "") == ""


class TestGet:
    def test_found(self):
        s = AgentTaskVerifier()
        rid = s.verify("t1", "a1")
        assert s.get_verification(rid) is not None

    def test_not_found(self):
        assert AgentTaskVerifier().get_verification("nope") is None

    def test_copy(self):
        s = AgentTaskVerifier()
        rid = s.verify("t1", "a1")
        assert s.get_verification(rid) is not s.get_verification(rid)


class TestList:
    def test_all(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.verify("t2", "a2")
        assert len(s.get_verifications()) == 2

    def test_filter(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.verify("t2", "a2")
        assert len(s.get_verifications("a1")) == 1

    def test_newest_first(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.verify("t2", "a1")
        assert s.get_verifications("a1")[0]["_seq"] > s.get_verifications("a1")[1]["_seq"]

    def test_limit(self):
        s = AgentTaskVerifier()
        for i in range(5): s.verify(f"t{i}", "a1")
        assert len(s.get_verifications(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.verify("t2", "a2")
        assert s.get_verification_count() == 2

    def test_filtered(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.verify("t2", "a2")
        assert s.get_verification_count("a1") == 1

    def test_empty(self):
        assert AgentTaskVerifier().get_verification_count() == 0


class TestStats:
    def test_empty(self):
        assert AgentTaskVerifier().get_stats()["total_verifications"] == 0

    def test_data(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.verify("t2", "a2")
        st = s.get_stats()
        assert st["total_verifications"] == 2
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskVerifier()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.verify("t1", "a1")
        assert "verified" in calls

    def test_remove_true(self):
        s = AgentTaskVerifier()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert AgentTaskVerifier().remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = AgentTaskVerifier(); s.MAX_ENTRIES = 5
        for i in range(8): s.verify(f"t{i}", "a1")
        assert s.get_verification_count() < 8


class TestReset:
    def test_clears(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.reset()
        assert s.get_verification_count() == 0

    def test_callbacks(self):
        s = AgentTaskVerifier()
        s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = AgentTaskVerifier()
        s.verify("t1", "a1"); s.reset()
        assert s._state._seq == 0
