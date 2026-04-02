"""Tests for AgentWorkflowProfiler service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_profiler import AgentWorkflowProfiler


# ------------------------------------------------------------------
# Profile basics
# ------------------------------------------------------------------

class TestProfile:
    def test_profile_returns_id_with_prefix(self):
        p = AgentWorkflowProfiler()
        pid = p.profile("agent-1", "deploy", {"duration_ms": 100})
        assert pid.startswith("awpf-")
        assert len(pid) > len("awpf-")

    def test_profile_unique_ids(self):
        p = AgentWorkflowProfiler()
        ids = {p.profile("agent-1", "deploy", {"d": i}) for i in range(20)}
        assert len(ids) == 20

    def test_profile_stores_metrics(self):
        p = AgentWorkflowProfiler()
        pid = p.profile("agent-1", "deploy", {"duration_ms": 500, "cpu": 80})
        entry = p.get_profile(pid)
        assert entry["metrics"] == {"duration_ms": 500, "cpu": 80}

    def test_profile_stores_metadata(self):
        p = AgentWorkflowProfiler()
        pid = p.profile("agent-1", "deploy", {"d": 1}, {"env": "prod"})
        entry = p.get_profile(pid)
        assert entry["metadata"] == {"env": "prod"}

    def test_profile_default_metadata_is_empty_dict(self):
        p = AgentWorkflowProfiler()
        pid = p.profile("agent-1", "deploy", {"d": 1})
        entry = p.get_profile(pid)
        assert entry["metadata"] == {}

    def test_profile_records_created_at(self):
        p = AgentWorkflowProfiler()
        before = time.time()
        pid = p.profile("agent-1", "deploy", {"d": 1})
        after = time.time()
        entry = p.get_profile(pid)
        assert before <= entry["created_at"] <= after


# ------------------------------------------------------------------
# get_profile
# ------------------------------------------------------------------

class TestGetProfile:
    def test_get_profile_returns_entry(self):
        p = AgentWorkflowProfiler()
        pid = p.profile("agent-1", "deploy", {"d": 1})
        entry = p.get_profile(pid)
        assert isinstance(entry, dict)
        assert entry["profile_id"] == pid
        assert entry["agent_id"] == "agent-1"
        assert entry["workflow_name"] == "deploy"

    def test_get_profile_not_found(self):
        p = AgentWorkflowProfiler()
        assert p.get_profile("awpf-nonexistent") is None

    def test_get_profile_returns_copy(self):
        p = AgentWorkflowProfiler()
        pid = p.profile("agent-1", "deploy", {"d": 1}, {"key": "val"})
        e1 = p.get_profile(pid)
        e2 = p.get_profile(pid)
        assert e1 is not e2
        e1["metadata"]["key"] = "modified"
        e3 = p.get_profile(pid)
        assert e3["metadata"]["key"] == "val"


# ------------------------------------------------------------------
# get_profiles (filtering, sorting, limit)
# ------------------------------------------------------------------

class TestGetProfiles:
    def test_get_profiles_all(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.profile("agent-2", "build", {"d": 2})
        results = p.get_profiles()
        assert len(results) == 2

    def test_get_profiles_filter_by_agent(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.profile("agent-2", "build", {"d": 2})
        p.profile("agent-1", "test", {"d": 3})
        results = p.get_profiles(agent_id="agent-1")
        assert len(results) == 2
        assert all(e["agent_id"] == "agent-1" for e in results)

    def test_get_profiles_filter_by_workflow(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.profile("agent-1", "build", {"d": 2})
        p.profile("agent-2", "deploy", {"d": 3})
        results = p.get_profiles(workflow_name="deploy")
        assert len(results) == 2
        assert all(e["workflow_name"] == "deploy" for e in results)

    def test_get_profiles_filter_by_agent_and_workflow(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.profile("agent-1", "build", {"d": 2})
        p.profile("agent-2", "deploy", {"d": 3})
        results = p.get_profiles(agent_id="agent-1", workflow_name="deploy")
        assert len(results) == 1
        assert results[0]["agent_id"] == "agent-1"
        assert results[0]["workflow_name"] == "deploy"

    def test_get_profiles_sorted_newest_first(self):
        p = AgentWorkflowProfiler()
        id1 = p.profile("agent-1", "deploy", {"step": 1})
        id2 = p.profile("agent-1", "deploy", {"step": 2})
        id3 = p.profile("agent-1", "deploy", {"step": 3})
        results = p.get_profiles(agent_id="agent-1")
        assert results[0]["profile_id"] == id3
        assert results[1]["profile_id"] == id2
        assert results[2]["profile_id"] == id1

    def test_get_profiles_limit(self):
        p = AgentWorkflowProfiler()
        for i in range(10):
            p.profile("agent-1", "deploy", {"step": i})
        results = p.get_profiles(limit=3)
        assert len(results) == 3

    def test_get_profiles_default_limit_50(self):
        p = AgentWorkflowProfiler()
        for i in range(60):
            p.profile("agent-1", "deploy", {"step": i})
        results = p.get_profiles()
        assert len(results) == 50

    def test_get_profiles_returns_copies(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1}, {"k": "v"})
        results = p.get_profiles()
        results[0]["metadata"]["k"] = "changed"
        fresh = p.get_profiles()
        assert fresh[0]["metadata"]["k"] == "v"


# ------------------------------------------------------------------
# get_profile_count
# ------------------------------------------------------------------

class TestGetProfileCount:
    def test_count_all(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.profile("agent-2", "build", {"d": 2})
        assert p.get_profile_count() == 2

    def test_count_by_agent(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.profile("agent-2", "build", {"d": 2})
        p.profile("agent-1", "test", {"d": 3})
        assert p.get_profile_count(agent_id="agent-1") == 2
        assert p.get_profile_count(agent_id="agent-2") == 1

    def test_count_empty(self):
        p = AgentWorkflowProfiler()
        assert p.get_profile_count() == 0
        assert p.get_profile_count(agent_id="ghost") == 0


# ------------------------------------------------------------------
# get_stats
# ------------------------------------------------------------------

class TestGetStats:
    def test_stats_initial(self):
        p = AgentWorkflowProfiler()
        stats = p.get_stats()
        assert stats["current_entries"] == 0
        assert stats["total_profiled"] == 0
        assert stats["total_pruned"] == 0
        assert stats["total_queries"] == 0
        assert stats["max_entries"] == 10000
        assert stats["callbacks"] == 0

    def test_stats_after_profile(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.profile("agent-1", "deploy", {"d": 2})
        stats = p.get_stats()
        assert stats["current_entries"] == 2
        assert stats["total_profiled"] == 2

    def test_stats_tracks_queries(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.get_profiles()
        p.get_profiles()
        stats = p.get_stats()
        assert stats["total_queries"] == 2


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------

class TestReset:
    def test_reset_clears_entries(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.reset()
        assert p.get_profile_count() == 0
        stats = p.get_stats()
        assert stats["current_entries"] == 0
        assert stats["total_profiled"] == 0

    def test_reset_clears_callbacks(self):
        p = AgentWorkflowProfiler()
        p._callbacks["cb1"] = lambda action, data: None
        p.on_change = lambda action, data: None
        p.reset()
        assert len(p._callbacks) == 0
        assert p.on_change is None

    def test_reset_clears_seq(self):
        p = AgentWorkflowProfiler()
        p.profile("agent-1", "deploy", {"d": 1})
        p.reset()
        assert p._state._seq == 0


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------

class TestCallbacks:
    def test_on_change_property(self):
        p = AgentWorkflowProfiler()
        assert p.on_change is None
        fn = lambda action, data: None
        p.on_change = fn
        assert p.on_change is fn

    def test_on_change_called_on_profile(self):
        p = AgentWorkflowProfiler()
        calls = []
        p.on_change = lambda action, data: calls.append((action, data))
        p.profile("agent-1", "deploy", {"d": 1})
        assert len(calls) == 1
        assert calls[0][0] == "profile_recorded"
        assert calls[0][1]["agent_id"] == "agent-1"

    def test_callback_called_on_profile(self):
        p = AgentWorkflowProfiler()
        calls = []
        p._callbacks["cb1"] = lambda action, data: calls.append((action, data))
        p.profile("agent-1", "deploy", {"d": 1})
        assert len(calls) == 1
        assert calls[0][0] == "profile_recorded"

    def test_on_change_called_before_callbacks(self):
        p = AgentWorkflowProfiler()
        order = []
        p.on_change = lambda action, data: order.append("on_change")
        p._callbacks["cb1"] = lambda action, data: order.append("cb1")
        p.profile("agent-1", "deploy", {"d": 1})
        assert order == ["on_change", "cb1"]

    def test_callback_exception_silenced(self):
        p = AgentWorkflowProfiler()
        p._callbacks["bad"] = lambda action, data: 1 / 0
        pid = p.profile("agent-1", "deploy", {"d": 1})
        assert pid.startswith("awpf-")

    def test_on_change_exception_silenced(self):
        p = AgentWorkflowProfiler()
        p.on_change = lambda action, data: 1 / 0
        pid = p.profile("agent-1", "deploy", {"d": 1})
        assert pid.startswith("awpf-")

    def test_remove_callback_returns_true(self):
        p = AgentWorkflowProfiler()
        p._callbacks["cb1"] = lambda action, data: None
        assert p.remove_callback("cb1") is True
        assert "cb1" not in p._callbacks

    def test_remove_callback_returns_false_if_not_found(self):
        p = AgentWorkflowProfiler()
        assert p.remove_callback("nonexistent") is False


# ------------------------------------------------------------------
# Pruning
# ------------------------------------------------------------------

class TestPruning:
    def test_prune_removes_oldest_quarter(self):
        p = AgentWorkflowProfiler()
        p.__class__.MAX_ENTRIES = 20
        try:
            for i in range(20):
                p.profile("agent-1", "deploy", {"step": i})
            assert p.get_profile_count() == 15  # 20 - 5 (oldest quarter)
        finally:
            p.__class__.MAX_ENTRIES = 10000

    def test_prune_tracks_total_pruned(self):
        p = AgentWorkflowProfiler()
        p.__class__.MAX_ENTRIES = 20
        try:
            for i in range(20):
                p.profile("agent-1", "deploy", {"step": i})
            stats = p.get_stats()
            assert stats["total_pruned"] == 5
        finally:
            p.__class__.MAX_ENTRIES = 10000

    def test_prune_removes_oldest_entries(self):
        p = AgentWorkflowProfiler()
        p.__class__.MAX_ENTRIES = 8
        try:
            ids = []
            for i in range(8):
                ids.append(p.profile("agent-1", "deploy", {"step": i}))
            # The first 2 (oldest quarter of 8) should be gone
            assert p.get_profile(ids[0]) is None
            assert p.get_profile(ids[1]) is None
            # The rest should still exist
            assert p.get_profile(ids[2]) is not None
        finally:
            p.__class__.MAX_ENTRIES = 10000


# ------------------------------------------------------------------
# Unique IDs
# ------------------------------------------------------------------

class TestUniqueIds:
    def test_many_unique_ids(self):
        p = AgentWorkflowProfiler()
        ids = set()
        for i in range(100):
            ids.add(p.profile("agent-1", "deploy", {"step": i}))
        assert len(ids) == 100

    def test_ids_differ_across_agents(self):
        p = AgentWorkflowProfiler()
        id1 = p.profile("agent-1", "deploy", {"d": 1})
        id2 = p.profile("agent-2", "deploy", {"d": 1})
        assert id1 != id2


# ------------------------------------------------------------------
# Metrics isolation
# ------------------------------------------------------------------

class TestMetricsIsolation:
    def test_metrics_are_copied_on_store(self):
        p = AgentWorkflowProfiler()
        metrics = {"duration_ms": 100}
        pid = p.profile("agent-1", "deploy", metrics)
        metrics["duration_ms"] = 999
        entry = p.get_profile(pid)
        assert entry["metrics"]["duration_ms"] == 100

    def test_metadata_are_copied_on_store(self):
        p = AgentWorkflowProfiler()
        metadata = {"env": "prod"}
        pid = p.profile("agent-1", "deploy", {"d": 1}, metadata)
        metadata["env"] = "staging"
        entry = p.get_profile(pid)
        assert entry["metadata"]["env"] == "prod"
