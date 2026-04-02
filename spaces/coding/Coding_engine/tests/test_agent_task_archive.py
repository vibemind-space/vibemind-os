"""Tests for AgentTaskArchive service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_archive import AgentTaskArchive


class TestArchiveBasic:
    """Basic archive and retrieval."""

    def test_archive_returns_id(self):
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1")
        assert aid.startswith("atar-")
        assert len(aid) > 5

    def test_archive_empty_task_id_returns_empty(self):
        svc = AgentTaskArchive()
        assert svc.archive("", "a1") == ""

    def test_archive_empty_agent_id_returns_empty(self):
        svc = AgentTaskArchive()
        assert svc.archive("t1", "") == ""

    def test_get_archive_existing(self):
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1", result="success")
        entry = svc.get_archive(aid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["result"] == "success"

    def test_get_archive_nonexistent(self):
        svc = AgentTaskArchive()
        assert svc.get_archive("atar-nonexistent") is None

    def test_default_result_is_completed(self):
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1")
        entry = svc.get_archive(aid)
        assert entry["result"] == "completed"


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1", metadata={"key": "val"})
        entry = svc.get_archive(aid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1", metadata=meta)
        # mutate original
        meta["nested"]["x"] = 999
        entry = svc.get_archive(aid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1")
        entry = svc.get_archive(aid)
        assert entry["metadata"] == {}


class TestGetArchives:
    """Querying multiple archives."""

    def test_get_archives_all(self):
        svc = AgentTaskArchive()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        results = svc.get_archives()
        assert len(results) == 2

    def test_get_archives_filter_by_agent(self):
        svc = AgentTaskArchive()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        svc.archive("t3", "a1")
        results = svc.get_archives(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_archives_filter_by_task(self):
        svc = AgentTaskArchive()
        svc.archive("t1", "a1")
        svc.archive("t1", "a2")
        svc.archive("t2", "a1")
        results = svc.get_archives(task_id="t1")
        assert len(results) == 2

    def test_get_archives_newest_first(self):
        svc = AgentTaskArchive()
        id1 = svc.archive("t1", "a1")
        id2 = svc.archive("t2", "a1")
        results = svc.get_archives()
        assert results[0]["archive_id"] == id2
        assert results[1]["archive_id"] == id1

    def test_get_archives_respects_limit(self):
        svc = AgentTaskArchive()
        for i in range(10):
            svc.archive(f"t{i}", "a1")
        results = svc.get_archives(limit=3)
        assert len(results) == 3


class TestUnarchive:
    """Removing entries from archive."""

    def test_unarchive_existing(self):
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1")
        assert svc.unarchive(aid) is True
        assert svc.get_archive(aid) is None

    def test_unarchive_nonexistent(self):
        svc = AgentTaskArchive()
        assert svc.unarchive("atar-nope") is False


class TestGetArchiveCount:
    """Counting archives."""

    def test_count_all(self):
        svc = AgentTaskArchive()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        assert svc.get_archive_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskArchive()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        svc.archive("t3", "a1")
        assert svc.get_archive_count(agent_id="a1") == 2
        assert svc.get_archive_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskArchive()
        assert svc.get_archive_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskArchive()
        stats = svc.get_stats()
        assert stats["total_archived"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_tasks"] == 0

    def test_stats_populated(self):
        svc = AgentTaskArchive()
        svc.archive("t1", "a1")
        svc.archive("t2", "a2")
        svc.archive("t1", "a2")
        stats = svc.get_stats()
        assert stats["total_archived"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_tasks"] == 2


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskArchive()
        svc.archive("t1", "a1")
        svc.reset()
        assert svc.get_archive_count() == 0
        assert svc.get_stats()["total_archived"] == 0


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_archive(self):
        events = []
        svc = AgentTaskArchive()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.archive("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "archived"

    def test_on_change_fires_on_unarchive(self):
        events = []
        svc = AgentTaskArchive()
        aid = svc.archive("t1", "a1")
        svc.on_change = lambda action, data: events.append((action, data))
        svc.unarchive(aid)
        assert len(events) == 1
        assert events[0][0] == "unarchived"

    def test_on_change_getter(self):
        svc = AgentTaskArchive()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskArchive()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskArchive()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        # Should not raise
        aid = svc.archive("t1", "a1")
        assert aid.startswith("atar-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskArchive()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.archive("t1", "a1")
        assert "archived" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskArchive()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.archive(f"t{i}", "a1"))
        # First entry should have been evicted
        assert svc.get_archive(ids[0]) is None
        assert svc.get_archive_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskArchive()
        ids = set()
        for i in range(50):
            ids.add(svc.archive(f"t{i}", "a1"))
        assert len(ids) == 50
