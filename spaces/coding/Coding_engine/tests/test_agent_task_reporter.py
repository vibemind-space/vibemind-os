"""Tests for AgentTaskReporter service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_reporter import AgentTaskReporter


class TestCreateReportBasic:
    """Basic report creation and retrieval."""

    def test_create_report_returns_id(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        assert rid.startswith("atrp-")
        assert len(rid) > 5

    def test_create_report_empty_task_id_returns_empty(self):
        svc = AgentTaskReporter()
        assert svc.create_report("", "a1") == ""

    def test_create_report_empty_agent_id_returns_empty(self):
        svc = AgentTaskReporter()
        assert svc.create_report("t1", "") == ""

    def test_get_report_existing(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1", status="in_progress", progress=0.5)
        entry = svc.get_report(rid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["status"] == "in_progress"
        assert entry["progress"] == 0.5

    def test_get_report_nonexistent(self):
        svc = AgentTaskReporter()
        assert svc.get_report("atrp-nonexistent") is None

    def test_default_status_is_in_progress(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        entry = svc.get_report(rid)
        assert entry["status"] == "in_progress"

    def test_default_progress_is_zero(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        entry = svc.get_report(rid)
        assert entry["progress"] == 0.0


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1", metadata={"key": "val"})
        entry = svc.get_report(rid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_report(rid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        entry = svc.get_report(rid)
        assert entry["metadata"] == {}


class TestGetReports:
    """Querying multiple reports."""

    def test_get_reports_all(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1")
        svc.create_report("t2", "a2")
        results = svc.get_reports()
        assert len(results) == 2

    def test_get_reports_filter_by_agent(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1")
        svc.create_report("t2", "a2")
        svc.create_report("t3", "a1")
        results = svc.get_reports(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_reports_filter_by_task(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1")
        svc.create_report("t1", "a2")
        svc.create_report("t2", "a1")
        results = svc.get_reports(task_id="t1")
        assert len(results) == 2

    def test_get_reports_filter_by_status(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1", status="in_progress")
        svc.create_report("t2", "a1", status="completed")
        svc.create_report("t3", "a1", status="in_progress")
        results = svc.get_reports(status="completed")
        assert len(results) == 1
        assert results[0]["status"] == "completed"

    def test_get_reports_newest_first(self):
        svc = AgentTaskReporter()
        id1 = svc.create_report("t1", "a1")
        id2 = svc.create_report("t2", "a1")
        results = svc.get_reports()
        assert results[0]["report_id"] == id2
        assert results[1]["report_id"] == id1

    def test_get_reports_respects_limit(self):
        svc = AgentTaskReporter()
        for i in range(10):
            svc.create_report(f"t{i}", "a1")
        results = svc.get_reports(limit=3)
        assert len(results) == 3


class TestUpdateReport:
    """Updating existing reports."""

    def test_update_status(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        assert svc.update_report(rid, status="completed") is True
        entry = svc.get_report(rid)
        assert entry["status"] == "completed"

    def test_update_progress(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        svc.update_report(rid, progress=0.75)
        entry = svc.get_report(rid)
        assert entry["progress"] == 0.75

    def test_update_summary(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        svc.update_report(rid, summary="Almost done")
        entry = svc.get_report(rid)
        assert entry["summary"] == "Almost done"

    def test_update_nonexistent_returns_false(self):
        svc = AgentTaskReporter()
        assert svc.update_report("atrp-nope", status="done") is False

    def test_update_changes_updated_at(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        before = svc.get_report(rid)["updated_at"]
        svc.update_report(rid, progress=0.5)
        after = svc.get_report(rid)["updated_at"]
        assert after >= before


class TestGetReportCount:
    """Counting reports."""

    def test_count_all(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1")
        svc.create_report("t2", "a2")
        assert svc.get_report_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1")
        svc.create_report("t2", "a2")
        svc.create_report("t3", "a1")
        assert svc.get_report_count(agent_id="a1") == 2
        assert svc.get_report_count(agent_id="a2") == 1

    def test_count_by_status(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1", status="in_progress")
        svc.create_report("t2", "a1", status="completed")
        assert svc.get_report_count(status="in_progress") == 1
        assert svc.get_report_count(status="completed") == 1

    def test_count_empty(self):
        svc = AgentTaskReporter()
        assert svc.get_report_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskReporter()
        stats = svc.get_stats()
        assert stats["total_reports"] == 0
        assert stats["by_status"] == {}
        assert stats["avg_progress"] == 0.0

    def test_stats_populated(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1", status="in_progress", progress=0.5)
        svc.create_report("t2", "a2", status="completed", progress=1.0)
        svc.create_report("t3", "a1", status="in_progress", progress=0.25)
        stats = svc.get_stats()
        assert stats["total_reports"] == 3
        assert stats["by_status"]["in_progress"] == 2
        assert stats["by_status"]["completed"] == 1
        assert abs(stats["avg_progress"] - 0.5833333333) < 0.01


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1")
        svc.reset()
        assert svc.get_report_count() == 0
        assert svc.get_stats()["total_reports"] == 0

    def test_reset_clears_on_change(self):
        svc = AgentTaskReporter()
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_create(self):
        events = []
        svc = AgentTaskReporter()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.create_report("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "report_created"

    def test_on_change_fires_on_update(self):
        events = []
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        svc.on_change = lambda action, data: events.append((action, data))
        svc.update_report(rid, progress=0.5)
        assert len(events) == 1
        assert events[0][0] == "report_updated"

    def test_on_change_getter(self):
        svc = AgentTaskReporter()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskReporter()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskReporter()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = svc.create_report("t1", "a1")
        assert rid.startswith("atrp-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskReporter()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.create_report("t1", "a1")
        assert "report_created" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskReporter()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.create_report(f"t{i}", "a1"))
        assert svc.get_report(ids[0]) is None
        assert svc.get_report_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskReporter()
        ids = set()
        for i in range(50):
            ids.add(svc.create_report(f"t{i}", "a1"))
        assert len(ids) == 50


class TestReturnTypes:
    """All public methods return expected types."""

    def test_create_report_returns_dict_via_get(self):
        svc = AgentTaskReporter()
        rid = svc.create_report("t1", "a1")
        assert isinstance(svc.get_report(rid), dict)

    def test_get_reports_returns_list_of_dicts(self):
        svc = AgentTaskReporter()
        svc.create_report("t1", "a1")
        results = svc.get_reports()
        assert isinstance(results, list)
        assert all(isinstance(r, dict) for r in results)

    def test_get_stats_returns_dict(self):
        svc = AgentTaskReporter()
        assert isinstance(svc.get_stats(), dict)
