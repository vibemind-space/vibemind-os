"""Tests for AgentTaskCloner."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_cloner import AgentTaskCloner


class TestGenerateId:
    def test_id_has_prefix(self):
        cloner = AgentTaskCloner()
        rid = cloner._generate_id()
        assert rid.startswith("atcl-")

    def test_id_unique(self):
        cloner = AgentTaskCloner()
        ids = {cloner._generate_id() for _ in range(100)}
        assert len(ids) == 100

    def test_id_length(self):
        cloner = AgentTaskCloner()
        rid = cloner._generate_id()
        # PREFIX (5 chars) + 12 hex chars = 17
        assert len(rid) == 17


class TestCloneBasic:
    def test_clone_returns_id(self):
        cloner = AgentTaskCloner()
        rid = cloner.clone("task-1", "agent-1")
        assert rid.startswith("atcl-")

    def test_clone_with_metadata(self):
        cloner = AgentTaskCloner()
        meta = {"priority": "high", "tags": ["a", "b"]}
        rid = cloner.clone("task-1", "agent-1", metadata=meta)
        entry = cloner.get_clone(rid)
        assert entry["metadata"] == {"priority": "high", "tags": ["a", "b"]}

    def test_clone_metadata_is_copy(self):
        cloner = AgentTaskCloner()
        meta = {"key": "value"}
        rid = cloner.clone("task-1", "agent-1", metadata=meta)
        meta["key"] = "changed"
        entry = cloner.get_clone(rid)
        assert entry["metadata"]["key"] == "value"

    def test_clone_count_stored(self):
        cloner = AgentTaskCloner()
        rid = cloner.clone("task-1", "agent-1", clone_count=5)
        entry = cloner.get_clone(rid)
        assert entry["clone_count"] == 5

    def test_clone_default_count(self):
        cloner = AgentTaskCloner()
        rid = cloner.clone("task-1", "agent-1")
        entry = cloner.get_clone(rid)
        assert entry["clone_count"] == 1

    def test_clone_stores_created_at(self):
        cloner = AgentTaskCloner()
        before = time.time()
        rid = cloner.clone("task-1", "agent-1")
        after = time.time()
        entry = cloner.get_clone(rid)
        assert before <= entry["created_at"] <= after


class TestCloneValidation:
    def test_empty_task_id(self):
        cloner = AgentTaskCloner()
        assert cloner.clone("", "agent-1") == ""

    def test_empty_agent_id(self):
        cloner = AgentTaskCloner()
        assert cloner.clone("task-1", "") == ""

    def test_clone_count_zero(self):
        cloner = AgentTaskCloner()
        assert cloner.clone("task-1", "agent-1", clone_count=0) == ""

    def test_clone_count_negative(self):
        cloner = AgentTaskCloner()
        assert cloner.clone("task-1", "agent-1", clone_count=-1) == ""


class TestGetClone:
    def test_found(self):
        cloner = AgentTaskCloner()
        rid = cloner.clone("task-1", "agent-1")
        entry = cloner.get_clone(rid)
        assert entry is not None
        assert entry["task_id"] == "task-1"
        assert entry["agent_id"] == "agent-1"

    def test_not_found(self):
        cloner = AgentTaskCloner()
        assert cloner.get_clone("nonexistent") is None

    def test_returns_copy(self):
        cloner = AgentTaskCloner()
        rid = cloner.clone("task-1", "agent-1")
        entry1 = cloner.get_clone(rid)
        entry2 = cloner.get_clone(rid)
        assert entry1 is not entry2
        assert entry1 == entry2


class TestGetClones:
    def test_no_filter(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        cloner.clone("task-2", "agent-2")
        results = cloner.get_clones()
        assert len(results) == 2

    def test_filter_by_agent(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        cloner.clone("task-2", "agent-2")
        cloner.clone("task-3", "agent-1")
        results = cloner.get_clones(agent_id="agent-1")
        assert len(results) == 2
        assert all(e["agent_id"] == "agent-1" for e in results)

    def test_ordering_newest_first(self):
        cloner = AgentTaskCloner()
        rid1 = cloner.clone("task-1", "agent-1")
        rid2 = cloner.clone("task-2", "agent-1")
        results = cloner.get_clones()
        assert results[0]["record_id"] == rid2
        assert results[1]["record_id"] == rid1

    def test_limit(self):
        cloner = AgentTaskCloner()
        for i in range(10):
            cloner.clone(f"task-{i}", "agent-1")
        results = cloner.get_clones(limit=3)
        assert len(results) == 3

    def test_returns_copies(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        results = cloner.get_clones()
        results[0]["task_id"] = "mutated"
        original = cloner.get_clone(results[0]["record_id"])
        assert original["task_id"] == "task-1"


class TestGetCloneCount:
    def test_total(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        cloner.clone("task-2", "agent-2")
        assert cloner.get_clone_count() == 2

    def test_filtered(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        cloner.clone("task-2", "agent-2")
        cloner.clone("task-3", "agent-1")
        assert cloner.get_clone_count(agent_id="agent-1") == 2
        assert cloner.get_clone_count(agent_id="agent-2") == 1

    def test_empty(self):
        cloner = AgentTaskCloner()
        assert cloner.get_clone_count() == 0


class TestGetStats:
    def test_empty(self):
        cloner = AgentTaskCloner()
        stats = cloner.get_stats()
        assert stats["total_clones"] == 0
        assert stats["unique_agents"] == 0

    def test_with_data(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        cloner.clone("task-2", "agent-2")
        cloner.clone("task-3", "agent-1")
        stats = cloner.get_stats()
        assert stats["total_clones"] == 3
        assert stats["unique_agents"] == 2


class TestOnChangeCallback:
    def test_on_change_setter_getter(self):
        cloner = AgentTaskCloner()
        assert cloner.on_change is None

        def my_cb(action, data):
            pass

        cloner.on_change = my_cb
        assert cloner.on_change is my_cb

    def test_on_change_fires(self):
        cloner = AgentTaskCloner()
        events = []
        cloner.on_change = lambda action, data: events.append((action, data["task_id"]))
        cloner.clone("task-1", "agent-1")
        assert len(events) == 1
        assert events[0] == ("clone", "task-1")

    def test_on_change_clear(self):
        cloner = AgentTaskCloner()
        cloner.on_change = lambda a, d: None
        cloner.on_change = None
        assert cloner.on_change is None

    def test_callback_exception_suppressed(self):
        cloner = AgentTaskCloner()
        cloner.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        # Should not raise
        rid = cloner.clone("task-1", "agent-1")
        assert rid != ""


class TestRemoveCallback:
    def test_remove_existing(self):
        cloner = AgentTaskCloner()
        cloner._state.callbacks["my_cb"] = lambda a, d: None
        assert cloner.remove_callback("my_cb") is True

    def test_remove_nonexistent(self):
        cloner = AgentTaskCloner()
        assert cloner.remove_callback("nope") is False

    def test_remove_stops_firing(self):
        cloner = AgentTaskCloner()
        events = []
        cloner._state.callbacks["tracker"] = lambda a, d: events.append(a)
        cloner.clone("task-1", "agent-1")
        assert len(events) == 1
        cloner.remove_callback("tracker")
        cloner.clone("task-2", "agent-1")
        assert len(events) == 1


class TestPrune:
    def test_prune_at_max(self):
        cloner = AgentTaskCloner()
        cloner.MAX_ENTRIES = 20
        for i in range(25):
            cloner.clone(f"task-{i}", "agent-1")
        assert len(cloner._state.entries) <= 20


class TestReset:
    def test_reset_clears_entries(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        cloner.reset()
        assert cloner.get_clone_count() == 0

    def test_reset_clears_callbacks(self):
        cloner = AgentTaskCloner()
        cloner.on_change = lambda a, d: None
        cloner._state.callbacks["extra"] = lambda a, d: None
        cloner.reset()
        assert cloner.on_change is None
        assert len(cloner._state.callbacks) == 0

    def test_reset_resets_seq(self):
        cloner = AgentTaskCloner()
        cloner.clone("task-1", "agent-1")
        assert cloner._state._seq > 0
        cloner.reset()
        assert cloner._state._seq == 0
