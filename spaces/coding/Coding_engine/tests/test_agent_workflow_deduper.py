"""Tests for AgentWorkflowDeduper service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_deduper import AgentWorkflowDeduper


class TestPrefix:
    """ID prefix validation."""

    def test_id_has_correct_prefix(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "hash1")
        assert rid.startswith("awdd-")

    def test_prefix_constant(self):
        assert AgentWorkflowDeduper.PREFIX == "awdd-"


class TestDedupBasic:
    """Basic dedup and retrieval."""

    def test_dedup_returns_id(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "hash1")
        assert rid.startswith("awdd-")
        assert len(rid) > 5

    def test_dedup_stores_agent_id(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("agent-x", "wf1", "hash1")
        entry = svc.get_dedup(rid)
        assert entry["agent_id"] == "agent-x"

    def test_dedup_stores_workflow_name(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "my-workflow", "hash1")
        entry = svc.get_dedup(rid)
        assert entry["workflow_name"] == "my-workflow"

    def test_dedup_stores_content_hash(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "abc123")
        entry = svc.get_dedup(rid)
        assert entry["content_hash"] == "abc123"

    def test_dedup_has_created_at(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "hash1")
        entry = svc.get_dedup(rid)
        assert "created_at" in entry
        assert isinstance(entry["created_at"], float)

    def test_unique_ids(self):
        svc = AgentWorkflowDeduper()
        ids = set()
        for i in range(50):
            ids.add(svc.dedup("a1", f"wf{i}", f"hash{i}"))
        assert len(ids) == 50


class TestMetadata:
    """Metadata handling."""

    def test_metadata_stored(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "hash1", metadata={"key": "val"})
        entry = svc.get_dedup(rid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_default_empty(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "hash1")
        entry = svc.get_dedup(rid)
        assert entry["metadata"] == {}

    def test_metadata_not_shared(self):
        meta = {"nested": {"x": 1}}
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "hash1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_dedup(rid)
        assert entry["metadata"]["nested"]["x"] == 1


class TestGetDedup:
    """Single record retrieval."""

    def test_get_found(self):
        svc = AgentWorkflowDeduper()
        rid = svc.dedup("a1", "wf1", "hash1")
        entry = svc.get_dedup(rid)
        assert entry is not None
        assert entry["record_id"] == rid

    def test_get_not_found(self):
        svc = AgentWorkflowDeduper()
        assert svc.get_dedup("awdd-nonexistent") is None


class TestGetDedups:
    """Querying multiple dedup records."""

    def test_list_all(self):
        svc = AgentWorkflowDeduper()
        svc.dedup("a1", "wf1", "h1")
        svc.dedup("a2", "wf2", "h2")
        results = svc.get_dedups()
        assert len(results) == 2

    def test_filter_by_agent(self):
        svc = AgentWorkflowDeduper()
        svc.dedup("a1", "wf1", "h1")
        svc.dedup("a2", "wf2", "h2")
        svc.dedup("a1", "wf3", "h3")
        results = svc.get_dedups(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_order_newest_first(self):
        svc = AgentWorkflowDeduper()
        id1 = svc.dedup("a1", "wf1", "h1")
        id2 = svc.dedup("a1", "wf2", "h2")
        results = svc.get_dedups()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_respects_limit(self):
        svc = AgentWorkflowDeduper()
        for i in range(10):
            svc.dedup("a1", f"wf{i}", f"h{i}")
        results = svc.get_dedups(limit=3)
        assert len(results) == 3

    def test_empty_list(self):
        svc = AgentWorkflowDeduper()
        results = svc.get_dedups()
        assert results == []


class TestGetDedupCount:
    """Counting dedup records."""

    def test_count_all(self):
        svc = AgentWorkflowDeduper()
        svc.dedup("a1", "wf1", "h1")
        svc.dedup("a2", "wf2", "h2")
        assert svc.get_dedup_count() == 2

    def test_count_by_agent(self):
        svc = AgentWorkflowDeduper()
        svc.dedup("a1", "wf1", "h1")
        svc.dedup("a2", "wf2", "h2")
        svc.dedup("a1", "wf3", "h3")
        assert svc.get_dedup_count(agent_id="a1") == 2
        assert svc.get_dedup_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentWorkflowDeduper()
        assert svc.get_dedup_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentWorkflowDeduper()
        stats = svc.get_stats()
        assert stats["total_dedups"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentWorkflowDeduper()
        svc.dedup("a1", "wf1", "h1")
        svc.dedup("a2", "wf2", "h2")
        svc.dedup("a1", "wf3", "h3")
        stats = svc.get_stats()
        assert stats["total_dedups"] == 3
        assert stats["unique_agents"] == 2

    def test_stats_returns_dict(self):
        svc = AgentWorkflowDeduper()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_dedup(self):
        events = []
        svc = AgentWorkflowDeduper()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.dedup("a1", "wf1", "h1")
        assert len(events) == 1
        assert events[0][0] == "deduped"

    def test_on_change_getter(self):
        svc = AgentWorkflowDeduper()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentWorkflowDeduper()
        svc._state.callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_remove_callback_nonexistent(self):
        svc = AgentWorkflowDeduper()
        assert svc.remove_callback("nope") is False

    def test_callback_exception_silenced(self):
        svc = AgentWorkflowDeduper()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = svc.dedup("a1", "wf1", "h1")
        assert rid.startswith("awdd-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentWorkflowDeduper()
        svc._state.callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.dedup("a1", "wf1", "h1")
        assert "deduped" in events

    def test_named_callback_exception_silenced(self):
        svc = AgentWorkflowDeduper()
        svc._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("x"))
        rid = svc.dedup("a1", "wf1", "h1")
        assert rid.startswith("awdd-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentWorkflowDeduper()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.dedup("a1", f"wf{i}", f"h{i}"))
        assert svc.get_dedup(ids[0]) is None
        assert svc.get_dedup(ids[1]) is None
        assert svc.get_dedup_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentWorkflowDeduper()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.dedup("a1", f"wf{i}", f"h{i}"))
        assert svc.get_dedup(ids[-1]) is not None


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowDeduper()
        svc.dedup("a1", "wf1", "h1")
        svc.reset()
        assert svc.get_dedup_count() == 0
        assert svc.get_stats()["total_dedups"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowDeduper()
        svc._state.callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None
        assert len(svc._state.callbacks) == 0

    def test_reset_allows_new_dedups(self):
        svc = AgentWorkflowDeduper()
        svc.dedup("a1", "wf1", "h1")
        svc.reset()
        rid = svc.dedup("a2", "wf2", "h2")
        assert rid.startswith("awdd-")
        assert svc.get_dedup_count() == 1
