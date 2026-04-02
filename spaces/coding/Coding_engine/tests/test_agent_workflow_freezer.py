import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_freezer import AgentWorkflowFreezer


class TestBasic:
    def test_returns_id(self):
        s = AgentWorkflowFreezer()
        rid = s.freeze("a1", "wf1")
        assert rid.startswith("awfz-")

    def test_prefix(self):
        assert AgentWorkflowFreezer.PREFIX == "awfz-"

    def test_fields(self):
        s = AgentWorkflowFreezer()
        rid = s.freeze("a1", "wf1", reason="maintenance")
        e = s.get_freeze(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["reason"] == "maintenance"

    def test_default_reason(self):
        s = AgentWorkflowFreezer()
        rid = s.freeze("a1", "wf1")
        assert s.get_freeze(rid)["reason"] == ""

    def test_metadata(self):
        s = AgentWorkflowFreezer()
        rid = s.freeze("a1", "wf1", metadata={"x": 1})
        assert s.get_freeze(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = AgentWorkflowFreezer()
        m = {"x": [1]}
        rid = s.freeze("a1", "wf1", metadata=m)
        m["x"].append(2)
        assert s.get_freeze(rid)["metadata"] == {"x": [1]}

    def test_created_at(self):
        s = AgentWorkflowFreezer()
        rid = s.freeze("a1", "wf1")
        assert s.get_freeze(rid)["created_at"] <= time.time()

    def test_empty_agent(self):
        assert AgentWorkflowFreezer().freeze("", "wf1") == ""

    def test_empty_workflow(self):
        assert AgentWorkflowFreezer().freeze("a1", "") == ""


class TestGet:
    def test_found(self):
        s = AgentWorkflowFreezer()
        rid = s.freeze("a1", "wf1")
        assert s.get_freeze(rid) is not None

    def test_not_found(self):
        assert AgentWorkflowFreezer().get_freeze("nope") is None

    def test_copy(self):
        s = AgentWorkflowFreezer()
        rid = s.freeze("a1", "wf1")
        assert s.get_freeze(rid) is not s.get_freeze(rid)


class TestList:
    def test_all(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.freeze("a2", "wf2")
        assert len(s.get_freezes()) == 2

    def test_filter(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.freeze("a2", "wf2")
        assert len(s.get_freezes("a1")) == 1

    def test_newest_first(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.freeze("a1", "wf2")
        recs = s.get_freezes("a1")
        assert recs[0]["_seq"] > recs[1]["_seq"]

    def test_limit(self):
        s = AgentWorkflowFreezer()
        for i in range(5):
            s.freeze("a1", f"wf{i}")
        assert len(s.get_freezes(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.freeze("a2", "wf2")
        assert s.get_freeze_count() == 2

    def test_filtered(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.freeze("a2", "wf2")
        assert s.get_freeze_count("a1") == 1

    def test_empty(self):
        assert AgentWorkflowFreezer().get_freeze_count() == 0


class TestStats:
    def test_empty(self):
        st = AgentWorkflowFreezer().get_stats()
        assert st["total_freezes"] == 0

    def test_data(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.freeze("a2", "wf2")
        st = s.get_stats()
        assert st["total_freezes"] == 2
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowFreezer()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.freeze("a1", "wf1")
        assert "frozen" in calls

    def test_named_callback(self):
        s = AgentWorkflowFreezer()
        calls = []
        s._state.callbacks["cb1"] = lambda a, d: calls.append(a)
        s.freeze("a1", "wf1")
        assert "frozen" in calls

    def test_remove_true(self):
        s = AgentWorkflowFreezer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert AgentWorkflowFreezer().remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = AgentWorkflowFreezer()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.freeze("a1", f"wf{i}")
        assert s.get_freeze_count() < 8


class TestReset:
    def test_clears(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.reset()
        assert s.get_freeze_count() == 0

    def test_callbacks(self):
        s = AgentWorkflowFreezer()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = AgentWorkflowFreezer()
        s.freeze("a1", "wf1")
        s.reset()
        assert s._state._seq == 0
