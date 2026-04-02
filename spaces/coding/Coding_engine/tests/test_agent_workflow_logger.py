"""Tests for AgentWorkflowLogger service."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_logger import AgentWorkflowLogger


class TestLogBasic:
    """Basic log creation and retrieval."""

    def test_log_returns_id(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1")
        assert lid.startswith("awlo-")
        assert len(lid) > 5

    def test_log_empty_agent_id_returns_empty(self):
        svc = AgentWorkflowLogger()
        assert svc.log("", "wf1") == ""

    def test_log_empty_workflow_name_returns_empty(self):
        svc = AgentWorkflowLogger()
        assert svc.log("a1", "") == ""

    def test_log_invalid_level_returns_empty(self):
        svc = AgentWorkflowLogger()
        assert svc.log("a1", "wf1", level="critical") == ""

    def test_get_log_existing(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1", message="hello")
        entry = svc.get_log(lid)
        assert entry is not None
        assert entry["agent_id"] == "a1"
        assert entry["workflow_name"] == "wf1"
        assert entry["message"] == "hello"
        assert entry["level"] == "info"

    def test_get_log_nonexistent(self):
        svc = AgentWorkflowLogger()
        assert svc.get_log("awlo-nonexistent") is None

    def test_default_level_is_info(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1")
        assert svc.get_log(lid)["level"] == "info"


class TestLogLevels:
    """Verify all valid levels are accepted."""

    def test_debug_level(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1", level="debug")
        assert svc.get_log(lid)["level"] == "debug"

    def test_warning_level(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1", level="warning")
        assert svc.get_log(lid)["level"] == "warning"

    def test_error_level(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1", level="error")
        assert svc.get_log(lid)["level"] == "error"


class TestMetadata:
    """Metadata storage and isolation."""

    def test_metadata_stored(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1", metadata={"key": "val"})
        assert svc.get_log(lid)["metadata"] == {"key": "val"}

    def test_metadata_default_empty_dict(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1")
        assert svc.get_log(lid)["metadata"] == {}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1", metadata=meta)
        meta["nested"]["x"] = 999
        assert svc.get_log(lid)["metadata"]["nested"]["x"] == 1


class TestGetLogs:
    """Filtering and ordering of get_logs."""

    def test_get_logs_all(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1")
        svc.log("a2", "wf2")
        assert len(svc.get_logs()) == 2

    def test_get_logs_filter_agent(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1")
        svc.log("a2", "wf1")
        results = svc.get_logs(agent_id="a1")
        assert len(results) == 1
        assert results[0]["agent_id"] == "a1"

    def test_get_logs_filter_workflow(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1")
        svc.log("a1", "wf2")
        results = svc.get_logs(workflow_name="wf2")
        assert len(results) == 1
        assert results[0]["workflow_name"] == "wf2"

    def test_get_logs_filter_level(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1", level="error")
        svc.log("a1", "wf1", level="info")
        results = svc.get_logs(level="error")
        assert len(results) == 1
        assert results[0]["level"] == "error"

    def test_get_logs_newest_first(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1", message="first")
        svc.log("a1", "wf1", message="second")
        results = svc.get_logs()
        assert results[0]["message"] == "second"
        assert results[1]["message"] == "first"

    def test_get_logs_limit(self):
        svc = AgentWorkflowLogger()
        for i in range(10):
            svc.log("a1", "wf1", message=str(i))
        results = svc.get_logs(limit=3)
        assert len(results) == 3


class TestGetLogCount:
    """Log counting with filters."""

    def test_count_all(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1")
        svc.log("a2", "wf2")
        assert svc.get_log_count() == 2

    def test_count_by_agent(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1")
        svc.log("a1", "wf2")
        svc.log("a2", "wf1")
        assert svc.get_log_count(agent_id="a1") == 2

    def test_count_by_level(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1", level="error")
        svc.log("a1", "wf1", level="error")
        svc.log("a1", "wf1", level="info")
        assert svc.get_log_count(level="error") == 2


class TestGetStats:
    """Aggregate statistics."""

    def test_stats_empty(self):
        svc = AgentWorkflowLogger()
        stats = svc.get_stats()
        assert stats["total_logs"] == 0
        assert stats["unique_agents"] == 0
        assert stats["logs_by_level"] == {}

    def test_stats_populated(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1", level="info")
        svc.log("a2", "wf1", level="error")
        svc.log("a1", "wf2", level="info")
        stats = svc.get_stats()
        assert stats["total_logs"] == 3
        assert stats["unique_agents"] == 2
        assert stats["logs_by_level"]["info"] == 2
        assert stats["logs_by_level"]["error"] == 1


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1")
        svc.reset()
        assert svc.get_log_count() == 0

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowLogger()
        svc.on_change["cb1"] = lambda e, d: None
        svc.reset()
        assert len(svc.on_change) == 0


class TestCallbacks:
    """Event firing and callback management."""

    def test_fire_on_log(self):
        svc = AgentWorkflowLogger()
        events = []
        svc.on_change["cb1"] = lambda e, d: events.append((e, d))
        svc.log("a1", "wf1")
        assert len(events) == 1
        assert events[0][0] == "log_created"

    def test_remove_callback_existing(self):
        svc = AgentWorkflowLogger()
        svc.on_change["cb1"] = lambda e, d: None
        assert svc.remove_callback("cb1") is True
        assert "cb1" not in svc.on_change

    def test_remove_callback_nonexistent(self):
        svc = AgentWorkflowLogger()
        assert svc.remove_callback("nope") is False

    def test_fire_silent_on_error(self):
        svc = AgentWorkflowLogger()
        svc.on_change["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
        # Should not raise
        lid = svc.log("a1", "wf1")
        assert lid.startswith("awlo-")


class TestPrune:
    """Pruning when exceeding MAX_ENTRIES."""

    def test_prune_limits_entries(self):
        svc = AgentWorkflowLogger()
        svc.MAX_ENTRIES = 5
        for i in range(8):
            svc.log("a1", "wf1", message=str(i))
        assert svc.get_log_count() == 5


class TestReturnTypes:
    """All public methods return dicts or expected types."""

    def test_get_log_returns_dict(self):
        svc = AgentWorkflowLogger()
        lid = svc.log("a1", "wf1")
        assert isinstance(svc.get_log(lid), dict)

    def test_get_logs_returns_list_of_dicts(self):
        svc = AgentWorkflowLogger()
        svc.log("a1", "wf1")
        results = svc.get_logs()
        assert isinstance(results, list)
        assert isinstance(results[0], dict)

    def test_get_stats_returns_dict(self):
        svc = AgentWorkflowLogger()
        assert isinstance(svc.get_stats(), dict)
