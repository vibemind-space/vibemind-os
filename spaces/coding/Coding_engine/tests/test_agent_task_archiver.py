"""Tests for AgentTaskArchiver service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_archiver import AgentTaskArchiver


class TestArchiveBasic:
    """Basic archive and retrieval."""

    def test_archive_returns_id(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1")
        assert aid.startswith("atar2-")
        assert len(aid) > 6

    def test_archive_empty_task_id_returns_empty(self):
        svc = AgentTaskArchiver()
        assert svc.archive("", "a1") == ""

    def test_archive_empty_agent_id_returns_empty(self):
        svc = AgentTaskArchiver()
        assert svc.archive("t1", "") == ""

    def test_get_archived_existing(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1", result="success", reason="done")
        entry = svc.get_archived(aid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["result"] == "success"
        assert entry["reason"] == "done"

    def test_get_archived_nonexistent(self):
        svc = AgentTaskArchiver()
        assert svc.get_archived("atar2-nonexistent") is None

    def test_default_reason_is_completed(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1")
        entry = svc.get_archived(aid)
        assert entry["reason"] == "completed"

    def test_default_result_is_empty(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1")
        entry = svc.get_archived(aid)
        assert entry["result"] == ""


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1", metadata={"key": "val"})
        entry = svc.get_archived(aid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_archived(aid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1")
        entry = svc.get_archived(aid)
        assert entry["metadata"] == {}


class TestGetArchives:
    """Querying multiple archives."""

    def test_get_archives_all(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        results = svc.get_archives()
        assert len(results) == 2

    def test_get_archives_filter_by_agent(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        svc.archive("t3", "a1")
        results = svc.get_archives(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_archives_filter_by_reason(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1", reason="completed")
        svc.archive("t2", "a1", reason="failed")
        svc.archive("t3", "a1", reason="completed")
        results = svc.get_archives(reason="completed")
        assert len(results) == 2
        assert all(r["reason"] == "completed" for r in results)

    def test_get_archives_filter_by_agent_and_reason(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1", reason="completed")
        svc.archive("t2", "a2", reason="completed")
        svc.archive("t3", "a1", reason="failed")
        results = svc.get_archives(agent_id="a1", reason="completed")
        assert len(results) == 1
        assert results[0]["task_id"] == "t1"

    def test_get_archives_newest_first(self):
        svc = AgentTaskArchiver()
        id1 = svc.archive("t1", "a1")
        id2 = svc.archive("t2", "a1")
        results = svc.get_archives()
        assert results[0]["archive_id"] == id2
        assert results[1]["archive_id"] == id1

    def test_get_archives_respects_limit(self):
        svc = AgentTaskArchiver()
        for i in range(10):
            svc.archive(f"t{i}", "a1")
        results = svc.get_archives(limit=3)
        assert len(results) == 3

    def test_get_archives_empty(self):
        svc = AgentTaskArchiver()
        results = svc.get_archives()
        assert results == []

    def test_get_archives_returns_copies(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1")
        results = svc.get_archives()
        results[0]["task_id"] = "mutated"
        entry = svc.get_archived(aid)
        assert entry["task_id"] == "t1"


class TestGetArchiveCount:
    """Counting archives."""

    def test_count_all(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        assert svc.get_archive_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        svc.archive("t3", "a1")
        assert svc.get_archive_count(agent_id="a1") == 2
        assert svc.get_archive_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskArchiver()
        assert svc.get_archive_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskArchiver()
        stats = svc.get_stats()
        assert stats["total_archived"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["reasons"] == {}

    def test_stats_populated(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1", reason="completed")
        svc.archive("t2", "a2", reason="failed")
        svc.archive("t1", "a2", reason="completed")
        stats = svc.get_stats()
        assert stats["total_archived"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_tasks"] == 2
        assert stats["reasons"]["completed"] == 2
        assert stats["reasons"]["failed"] == 1

    def test_stats_returns_dict(self):
        svc = AgentTaskArchiver()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1")
        svc.reset()
        assert svc.get_archive_count() == 0
        assert svc.get_stats()["total_archived"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskArchiver()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None
        assert len(svc._callbacks) == 0

    def test_reset_allows_new_archives(self):
        svc = AgentTaskArchiver()
        svc.archive("t1", "a1")
        svc.reset()
        aid = svc.archive("t2", "a2")
        assert aid.startswith("atar2-")
        assert svc.get_archive_count() == 1


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_archive(self):
        events = []
        svc = AgentTaskArchiver()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.archive("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "archived"

    def test_on_change_getter(self):
        svc = AgentTaskArchiver()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskArchiver()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskArchiver()
        assert svc.remove_callback("nope") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskArchiver()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        aid = svc.archive("t1", "a1")
        assert aid.startswith("atar2-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskArchiver()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.archive("t1", "a1")
        assert "archived" in events

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskArchiver()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("x"))
        aid = svc.archive("t1", "a1")
        assert aid.startswith("atar2-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentTaskArchiver()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.archive(f"t{i}", "a1"))
        # First two (quarter of 8) should be evicted
        assert svc.get_archived(ids[0]) is None
        assert svc.get_archived(ids[1]) is None
        assert svc.get_archive_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskArchiver()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.archive(f"t{i}", "a1"))
        # Last entry should still exist
        assert svc.get_archived(ids[-1]) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskArchiver()
        ids = set()
        for i in range(50):
            ids.add(svc.archive(f"t{i}", "a1"))
        assert len(ids) == 50

    def test_id_prefix(self):
        svc = AgentTaskArchiver()
        aid = svc.archive("t1", "a1")
        assert aid.startswith("atar2-")
