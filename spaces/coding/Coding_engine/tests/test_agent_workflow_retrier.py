"""Tests for AgentWorkflowRetrier service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_retrier import AgentWorkflowRetrier


class TestIdGeneration:
    def test_prefix(self):
        assert AgentWorkflowRetrier().retry("a1", "wf1").startswith("awrt-")

    def test_unique(self):
        s = AgentWorkflowRetrier()
        ids = {s.retry("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

    def test_id_length(self):
        rid = AgentWorkflowRetrier().retry("a1", "wf1")
        assert len(rid) == len("awrt-") + 12


class TestRetryBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowRetrier().retry("a1", "wf1")) > 0

    def test_stores_fields(self):
        s = AgentWorkflowRetrier()
        rid = s.retry("a1", "wf1", attempt=3)
        e = s.get_retry(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["attempt"] == 3

    def test_default_attempt(self):
        s = AgentWorkflowRetrier()
        rid = s.retry("a1", "wf1")
        assert s.get_retry(rid)["attempt"] == 1

    def test_metadata_deepcopy(self):
        s = AgentWorkflowRetrier()
        m = {"a": [1]}
        rid = s.retry("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_retry(rid)["metadata"]["a"] == [1]

    def test_metadata_default_empty(self):
        s = AgentWorkflowRetrier()
        rid = s.retry("a1", "wf1")
        assert s.get_retry(rid)["metadata"] == {}

    def test_created_at(self):
        s = AgentWorkflowRetrier()
        before = time.time()
        assert s.get_retry(s.retry("a1", "wf1"))["created_at"] >= before

    def test_empty_agent(self):
        assert AgentWorkflowRetrier().retry("", "wf1") == ""

    def test_empty_workflow(self):
        assert AgentWorkflowRetrier().retry("a1", "") == ""

    def test_both_empty(self):
        assert AgentWorkflowRetrier().retry("", "") == ""


class TestGetRetry:
    def test_found(self):
        s = AgentWorkflowRetrier()
        assert s.get_retry(s.retry("a1", "wf1")) is not None

    def test_not_found(self):
        assert AgentWorkflowRetrier().get_retry("xxx") is None

    def test_copy(self):
        s = AgentWorkflowRetrier()
        rid = s.retry("a1", "wf1")
        assert s.get_retry(rid) is not s.get_retry(rid)


class TestGetRetries:
    def test_all(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.retry("a2", "wf2")
        assert len(s.get_retries()) == 2

    def test_filter(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.retry("a2", "wf2")
        assert len(s.get_retries(agent_id="a1")) == 1

    def test_newest_first(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.retry("a1", "wf2")
        assert s.get_retries(agent_id="a1")[0]["workflow_name"] == "wf2"

    def test_limit(self):
        s = AgentWorkflowRetrier()
        for i in range(10):
            s.retry("a1", f"wf{i}")
        assert len(s.get_retries(limit=3)) == 3

    def test_default_limit(self):
        s = AgentWorkflowRetrier()
        for i in range(60):
            s.retry("a1", f"wf{i}")
        assert len(s.get_retries()) == 50

    def test_empty(self):
        assert AgentWorkflowRetrier().get_retries() == []


class TestCount:
    def test_total(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.retry("a2", "wf2")
        assert s.get_retry_count() == 2

    def test_filtered(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.retry("a2", "wf2")
        assert s.get_retry_count(agent_id="a1") == 1

    def test_empty(self):
        assert AgentWorkflowRetrier().get_retry_count() == 0


class TestStats:
    def test_empty(self):
        st = AgentWorkflowRetrier().get_stats()
        assert st["total_retries"] == 0
        assert st["unique_agents"] == 0

    def test_data(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.retry("a2", "wf2")
        assert s.get_stats()["total_retries"] == 2
        assert s.get_stats()["unique_agents"] == 2

    def test_same_agent(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.retry("a1", "wf2")
        assert s.get_stats()["unique_agents"] == 1


class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowRetrier()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.retry("a1", "wf1")
        assert len(evts) >= 1

    def test_on_change_event_name(self):
        s = AgentWorkflowRetrier()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.retry("a1", "wf1")
        assert "retried" in evts

    def test_on_change_getter(self):
        s = AgentWorkflowRetrier()
        assert s.on_change is None
        cb = lambda a, d: None
        s.on_change = cb
        assert s.on_change is cb

    def test_registered_callback(self):
        s = AgentWorkflowRetrier()
        evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.retry("a1", "wf1")
        assert "retried" in evts

    def test_remove_true(self):
        s = AgentWorkflowRetrier()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert AgentWorkflowRetrier().remove_callback("x") is False

    def test_remove_actually_removes(self):
        s = AgentWorkflowRetrier()
        s._state.callbacks["cb1"] = lambda a, d: None
        s.remove_callback("cb1")
        assert "cb1" not in s._state.callbacks

    def test_callback_exception_ignored(self):
        s = AgentWorkflowRetrier()
        s._state.callbacks["bad"] = lambda a, d: 1 / 0
        s.retry("a1", "wf1")  # should not raise


class TestPrune:
    def test_prune(self):
        s = AgentWorkflowRetrier()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.retry("a1", f"wf{i}")
        assert s.get_retry_count() < 8

    def test_prune_removes_oldest(self):
        s = AgentWorkflowRetrier()
        s.MAX_ENTRIES = 4
        first = s.retry("a1", "wf_first")
        for i in range(5):
            s.retry("a1", f"wf{i}")
        assert s.get_retry(first) is None


class TestReset:
    def test_clears(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.reset()
        assert s.get_retry_count() == 0

    def test_callbacks(self):
        s = AgentWorkflowRetrier()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = AgentWorkflowRetrier()
        s.retry("a1", "wf1"); s.reset()
        assert s._state._seq == 0

    def test_state_callbacks_cleared(self):
        s = AgentWorkflowRetrier()
        s._state.callbacks["cb1"] = lambda a, d: None
        s.reset()
        assert len(s._state.callbacks) == 0
