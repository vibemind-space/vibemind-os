"""Tests for AgentWorkflowInspector service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_inspector import AgentWorkflowInspector


# ------------------------------------------------------------------
# Inspect basics
# ------------------------------------------------------------------

class TestInspect:
    def test_inspect_returns_id_with_prefix(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "all clear")
        assert iid.startswith("awin-")
        assert len(iid) > len("awin-")

    def test_inspect_unique_ids(self):
        i = AgentWorkflowInspector()
        ids = {i.inspect("agent-1", "deploy", "ok") for _ in range(20)}
        assert len(ids) == 20

    def test_inspect_stores_metadata(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "drift", metadata={"env": "prod"})
        entry = i.get_inspection(iid)
        assert entry["metadata"] == {"env": "prod"}

    def test_inspect_default_metadata_is_empty_dict(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "ok")
        entry = i.get_inspection(iid)
        assert entry["metadata"] == {}

    def test_inspect_default_severity_is_info(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "ok")
        entry = i.get_inspection(iid)
        assert entry["severity"] == "info"

    def test_inspect_custom_severity(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "bad config", severity="error")
        entry = i.get_inspection(iid)
        assert entry["severity"] == "error"

    def test_inspect_records_created_at(self):
        i = AgentWorkflowInspector()
        before = time.time()
        iid = i.inspect("agent-1", "deploy", "ok")
        after = time.time()
        entry = i.get_inspection(iid)
        assert before <= entry["created_at"] <= after

    def test_inspect_stores_findings(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "config drift detected")
        entry = i.get_inspection(iid)
        assert entry["findings"] == "config drift detected"


# ------------------------------------------------------------------
# get_inspection
# ------------------------------------------------------------------

class TestGetInspection:
    def test_get_inspection_returns_entry(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "ok")
        entry = i.get_inspection(iid)
        assert isinstance(entry, dict)
        assert entry["inspection_id"] == iid
        assert entry["agent_id"] == "agent-1"
        assert entry["workflow_name"] == "deploy"
        assert entry["findings"] == "ok"

    def test_get_inspection_not_found(self):
        i = AgentWorkflowInspector()
        assert i.get_inspection("awin-nonexistent") is None

    def test_get_inspection_returns_copy(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "ok", metadata={"key": "val"})
        e1 = i.get_inspection(iid)
        e2 = i.get_inspection(iid)
        assert e1 is not e2

    def test_get_inspection_mutation_does_not_affect_store(self):
        i = AgentWorkflowInspector()
        iid = i.inspect("agent-1", "deploy", "ok", metadata={"key": "val"})
        e1 = i.get_inspection(iid)
        e1["findings"] = "tampered"
        e2 = i.get_inspection(iid)
        assert e2["findings"] == "ok"


# ------------------------------------------------------------------
# get_inspections (filtering, sorting, limit)
# ------------------------------------------------------------------

class TestGetInspections:
    def test_get_inspections_all(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.inspect("agent-2", "build", "ok")
        results = i.get_inspections()
        assert len(results) == 2

    def test_get_inspections_filter_by_agent(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.inspect("agent-2", "build", "ok")
        i.inspect("agent-1", "test", "ok")
        results = i.get_inspections(agent_id="agent-1")
        assert len(results) == 2
        assert all(e["agent_id"] == "agent-1" for e in results)

    def test_get_inspections_filter_by_severity(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok", severity="info")
        i.inspect("agent-1", "build", "bad", severity="error")
        i.inspect("agent-2", "deploy", "warn", severity="warning")
        results = i.get_inspections(severity="error")
        assert len(results) == 1
        assert results[0]["severity"] == "error"

    def test_get_inspections_filter_by_agent_and_severity(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok", severity="info")
        i.inspect("agent-1", "build", "bad", severity="error")
        i.inspect("agent-2", "deploy", "bad", severity="error")
        results = i.get_inspections(agent_id="agent-1", severity="error")
        assert len(results) == 1
        assert results[0]["agent_id"] == "agent-1"
        assert results[0]["severity"] == "error"

    def test_get_inspections_sorted_newest_first(self):
        i = AgentWorkflowInspector()
        id1 = i.inspect("agent-1", "deploy", "step-1")
        id2 = i.inspect("agent-1", "deploy", "step-2")
        id3 = i.inspect("agent-1", "deploy", "step-3")
        results = i.get_inspections(agent_id="agent-1")
        assert results[0]["inspection_id"] == id3
        assert results[1]["inspection_id"] == id2
        assert results[2]["inspection_id"] == id1

    def test_get_inspections_limit(self):
        i = AgentWorkflowInspector()
        for n in range(10):
            i.inspect("agent-1", "deploy", f"step-{n}")
        results = i.get_inspections(limit=3)
        assert len(results) == 3

    def test_get_inspections_default_limit_50(self):
        i = AgentWorkflowInspector()
        for n in range(60):
            i.inspect("agent-1", "deploy", f"step-{n}")
        results = i.get_inspections()
        assert len(results) == 50

    def test_get_inspections_returns_copies(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok", metadata={"k": "v"})
        results = i.get_inspections()
        results[0]["metadata"]["k"] = "changed"
        fresh = i.get_inspections()
        assert fresh[0]["metadata"]["k"] == "v"


# ------------------------------------------------------------------
# get_inspection_count
# ------------------------------------------------------------------

class TestGetInspectionCount:
    def test_count_all(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.inspect("agent-2", "build", "ok")
        assert i.get_inspection_count() == 2

    def test_count_by_agent(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.inspect("agent-2", "build", "ok")
        i.inspect("agent-1", "test", "ok")
        assert i.get_inspection_count(agent_id="agent-1") == 2
        assert i.get_inspection_count(agent_id="agent-2") == 1

    def test_count_empty(self):
        i = AgentWorkflowInspector()
        assert i.get_inspection_count() == 0
        assert i.get_inspection_count(agent_id="ghost") == 0


# ------------------------------------------------------------------
# get_stats
# ------------------------------------------------------------------

class TestGetStats:
    def test_stats_initial(self):
        i = AgentWorkflowInspector()
        stats = i.get_stats()
        assert stats["current_entries"] == 0
        assert stats["total_inspected"] == 0
        assert stats["total_pruned"] == 0
        assert stats["total_queries"] == 0
        assert stats["max_entries"] == 10000
        assert stats["callbacks"] == 0

    def test_stats_after_inspect(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.inspect("agent-1", "deploy", "ok")
        stats = i.get_stats()
        assert stats["current_entries"] == 2
        assert stats["total_inspected"] == 2

    def test_stats_tracks_queries(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.get_inspections()
        i.get_inspections()
        stats = i.get_stats()
        assert stats["total_queries"] == 2


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------

class TestReset:
    def test_reset_clears_entries(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.reset()
        assert i.get_inspection_count() == 0
        stats = i.get_stats()
        assert stats["current_entries"] == 0
        assert stats["total_inspected"] == 0

    def test_reset_clears_callbacks(self):
        i = AgentWorkflowInspector()
        i._callbacks["cb1"] = lambda action, data: None
        i.on_change = lambda action, data: None
        i.reset()
        assert len(i._callbacks) == 0
        assert i.on_change is None

    def test_reset_clears_seq(self):
        i = AgentWorkflowInspector()
        i.inspect("agent-1", "deploy", "ok")
        i.reset()
        assert i._state._seq == 0


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------

class TestCallbacks:
    def test_on_change_property(self):
        i = AgentWorkflowInspector()
        assert i.on_change is None
        fn = lambda action, data: None
        i.on_change = fn
        assert i.on_change is fn

    def test_on_change_called_on_inspect(self):
        i = AgentWorkflowInspector()
        calls = []
        i.on_change = lambda action, data: calls.append((action, data))
        i.inspect("agent-1", "deploy", "ok")
        assert len(calls) == 1
        assert calls[0][0] == "inspection_recorded"
        assert calls[0][1]["agent_id"] == "agent-1"

    def test_callback_called_on_inspect(self):
        i = AgentWorkflowInspector()
        calls = []
        i._callbacks["cb1"] = lambda action, data: calls.append((action, data))
        i.inspect("agent-1", "deploy", "ok")
        assert len(calls) == 1
        assert calls[0][0] == "inspection_recorded"

    def test_on_change_called_before_callbacks(self):
        i = AgentWorkflowInspector()
        order = []
        i.on_change = lambda action, data: order.append("on_change")
        i._callbacks["cb1"] = lambda action, data: order.append("cb1")
        i.inspect("agent-1", "deploy", "ok")
        assert order == ["on_change", "cb1"]

    def test_callback_exception_silenced(self):
        i = AgentWorkflowInspector()
        i._callbacks["bad"] = lambda action, data: 1 / 0
        iid = i.inspect("agent-1", "deploy", "ok")
        assert iid.startswith("awin-")

    def test_on_change_exception_silenced(self):
        i = AgentWorkflowInspector()
        i.on_change = lambda action, data: 1 / 0
        iid = i.inspect("agent-1", "deploy", "ok")
        assert iid.startswith("awin-")

    def test_remove_callback_returns_true(self):
        i = AgentWorkflowInspector()
        i._callbacks["cb1"] = lambda action, data: None
        assert i.remove_callback("cb1") is True
        assert "cb1" not in i._callbacks

    def test_remove_callback_returns_false_if_not_found(self):
        i = AgentWorkflowInspector()
        assert i.remove_callback("nonexistent") is False


# ------------------------------------------------------------------
# Pruning
# ------------------------------------------------------------------

class TestPruning:
    def test_prune_removes_oldest_quarter(self):
        i = AgentWorkflowInspector()
        i.__class__.MAX_ENTRIES = 20
        try:
            for n in range(20):
                i.inspect("agent-1", "deploy", f"step-{n}")
            assert i.get_inspection_count() == 15  # 20 - 5 (oldest quarter)
        finally:
            i.__class__.MAX_ENTRIES = 10000

    def test_prune_tracks_total_pruned(self):
        i = AgentWorkflowInspector()
        i.__class__.MAX_ENTRIES = 20
        try:
            for n in range(20):
                i.inspect("agent-1", "deploy", f"step-{n}")
            stats = i.get_stats()
            assert stats["total_pruned"] == 5
        finally:
            i.__class__.MAX_ENTRIES = 10000

    def test_prune_removes_oldest_entries(self):
        i = AgentWorkflowInspector()
        i.__class__.MAX_ENTRIES = 8
        try:
            ids = []
            for n in range(8):
                ids.append(i.inspect("agent-1", "deploy", f"step-{n}"))
            # The first 2 (oldest quarter of 8) should be gone
            assert i.get_inspection(ids[0]) is None
            assert i.get_inspection(ids[1]) is None
            # The rest should still exist
            assert i.get_inspection(ids[2]) is not None
        finally:
            i.__class__.MAX_ENTRIES = 10000


# ------------------------------------------------------------------
# Unique IDs
# ------------------------------------------------------------------

class TestUniqueIds:
    def test_many_unique_ids(self):
        i = AgentWorkflowInspector()
        ids = set()
        for n in range(100):
            ids.add(i.inspect("agent-1", "deploy", f"step-{n}"))
        assert len(ids) == 100

    def test_ids_differ_across_agents(self):
        i = AgentWorkflowInspector()
        id1 = i.inspect("agent-1", "deploy", "ok")
        id2 = i.inspect("agent-2", "deploy", "ok")
        assert id1 != id2
