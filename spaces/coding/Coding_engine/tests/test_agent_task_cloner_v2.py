"""Tests for AgentTaskClonerV2."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_cloner_v2 import AgentTaskClonerV2


class TestGenerateId:
    def test_id_has_prefix_and_length(self):
        cloner = AgentTaskClonerV2()
        rid = cloner._generate_id()
        assert rid.startswith("atcl-")
        assert len(rid) == 17  # PREFIX (5) + 12 hex

    def test_id_unique(self):
        cloner = AgentTaskClonerV2()
        ids = {cloner._generate_id() for _ in range(100)}
        assert len(ids) == 100


class TestCloneV2Basic:
    def test_clone_returns_id(self):
        cloner = AgentTaskClonerV2()
        rid = cloner.clone_v2("task-1", "agent-1")
        assert rid.startswith("atcl-")

    def test_clone_with_metadata_is_independent_copy(self):
        cloner = AgentTaskClonerV2()
        meta = {"priority": "high", "tags": ["a", "b"]}
        rid = cloner.clone_v2("task-1", "agent-1", metadata=meta)
        meta["priority"] = "low"
        entry = cloner.get_clone(rid)
        assert entry["metadata"] == {"priority": "high", "tags": ["a", "b"]}

    def test_clone_copies_stored(self):
        cloner = AgentTaskClonerV2()
        rid = cloner.clone_v2("task-1", "agent-1", copies=5)
        entry = cloner.get_clone(rid)
        assert entry["copies"] == 5

    def test_clone_default_copies(self):
        cloner = AgentTaskClonerV2()
        rid = cloner.clone_v2("task-1", "agent-1")
        entry = cloner.get_clone(rid)
        assert entry["copies"] == 1

    def test_clone_stores_created_at(self):
        cloner = AgentTaskClonerV2()
        before = time.time()
        rid = cloner.clone_v2("task-1", "agent-1")
        after = time.time()
        entry = cloner.get_clone(rid)
        assert before <= entry["created_at"] <= after


class TestCloneV2Validation:
    def test_empty_task_id_or_agent_id(self):
        cloner = AgentTaskClonerV2()
        assert cloner.clone_v2("", "agent-1") == ""
        assert cloner.clone_v2("task-1", "") == ""


class TestGetClone:
    def test_found(self):
        cloner = AgentTaskClonerV2()
        rid = cloner.clone_v2("task-1", "agent-1")
        entry = cloner.get_clone(rid)
        assert entry is not None
        assert entry["task_id"] == "task-1"
        assert entry["agent_id"] == "agent-1"

    def test_not_found(self):
        cloner = AgentTaskClonerV2()
        assert cloner.get_clone("nonexistent") is None

    def test_returns_copy(self):
        cloner = AgentTaskClonerV2()
        rid = cloner.clone_v2("task-1", "agent-1")
        entry1 = cloner.get_clone(rid)
        entry2 = cloner.get_clone(rid)
        assert entry1 is not entry2
        assert entry1 == entry2


class TestGetClones:
    def test_filter_by_agent(self):
        cloner = AgentTaskClonerV2()
        cloner.clone_v2("task-1", "agent-1")
        cloner.clone_v2("task-2", "agent-2")
        cloner.clone_v2("task-3", "agent-1")
        results = cloner.get_clones(agent_id="agent-1")
        assert len(results) == 2
        assert all(e["agent_id"] == "agent-1" for e in results)

    def test_ordering_newest_first(self):
        cloner = AgentTaskClonerV2()
        rid1 = cloner.clone_v2("task-1", "agent-1")
        rid2 = cloner.clone_v2("task-2", "agent-1")
        results = cloner.get_clones()
        assert results[0]["record_id"] == rid2
        assert results[1]["record_id"] == rid1

    def test_limit(self):
        cloner = AgentTaskClonerV2()
        for i in range(10):
            cloner.clone_v2(f"task-{i}", "agent-1")
        results = cloner.get_clones(limit=3)
        assert len(results) == 3


class TestGetCloneCount:
    def test_empty_total_and_filtered(self):
        cloner = AgentTaskClonerV2()
        assert cloner.get_clone_count() == 0
        cloner.clone_v2("task-1", "agent-1")
        cloner.clone_v2("task-2", "agent-2")
        cloner.clone_v2("task-3", "agent-1")
        assert cloner.get_clone_count() == 3
        assert cloner.get_clone_count(agent_id="agent-1") == 2
        assert cloner.get_clone_count(agent_id="agent-2") == 1


class TestGetStats:
    def test_empty_and_with_data(self):
        cloner = AgentTaskClonerV2()
        stats = cloner.get_stats()
        assert stats["total_clones"] == 0
        assert stats["unique_agents"] == 0

        cloner.clone_v2("task-1", "agent-1")
        cloner.clone_v2("task-2", "agent-2")
        cloner.clone_v2("task-3", "agent-1")
        stats = cloner.get_stats()
        assert stats["total_clones"] == 3
        assert stats["unique_agents"] == 2


class TestFireAndCallbacks:
    def test_fire_sends_action_in_data(self):
        cloner = AgentTaskClonerV2()
        events = []
        cloner.on_change = lambda action, data: events.append(data)
        cloner.clone_v2("task-1", "agent-1")
        assert len(events) == 1
        assert events[0]["action"] == "clone_v2"
        assert events[0]["task_id"] == "task-1"

    def test_on_change_set_get_clear(self):
        cloner = AgentTaskClonerV2()
        assert cloner.on_change is None
        cb = lambda a, d: None
        cloner.on_change = cb
        assert cloner.on_change is cb
        cloner.on_change = None
        assert cloner.on_change is None

    def test_callback_exception_suppressed(self):
        cloner = AgentTaskClonerV2()
        cloner.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = cloner.clone_v2("task-1", "agent-1")
        assert rid != ""

    def test_remove_callback(self):
        cloner = AgentTaskClonerV2()
        cloner._state.callbacks["my_cb"] = lambda a, d: None
        assert cloner.remove_callback("my_cb") is True
        assert cloner.remove_callback("nope") is False


class TestPrune:
    def test_prune_at_max(self):
        cloner = AgentTaskClonerV2()
        cloner.MAX_ENTRIES = 20
        for i in range(25):
            cloner.clone_v2(f"task-{i}", "agent-1")
        assert len(cloner._state.entries) <= 20


class TestReset:
    def test_reset_clears_all(self):
        cloner = AgentTaskClonerV2()
        cloner.clone_v2("task-1", "agent-1")
        cloner.on_change = lambda a, d: None
        cloner.reset()
        assert cloner.get_clone_count() == 0
        assert cloner.on_change is None
        assert len(cloner._state.callbacks) == 0
        assert cloner._state._seq == 0
