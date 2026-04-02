"""Tests for AgentTaskSuspenderV2."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_suspender_v2 import AgentTaskSuspenderV2

class TestBasic:
    def test_returns_id(self):
        s = AgentTaskSuspenderV2()
        assert s.suspend_v2("task-1", "agent-1").startswith("atsv-")
    def test_fields(self):
        s = AgentTaskSuspenderV2()
        rid = s.suspend_v2("task-1", "agent-1", reason="overload")
        rec = s.get_suspension(rid)
        assert rec["task_id"] == "task-1"
        assert rec["agent_id"] == "agent-1"
        assert rec["reason"] == "overload"
    def test_default_reason(self):
        s = AgentTaskSuspenderV2()
        rid = s.suspend_v2("task-1", "agent-1")
        assert s.get_suspension(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = AgentTaskSuspenderV2()
        m = {"k": [1]}
        rid = s.suspend_v2("task-1", "agent-1", metadata=m)
        m["k"].append(2)
        assert s.get_suspension(rid)["metadata"]["k"] == [1]
    def test_empty_task(self):
        assert AgentTaskSuspenderV2().suspend_v2("", "agent-1") == ""
    def test_empty_agent(self):
        assert AgentTaskSuspenderV2().suspend_v2("task-1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskSuspenderV2()
        rid = s.suspend_v2("task-1", "agent-1")
        assert s.get_suspension(rid) is not None
    def test_not_found(self):
        assert AgentTaskSuspenderV2().get_suspension("nope") is None
    def test_copy(self):
        s = AgentTaskSuspenderV2()
        rid = s.suspend_v2("task-1", "agent-1")
        assert s.get_suspension(rid) is not s.get_suspension(rid)

class TestList:
    def test_all(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1"); s.suspend_v2("task-2", "agent-2")
        assert len(s.get_suspensions()) == 2
    def test_filter(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1"); s.suspend_v2("task-2", "agent-2")
        assert len(s.get_suspensions(agent_id="agent-1")) == 1
    def test_newest_first(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1"); time.sleep(0.01); s.suspend_v2("task-2", "agent-1")
        assert s.get_suspensions(agent_id="agent-1")[0]["task_id"] == "task-2"

class TestCount:
    def test_total(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1"); s.suspend_v2("task-2", "agent-2")
        assert s.get_suspension_count() == 2
    def test_filtered(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1"); s.suspend_v2("task-2", "agent-2")
        assert s.get_suspension_count("agent-1") == 1

class TestStats:
    def test_data(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1"); s.suspend_v2("task-2", "agent-2")
        st = s.get_stats()
        assert st["total_suspensions"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskSuspenderV2()
        called = []
        s.on_change = lambda a, d: called.append(a)
        s.suspend_v2("task-1", "agent-1")
        assert len(called) == 1
    def test_remove_true(self):
        s = AgentTaskSuspenderV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskSuspenderV2().remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskSuspenderV2()
        s.MAX_ENTRIES = 5
        for i in range(8): s.suspend_v2(f"task-{i}", f"agent-{i}")
        assert len(s._state.entries) < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1")
        s.on_change = lambda a, d: None
        s.reset()
        assert s.get_suspension_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskSuspenderV2()
        s.suspend_v2("task-1", "agent-1")
        s.reset()
        assert s._state._seq == 0
