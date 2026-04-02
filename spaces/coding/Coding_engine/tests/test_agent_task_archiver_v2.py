"""Tests for AgentTaskArchiverV2."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_archiver_v2 import AgentTaskArchiverV2


class TestBasic:
    def test_returns_id(self):
        s = AgentTaskArchiverV2()
        rid = s.archive_v2("task-1", "agent-1")
        assert rid.startswith("atav-")

    def test_fields(self):
        s = AgentTaskArchiverV2()
        rid = s.archive_v2("task-1", "agent-1", destination="warm")
        rec = s.get_archive(rid)
        assert rec["task_id"] == "task-1"
        assert rec["agent_id"] == "agent-1"
        assert rec["destination"] == "warm"

    def test_default_destination(self):
        s = AgentTaskArchiverV2()
        rid = s.archive_v2("task-1", "agent-1")
        rec = s.get_archive(rid)
        assert rec["destination"] == "cold"

    def test_metadata_deepcopy(self):
        s = AgentTaskArchiverV2()
        meta = {"k": [1]}
        rid = s.archive_v2("task-1", "agent-1", metadata=meta)
        meta["k"].append(2)
        rec = s.get_archive(rid)
        assert rec["metadata"]["k"] == [1]

    def test_empty_task(self):
        s = AgentTaskArchiverV2()
        assert s.archive_v2("", "agent-1") == ""

    def test_empty_agent(self):
        s = AgentTaskArchiverV2()
        assert s.archive_v2("task-1", "") == ""


class TestGet:
    def test_found(self):
        s = AgentTaskArchiverV2()
        rid = s.archive_v2("task-1", "agent-1")
        assert s.get_archive(rid) is not None

    def test_not_found(self):
        s = AgentTaskArchiverV2()
        assert s.get_archive("nope") is None

    def test_copy(self):
        s = AgentTaskArchiverV2()
        rid = s.archive_v2("task-1", "agent-1")
        r1 = s.get_archive(rid)
        r2 = s.get_archive(rid)
        assert r1 is not r2


class TestList:
    def test_all(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        s.archive_v2("task-2", "agent-2")
        assert len(s.get_archives()) == 2

    def test_filter(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        s.archive_v2("task-2", "agent-2")
        assert len(s.get_archives(agent_id="agent-1")) == 1

    def test_newest_first(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        time.sleep(0.01)
        s.archive_v2("task-2", "agent-1")
        recs = s.get_archives(agent_id="agent-1")
        assert recs[0]["task_id"] == "task-2"


class TestCount:
    def test_total(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        s.archive_v2("task-2", "agent-2")
        assert s.get_archive_count() == 2

    def test_filtered(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        s.archive_v2("task-2", "agent-2")
        assert s.get_archive_count("agent-1") == 1


class TestStats:
    def test_data(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        s.archive_v2("task-2", "agent-2")
        st = s.get_stats()
        assert st["total_archives"] == 2
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskArchiverV2()
        called = []
        s.on_change = lambda a, d=None: called.append(a)
        s.archive_v2("task-1", "agent-1")
        assert len(called) == 1

    def test_remove_true(self):
        s = AgentTaskArchiverV2()
        s._state.callbacks["cb1"] = lambda a, d=None: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = AgentTaskArchiverV2()
        assert s.remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = AgentTaskArchiverV2()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.archive_v2(f"task-{i}", f"agent-{i}")
        assert len(s._state.entries) < 8


class TestReset:
    def test_clears(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        s.on_change = lambda a, d=None: None
        s.reset()
        assert s.get_archive_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = AgentTaskArchiverV2()
        s.archive_v2("task-1", "agent-1")
        s.reset()
        assert s._state._seq == 0
