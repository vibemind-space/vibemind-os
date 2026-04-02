"""Tests for AgentTaskLogger service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_logger import AgentTaskLogger


class TestLogBasic:
    """Basic log creation and retrieval."""

    def test_log_returns_id(self):
        svc = AgentTaskLogger()
        lid = svc.log("t1", "a1")
        assert lid.startswith("atlg-")
        assert len(lid) > 5

    def test_log_empty_task_id_returns_empty(self):
        svc = AgentTaskLogger()
        assert svc.log("", "a1") == ""

    def test_log_empty_agent_id_returns_empty(self):
        svc = AgentTaskLogger()
        assert svc.log("t1", "") == ""

    def test_log_invalid_level_returns_empty(self):
        svc = AgentTaskLogger()
        assert svc.log("t1", "a1", level="critical") == ""

    def test_get_log_existing(self):
        svc = AgentTaskLogger()
        lid = svc.log("t1", "a1", level="warning", message="something happened")
        entry = svc.get_log(lid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["level"] == "warning"
        assert entry["message"] == "something happened"

    def test_get_log_nonexistent(self):
        svc = AgentTaskLogger()
        assert svc.get_log("atlg-nonexistent") is None

    def test_default_level_is_info(self):
        svc = AgentTaskLogger()
        lid = svc.log("t1", "a1")
        entry = svc.get_log(lid)
        assert entry["level"] == "info"

    def test_default_message_is_empty(self):
        svc = AgentTaskLogger()
        lid = svc.log("t1", "a1")
        entry = svc.get_log(lid)
        assert entry["message"] == ""

    def test_all_valid_levels(self):
        svc = AgentTaskLogger()
        for level in ("debug", "info", "warning", "error"):
            lid = svc.log("t1", "a1", level=level)
            assert lid != ""
            entry = svc.get_log(lid)
            assert entry["level"] == level


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskLogger()
        lid = svc.log("t1", "a1", metadata={"key": "val"})
        entry = svc.get_log(lid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskLogger()
        lid = svc.log("t1", "a1", metadata=meta)
        # mutate original
        meta["nested"]["x"] = 999
        entry = svc.get_log(lid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskLogger()
        lid = svc.log("t1", "a1")
        entry = svc.get_log(lid)
        assert entry["metadata"] == {}


class TestGetLogs:
    """Querying multiple logs."""

    def test_get_logs_all(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1")
        svc.log("t2", "a2")
        results = svc.get_logs()
        assert len(results) == 2

    def test_get_logs_filter_by_task(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1")
        svc.log("t1", "a2")
        svc.log("t2", "a1")
        results = svc.get_logs(task_id="t1")
        assert len(results) == 2
        assert all(r["task_id"] == "t1" for r in results)

    def test_get_logs_filter_by_agent(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1")
        svc.log("t2", "a2")
        svc.log("t3", "a1")
        results = svc.get_logs(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_logs_filter_by_level(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1", level="info")
        svc.log("t2", "a1", level="error")
        svc.log("t3", "a1", level="info")
        results = svc.get_logs(level="error")
        assert len(results) == 1
        assert results[0]["level"] == "error"

    def test_get_logs_newest_first(self):
        svc = AgentTaskLogger()
        id1 = svc.log("t1", "a1")
        id2 = svc.log("t2", "a1")
        results = svc.get_logs()
        assert results[0]["log_id"] == id2
        assert results[1]["log_id"] == id1

    def test_get_logs_respects_limit(self):
        svc = AgentTaskLogger()
        for i in range(10):
            svc.log(f"t{i}", "a1")
        results = svc.get_logs(limit=3)
        assert len(results) == 3

    def test_get_logs_combined_filters(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1", level="error")
        svc.log("t1", "a1", level="info")
        svc.log("t1", "a2", level="error")
        svc.log("t2", "a1", level="error")
        results = svc.get_logs(task_id="t1", agent_id="a1", level="error")
        assert len(results) == 1


class TestGetLogCount:
    """Counting log entries."""

    def test_count_all(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1")
        svc.log("t2", "a2")
        assert svc.get_log_count() == 2

    def test_count_by_task(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1")
        svc.log("t1", "a2")
        svc.log("t2", "a1")
        assert svc.get_log_count(task_id="t1") == 2

    def test_count_by_level(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1", level="error")
        svc.log("t2", "a1", level="info")
        svc.log("t3", "a1", level="error")
        assert svc.get_log_count(level="error") == 2

    def test_count_empty(self):
        svc = AgentTaskLogger()
        assert svc.get_log_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskLogger()
        stats = svc.get_stats()
        assert stats["total_logs"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["unique_agents"] == 0
        assert stats["by_level"] == {}

    def test_stats_populated(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1", level="info")
        svc.log("t2", "a2", level="error")
        svc.log("t1", "a2", level="info")
        stats = svc.get_stats()
        assert stats["total_logs"] == 3
        assert stats["unique_tasks"] == 2
        assert stats["unique_agents"] == 2
        assert stats["by_level"]["info"] == 2
        assert stats["by_level"]["error"] == 1


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskLogger()
        svc.log("t1", "a1")
        svc.reset()
        assert svc.get_log_count() == 0
        assert svc.get_stats()["total_logs"] == 0

    def test_reset_clears_on_change(self):
        svc = AgentTaskLogger()
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_log(self):
        events = []
        svc = AgentTaskLogger()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.log("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "logged"

    def test_on_change_getter(self):
        svc = AgentTaskLogger()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskLogger()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskLogger()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        # Should not raise
        lid = svc.log("t1", "a1")
        assert lid.startswith("atlg-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskLogger()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.log("t1", "a1")
        assert "logged" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskLogger()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.log(f"t{i}", "a1"))
        # First entry should have been evicted
        assert svc.get_log(ids[0]) is None
        assert svc.get_log_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskLogger()
        ids = set()
        for i in range(50):
            ids.add(svc.log(f"t{i}", "a1"))
        assert len(ids) == 50
