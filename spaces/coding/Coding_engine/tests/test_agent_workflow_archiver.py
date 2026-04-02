"""Tests for AgentWorkflowArchiver service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_archiver import AgentWorkflowArchiver


class TestArchiveBasic:
    """Basic archive and retrieval."""

    def test_archive_returns_id(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "success")
        assert aid.startswith("awar-")
        assert len(aid) > 5

    def test_get_archived_existing(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "success", reason="done")
        entry = svc.get_archived_workflow(aid)
        assert entry is not None
        assert entry["agent_id"] == "a1"
        assert entry["workflow_name"] == "wf1"
        assert entry["result"] == "success"
        assert entry["reason"] == "done"

    def test_get_archived_nonexistent(self):
        svc = AgentWorkflowArchiver()
        assert svc.get_archived_workflow("awar-nonexistent") is None

    def test_default_reason_is_completed(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok")
        entry = svc.get_archived_workflow(aid)
        assert entry["reason"] == "completed"

    def test_archive_has_created_at(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok")
        entry = svc.get_archived_workflow(aid)
        assert "created_at" in entry
        assert isinstance(entry["created_at"], float)

    def test_archive_has_seq(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok")
        entry = svc.get_archived_workflow(aid)
        assert "seq" in entry


class TestMetadata:
    """Metadata handling."""

    def test_metadata_stored(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok", metadata={"key": "val"})
        entry = svc.get_archived_workflow(aid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_archived_workflow(aid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok")
        entry = svc.get_archived_workflow(aid)
        assert entry["metadata"] == {}


class TestGetArchivedWorkflows:
    """Querying multiple archives."""

    def test_get_all(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.archive_workflow("a2", "wf2", "ok")
        results = svc.get_archived_workflows()
        assert len(results) == 2

    def test_filter_by_agent(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.archive_workflow("a2", "wf2", "ok")
        svc.archive_workflow("a1", "wf3", "ok")
        results = svc.get_archived_workflows(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_filter_by_workflow_name(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.archive_workflow("a1", "wf2", "ok")
        svc.archive_workflow("a2", "wf1", "ok")
        results = svc.get_archived_workflows(workflow_name="wf1")
        assert len(results) == 2
        assert all(r["workflow_name"] == "wf1" for r in results)

    def test_filter_by_agent_and_workflow(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.archive_workflow("a2", "wf1", "ok")
        svc.archive_workflow("a1", "wf2", "ok")
        results = svc.get_archived_workflows(agent_id="a1", workflow_name="wf1")
        assert len(results) == 1
        assert results[0]["agent_id"] == "a1"
        assert results[0]["workflow_name"] == "wf1"

    def test_newest_first(self):
        svc = AgentWorkflowArchiver()
        id1 = svc.archive_workflow("a1", "wf1", "ok")
        id2 = svc.archive_workflow("a1", "wf2", "ok")
        results = svc.get_archived_workflows()
        assert results[0]["archive_id"] == id2
        assert results[1]["archive_id"] == id1

    def test_respects_limit(self):
        svc = AgentWorkflowArchiver()
        for i in range(10):
            svc.archive_workflow("a1", f"wf{i}", "ok")
        results = svc.get_archived_workflows(limit=3)
        assert len(results) == 3

    def test_empty(self):
        svc = AgentWorkflowArchiver()
        results = svc.get_archived_workflows()
        assert results == []

    def test_returns_copies(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok")
        results = svc.get_archived_workflows()
        results[0]["agent_id"] = "mutated"
        entry = svc.get_archived_workflow(aid)
        assert entry["agent_id"] == "a1"


class TestGetArchiveCount:
    """Counting archives."""

    def test_count_all(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.archive_workflow("a2", "wf2", "ok")
        assert svc.get_archive_count() == 2

    def test_count_by_agent(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.archive_workflow("a2", "wf2", "ok")
        svc.archive_workflow("a1", "wf3", "ok")
        assert svc.get_archive_count(agent_id="a1") == 2
        assert svc.get_archive_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentWorkflowArchiver()
        assert svc.get_archive_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentWorkflowArchiver()
        stats = svc.get_stats()
        assert stats["total_archived"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_workflows"] == 0
        assert stats["reasons"] == {}

    def test_stats_populated(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok", reason="completed")
        svc.archive_workflow("a2", "wf2", "fail", reason="failed")
        svc.archive_workflow("a1", "wf1", "ok", reason="completed")
        stats = svc.get_stats()
        assert stats["total_archived"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_workflows"] == 2
        assert stats["reasons"]["completed"] == 2
        assert stats["reasons"]["failed"] == 1

    def test_stats_returns_dict(self):
        svc = AgentWorkflowArchiver()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.reset()
        assert svc.get_archive_count() == 0
        assert svc.get_stats()["total_archived"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowArchiver()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None
        assert len(svc._callbacks) == 0

    def test_reset_allows_new_archives(self):
        svc = AgentWorkflowArchiver()
        svc.archive_workflow("a1", "wf1", "ok")
        svc.reset()
        aid = svc.archive_workflow("a2", "wf2", "ok")
        assert aid.startswith("awar-")
        assert svc.get_archive_count() == 1


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_archive(self):
        events = []
        svc = AgentWorkflowArchiver()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.archive_workflow("a1", "wf1", "ok")
        assert len(events) == 1
        assert events[0][0] == "archived"

    def test_on_change_getter(self):
        svc = AgentWorkflowArchiver()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentWorkflowArchiver()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_remove_callback_nonexistent(self):
        svc = AgentWorkflowArchiver()
        assert svc.remove_callback("nope") is False

    def test_callback_exception_silenced(self):
        svc = AgentWorkflowArchiver()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        aid = svc.archive_workflow("a1", "wf1", "ok")
        assert aid.startswith("awar-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentWorkflowArchiver()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.archive_workflow("a1", "wf1", "ok")
        assert "archived" in events

    def test_named_callback_exception_silenced(self):
        svc = AgentWorkflowArchiver()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("x"))
        aid = svc.archive_workflow("a1", "wf1", "ok")
        assert aid.startswith("awar-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentWorkflowArchiver()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.archive_workflow("a1", f"wf{i}", "ok"))
        assert svc.get_archived_workflow(ids[0]) is None
        assert svc.get_archived_workflow(ids[1]) is None
        assert svc.get_archive_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentWorkflowArchiver()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.archive_workflow("a1", f"wf{i}", "ok"))
        assert svc.get_archived_workflow(ids[-1]) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentWorkflowArchiver()
        ids = set()
        for i in range(50):
            ids.add(svc.archive_workflow("a1", f"wf{i}", "ok"))
        assert len(ids) == 50

    def test_id_prefix(self):
        svc = AgentWorkflowArchiver()
        aid = svc.archive_workflow("a1", "wf1", "ok")
        assert aid.startswith("awar-")
