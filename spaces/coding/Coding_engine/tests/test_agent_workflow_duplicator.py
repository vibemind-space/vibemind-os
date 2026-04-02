"""Tests for AgentWorkflowDuplicator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_duplicator import AgentWorkflowDuplicator


class TestBasic:
    """Basic duplication and retrieval."""

    def test_duplicate_returns_id_with_prefix(self):
        svc = AgentWorkflowDuplicator()
        rid = svc.duplicate("a1", "wf1")
        assert rid.startswith("awdu-")
        assert len(rid) > 5

    def test_duplicate_stores_all_fields(self):
        svc = AgentWorkflowDuplicator()
        rid = svc.duplicate("a1", "wf1", copies=3, metadata={"k": "v"})
        entry = svc.get_duplication(rid)
        assert entry is not None
        assert entry["record_id"] == rid
        assert entry["agent_id"] == "a1"
        assert entry["workflow_name"] == "wf1"
        assert entry["copies"] == 3
        assert entry["metadata"] == {"k": "v"}
        assert "created_at" in entry
        assert "updated_at" in entry
        assert "_seq" in entry

    def test_default_copies_is_one(self):
        svc = AgentWorkflowDuplicator()
        rid = svc.duplicate("a1", "wf1")
        entry = svc.get_duplication(rid)
        assert entry["copies"] == 1

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentWorkflowDuplicator()
        rid = svc.duplicate("a1", "wf1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_duplication(rid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_empty_agent_id_returns_empty_string(self):
        svc = AgentWorkflowDuplicator()
        assert svc.duplicate("", "wf1") == ""

    def test_empty_workflow_name_returns_empty_string(self):
        svc = AgentWorkflowDuplicator()
        assert svc.duplicate("a1", "") == ""

    def test_both_empty_returns_empty_string(self):
        svc = AgentWorkflowDuplicator()
        assert svc.duplicate("", "") == ""

    def test_metadata_default_empty_dict(self):
        svc = AgentWorkflowDuplicator()
        rid = svc.duplicate("a1", "wf1")
        entry = svc.get_duplication(rid)
        assert entry["metadata"] == {}


class TestGet:
    """Getting individual duplication records."""

    def test_get_existing(self):
        svc = AgentWorkflowDuplicator()
        rid = svc.duplicate("a1", "wf1")
        entry = svc.get_duplication(rid)
        assert entry is not None
        assert entry["agent_id"] == "a1"

    def test_get_nonexistent(self):
        svc = AgentWorkflowDuplicator()
        assert svc.get_duplication("awdu-nonexistent") is None

    def test_get_returns_copy(self):
        svc = AgentWorkflowDuplicator()
        rid = svc.duplicate("a1", "wf1")
        entry = svc.get_duplication(rid)
        entry["agent_id"] = "mutated"
        original = svc.get_duplication(rid)
        assert original["agent_id"] == "a1"


class TestList:
    """Querying multiple duplication records."""

    def test_get_all(self):
        svc = AgentWorkflowDuplicator()
        svc.duplicate("a1", "wf1")
        svc.duplicate("a2", "wf2")
        results = svc.get_duplications()
        assert len(results) == 2

    def test_filter_by_agent_id(self):
        svc = AgentWorkflowDuplicator()
        svc.duplicate("a1", "wf1")
        svc.duplicate("a2", "wf2")
        svc.duplicate("a1", "wf3")
        results = svc.get_duplications(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_newest_first(self):
        svc = AgentWorkflowDuplicator()
        id1 = svc.duplicate("a1", "wf1")
        id2 = svc.duplicate("a1", "wf2")
        results = svc.get_duplications()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_respects_limit(self):
        svc = AgentWorkflowDuplicator()
        for i in range(10):
            svc.duplicate("a1", f"wf{i}")
        results = svc.get_duplications(limit=3)
        assert len(results) == 3

    def test_empty(self):
        svc = AgentWorkflowDuplicator()
        results = svc.get_duplications()
        assert results == []


class TestCount:
    """Counting duplication records."""

    def test_count_all(self):
        svc = AgentWorkflowDuplicator()
        svc.duplicate("a1", "wf1")
        svc.duplicate("a2", "wf2")
        assert svc.get_duplication_count() == 2

    def test_count_by_agent(self):
        svc = AgentWorkflowDuplicator()
        svc.duplicate("a1", "wf1")
        svc.duplicate("a2", "wf2")
        svc.duplicate("a1", "wf3")
        assert svc.get_duplication_count(agent_id="a1") == 2
        assert svc.get_duplication_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentWorkflowDuplicator()
        assert svc.get_duplication_count() == 0


class TestStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentWorkflowDuplicator()
        stats = svc.get_stats()
        assert stats["total_duplications"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentWorkflowDuplicator()
        svc.duplicate("a1", "wf1")
        svc.duplicate("a2", "wf2")
        svc.duplicate("a1", "wf3")
        stats = svc.get_stats()
        assert stats["total_duplications"] == 3
        assert stats["unique_agents"] == 2

    def test_stats_returns_dict(self):
        svc = AgentWorkflowDuplicator()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_duplicate(self):
        events = []
        svc = AgentWorkflowDuplicator()
        svc._on_change = lambda action, data: events.append((action, data))
        svc.duplicate("a1", "wf1")
        assert len(events) == 1
        assert events[0][0] == "duplicated"

    def test_on_change_receives_data_dict(self):
        events = []
        svc = AgentWorkflowDuplicator()
        svc._on_change = lambda action, data: events.append((action, data))
        svc.duplicate("a1", "wf1", copies=5)
        assert events[0][1]["action"] == "duplicated"
        assert events[0][1]["agent_id"] == "a1"
        assert events[0][1]["copies"] == 5

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentWorkflowDuplicator()
        svc._state.callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.duplicate("a1", "wf1")
        assert "duplicated" in events

    def test_on_change_exception_silenced(self):
        svc = AgentWorkflowDuplicator()
        svc._on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = svc.duplicate("a1", "wf1")
        assert rid.startswith("awdu-")

    def test_named_callback_exception_silenced(self):
        svc = AgentWorkflowDuplicator()
        svc._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("x"))
        rid = svc.duplicate("a1", "wf1")
        assert rid.startswith("awdu-")


class TestPrune:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_limits_entries(self):
        svc = AgentWorkflowDuplicator()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.duplicate("a1", f"wf{i}"))
        assert svc.get_duplication_count() <= 5

    def test_prune_removes_oldest(self):
        svc = AgentWorkflowDuplicator()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.duplicate("a1", f"wf{i}"))
        assert svc.get_duplication(ids[0]) is None

    def test_prune_keeps_newest(self):
        svc = AgentWorkflowDuplicator()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.duplicate("a1", f"wf{i}"))
        assert svc.get_duplication(ids[-1]) is not None


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowDuplicator()
        svc.duplicate("a1", "wf1")
        svc.reset()
        assert svc.get_duplication_count() == 0
        assert svc.get_stats()["total_duplications"] == 0

    def test_reset_clears_on_change(self):
        svc = AgentWorkflowDuplicator()
        svc._on_change = lambda a, d: None
        svc.reset()
        assert svc._on_change is None

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowDuplicator()
        svc._state.callbacks["cb1"] = lambda a, d: None
        svc.reset()
        assert len(svc._state.callbacks) == 0

    def test_reset_allows_new_duplications(self):
        svc = AgentWorkflowDuplicator()
        svc.duplicate("a1", "wf1")
        svc.reset()
        rid = svc.duplicate("a2", "wf2")
        assert rid.startswith("awdu-")
        assert svc.get_duplication_count() == 1


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentWorkflowDuplicator()
        ids = set()
        for i in range(50):
            ids.add(svc.duplicate("a1", f"wf{i}"))
        assert len(ids) == 50
