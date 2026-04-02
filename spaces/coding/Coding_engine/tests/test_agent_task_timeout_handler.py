"""Tests for AgentTaskTimeoutHandler."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_timeout_handler import AgentTaskTimeoutHandler


class TestBasic:
    def test_returns_id(self):
        s = AgentTaskTimeoutHandler()
        rid = s.handle_timeout("task-1", "agent-1")
        assert rid.startswith("atth-")

    def test_fields(self):
        s = AgentTaskTimeoutHandler()
        rid = s.handle_timeout("task-1", "agent-1", timeout_seconds=600)
        rec = s.get_timeout(rid)
        assert rec["task_id"] == "task-1"
        assert rec["agent_id"] == "agent-1"
        assert rec["timeout_seconds"] == 600

    def test_default_timeout(self):
        s = AgentTaskTimeoutHandler()
        rid = s.handle_timeout("task-1", "agent-1")
        rec = s.get_timeout(rid)
        assert rec["timeout_seconds"] == 300

    def test_metadata_deepcopy(self):
        s = AgentTaskTimeoutHandler()
        meta = {"k": [1]}
        rid = s.handle_timeout("task-1", "agent-1", metadata=meta)
        meta["k"].append(2)
        rec = s.get_timeout(rid)
        assert rec["metadata"]["k"] == [1]

    def test_empty_task(self):
        s = AgentTaskTimeoutHandler()
        assert s.handle_timeout("", "agent-1") == ""

    def test_empty_agent(self):
        s = AgentTaskTimeoutHandler()
        assert s.handle_timeout("task-1", "") == ""


class TestGet:
    def test_found(self):
        s = AgentTaskTimeoutHandler()
        rid = s.handle_timeout("task-1", "agent-1")
        assert s.get_timeout(rid) is not None

    def test_not_found(self):
        s = AgentTaskTimeoutHandler()
        assert s.get_timeout("nope") is None

    def test_copy(self):
        s = AgentTaskTimeoutHandler()
        rid = s.handle_timeout("task-1", "agent-1")
        r1 = s.get_timeout(rid)
        r2 = s.get_timeout(rid)
        assert r1 is not r2


class TestList:
    def test_all(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        s.handle_timeout("task-2", "agent-2")
        assert len(s.get_timeouts()) == 2

    def test_filter(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        s.handle_timeout("task-2", "agent-2")
        assert len(s.get_timeouts(agent_id="agent-1")) == 1

    def test_newest_first(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        time.sleep(0.01)
        s.handle_timeout("task-2", "agent-1")
        recs = s.get_timeouts(agent_id="agent-1")
        assert recs[0]["task_id"] == "task-2"


class TestCount:
    def test_total(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        s.handle_timeout("task-2", "agent-2")
        assert s.get_timeout_count() == 2

    def test_filtered(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        s.handle_timeout("task-2", "agent-2")
        assert s.get_timeout_count("agent-1") == 1


class TestStats:
    def test_data(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        s.handle_timeout("task-2", "agent-2")
        st = s.get_stats()
        assert st["total_timeouts"] == 2
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskTimeoutHandler()
        called = []
        s.on_change = lambda a, d: called.append(a)
        s.handle_timeout("task-1", "agent-1")
        assert len(called) == 1

    def test_remove_true(self):
        s = AgentTaskTimeoutHandler()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = AgentTaskTimeoutHandler()
        assert s.remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = AgentTaskTimeoutHandler()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.handle_timeout(f"task-{i}", f"agent-{i}")
        assert len(s._state.entries) < 8


class TestReset:
    def test_clears(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        s.on_change = lambda a, d: None
        s.reset()
        assert s.get_timeout_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = AgentTaskTimeoutHandler()
        s.handle_timeout("task-1", "agent-1")
        s.reset()
        assert s._state._seq == 0
