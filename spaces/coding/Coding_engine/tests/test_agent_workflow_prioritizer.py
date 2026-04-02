import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_prioritizer import AgentWorkflowPrioritizer


class TestBasic:
    def test_returns_id(self):
        s = AgentWorkflowPrioritizer()
        assert s.prioritize("a1", "wf1").startswith("awpr-")

    def test_fields(self):
        s = AgentWorkflowPrioritizer()
        rid = s.prioritize("a1", "wf1", priority=10)
        e = s.get_priority(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["priority"] == 10

    def test_default_priority(self):
        s = AgentWorkflowPrioritizer()
        rid = s.prioritize("a1", "wf1")
        assert s.get_priority(rid)["priority"] == 5

    def test_metadata(self):
        s = AgentWorkflowPrioritizer()
        rid = s.prioritize("a1", "wf1", metadata={"x": 1})
        assert s.get_priority(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = AgentWorkflowPrioritizer()
        m = {"x": [1]}
        rid = s.prioritize("a1", "wf1", metadata=m)
        m["x"].append(2)
        assert s.get_priority(rid)["metadata"] == {"x": [1]}

    def test_empty_agent(self):
        assert AgentWorkflowPrioritizer().prioritize("", "wf1") == ""

    def test_empty_workflow(self):
        assert AgentWorkflowPrioritizer().prioritize("a1", "") == ""


class TestGet:
    def test_found(self):
        s = AgentWorkflowPrioritizer()
        rid = s.prioritize("a1", "wf1")
        assert s.get_priority(rid) is not None

    def test_not_found(self):
        assert AgentWorkflowPrioritizer().get_priority("nope") is None

    def test_copy(self):
        s = AgentWorkflowPrioritizer()
        rid = s.prioritize("a1", "wf1")
        assert s.get_priority(rid) is not s.get_priority(rid)


class TestList:
    def test_all(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.prioritize("a2", "wf2")
        assert len(s.get_priorities()) == 2

    def test_filter(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.prioritize("a2", "wf2")
        assert len(s.get_priorities("a1")) == 1

    def test_newest_first(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.prioritize("a1", "wf2")
        assert s.get_priorities("a1")[0]["_seq"] > s.get_priorities("a1")[1]["_seq"]

    def test_limit(self):
        s = AgentWorkflowPrioritizer()
        for i in range(5): s.prioritize("a1", f"wf{i}")
        assert len(s.get_priorities(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.prioritize("a2", "wf2")
        assert s.get_priority_count() == 2

    def test_filtered(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.prioritize("a2", "wf2")
        assert s.get_priority_count("a1") == 1

    def test_empty(self):
        assert AgentWorkflowPrioritizer().get_priority_count() == 0


class TestStats:
    def test_empty(self):
        assert AgentWorkflowPrioritizer().get_stats()["total_priorities"] == 0

    def test_data(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.prioritize("a2", "wf2")
        st = s.get_stats()
        assert st["total_priorities"] == 2
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowPrioritizer()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.prioritize("a1", "wf1")
        assert "prioritized" in calls

    def test_remove_true(self):
        s = AgentWorkflowPrioritizer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert AgentWorkflowPrioritizer().remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = AgentWorkflowPrioritizer(); s.MAX_ENTRIES = 5
        for i in range(8): s.prioritize("a1", f"wf{i}")
        assert s.get_priority_count() < 8


class TestReset:
    def test_clears(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.reset()
        assert s.get_priority_count() == 0

    def test_callbacks(self):
        s = AgentWorkflowPrioritizer()
        s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = AgentWorkflowPrioritizer()
        s.prioritize("a1", "wf1"); s.reset()
        assert s._state._seq == 0
