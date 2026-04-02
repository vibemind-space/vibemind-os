"""Tests for AgentWorkflowCanceler service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_canceler import AgentWorkflowCanceler

class TestIdGeneration:
    def test_prefix(self):
        assert AgentWorkflowCanceler().cancel("a1", "wf1").startswith("awca-")
    def test_unique(self):
        s = AgentWorkflowCanceler()
        ids = {s.cancel("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestCancelBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowCanceler().cancel("a1", "wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowCanceler()
        rid = s.cancel("a1", "wf1", reason="timeout")
        e = s.get_cancellation(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["reason"] == "timeout"
    def test_metadata_deepcopy(self):
        s = AgentWorkflowCanceler()
        m = {"a": [1]}
        rid = s.cancel("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_cancellation(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowCanceler()
        before = time.time()
        assert s.get_cancellation(s.cancel("a1", "wf1"))["created_at"] >= before
    def test_empty_agent(self):
        assert AgentWorkflowCanceler().cancel("", "wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowCanceler().cancel("a1", "") == ""

class TestGetCancellation:
    def test_found(self):
        s = AgentWorkflowCanceler()
        assert s.get_cancellation(s.cancel("a1", "wf1")) is not None
    def test_not_found(self):
        assert AgentWorkflowCanceler().get_cancellation("xxx") is None
    def test_copy(self):
        s = AgentWorkflowCanceler()
        rid = s.cancel("a1", "wf1")
        assert s.get_cancellation(rid) is not s.get_cancellation(rid)

class TestGetCancellations:
    def test_all(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.cancel("a2", "wf2")
        assert len(s.get_cancellations()) == 2
    def test_filter(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.cancel("a2", "wf2")
        assert len(s.get_cancellations(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.cancel("a1", "wf2")
        assert s.get_cancellations(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowCanceler()
        for i in range(10): s.cancel("a1", f"wf{i}")
        assert len(s.get_cancellations(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.cancel("a2", "wf2")
        assert s.get_cancellation_count() == 2
    def test_filtered(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.cancel("a2", "wf2")
        assert s.get_cancellation_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowCanceler().get_cancellation_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentWorkflowCanceler().get_stats()["total_cancellations"] == 0
    def test_data(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.cancel("a2", "wf2")
        assert s.get_stats()["total_cancellations"] == 2
        assert s.get_stats()["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowCanceler()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.cancel("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = AgentWorkflowCanceler()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowCanceler().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowCanceler()
        s.MAX_ENTRIES = 5
        for i in range(8): s.cancel("a1", f"wf{i}")
        assert s.get_cancellation_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.reset()
        assert s.get_cancellation_count() == 0
    def test_callbacks(self):
        s = AgentWorkflowCanceler()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowCanceler()
        s.cancel("a1", "wf1"); s.reset()
        assert s._state._seq == 0
