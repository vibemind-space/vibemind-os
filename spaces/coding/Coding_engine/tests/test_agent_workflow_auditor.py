"""Tests for AgentWorkflowAuditor service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_auditor import AgentWorkflowAuditor


# ------------------------------------------------------------------
# Audit basics
# ------------------------------------------------------------------

class TestAudit:
    def test_audit_returns_id_with_prefix(self):
        a = AgentWorkflowAuditor()
        aid = a.audit("agent-1", "deploy", "started")
        assert aid.startswith("awau-")
        assert len(aid) > len("awau-")

    def test_audit_unique_ids(self):
        a = AgentWorkflowAuditor()
        ids = {a.audit("agent-1", "deploy", "started") for _ in range(20)}
        assert len(ids) == 20

    def test_audit_stores_details(self):
        a = AgentWorkflowAuditor()
        aid = a.audit("agent-1", "deploy", "started", {"env": "prod"})
        entry = a.get_audit(aid)
        assert entry["details"] == {"env": "prod"}

    def test_audit_default_details_is_empty_dict(self):
        a = AgentWorkflowAuditor()
        aid = a.audit("agent-1", "deploy", "started")
        entry = a.get_audit(aid)
        assert entry["details"] == {}

    def test_audit_records_created_at(self):
        a = AgentWorkflowAuditor()
        before = time.time()
        aid = a.audit("agent-1", "deploy", "started")
        after = time.time()
        entry = a.get_audit(aid)
        assert before <= entry["created_at"] <= after


# ------------------------------------------------------------------
# get_audit
# ------------------------------------------------------------------

class TestGetAudit:
    def test_get_audit_returns_entry(self):
        a = AgentWorkflowAuditor()
        aid = a.audit("agent-1", "deploy", "started")
        entry = a.get_audit(aid)
        assert isinstance(entry, dict)
        assert entry["audit_id"] == aid
        assert entry["agent_id"] == "agent-1"
        assert entry["workflow_name"] == "deploy"
        assert entry["action"] == "started"

    def test_get_audit_not_found(self):
        a = AgentWorkflowAuditor()
        assert a.get_audit("awau-nonexistent") is None

    def test_get_audit_returns_copy(self):
        a = AgentWorkflowAuditor()
        aid = a.audit("agent-1", "deploy", "started", {"key": "val"})
        e1 = a.get_audit(aid)
        e2 = a.get_audit(aid)
        assert e1 is not e2
        e1["details"]["key"] = "modified"
        e3 = a.get_audit(aid)
        assert e3["details"]["key"] == "val"


# ------------------------------------------------------------------
# get_audits (filtering, sorting, limit)
# ------------------------------------------------------------------

class TestGetAudits:
    def test_get_audits_all(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.audit("agent-2", "build", "started")
        results = a.get_audits()
        assert len(results) == 2

    def test_get_audits_filter_by_agent(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.audit("agent-2", "build", "started")
        a.audit("agent-1", "test", "completed")
        results = a.get_audits(agent_id="agent-1")
        assert len(results) == 2
        assert all(e["agent_id"] == "agent-1" for e in results)

    def test_get_audits_filter_by_workflow(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.audit("agent-1", "build", "started")
        a.audit("agent-2", "deploy", "completed")
        results = a.get_audits(workflow_name="deploy")
        assert len(results) == 2
        assert all(e["workflow_name"] == "deploy" for e in results)

    def test_get_audits_filter_by_agent_and_workflow(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.audit("agent-1", "build", "started")
        a.audit("agent-2", "deploy", "completed")
        results = a.get_audits(agent_id="agent-1", workflow_name="deploy")
        assert len(results) == 1
        assert results[0]["agent_id"] == "agent-1"
        assert results[0]["workflow_name"] == "deploy"

    def test_get_audits_sorted_newest_first(self):
        a = AgentWorkflowAuditor()
        id1 = a.audit("agent-1", "deploy", "step-1")
        id2 = a.audit("agent-1", "deploy", "step-2")
        id3 = a.audit("agent-1", "deploy", "step-3")
        results = a.get_audits(agent_id="agent-1")
        assert results[0]["audit_id"] == id3
        assert results[1]["audit_id"] == id2
        assert results[2]["audit_id"] == id1

    def test_get_audits_limit(self):
        a = AgentWorkflowAuditor()
        for i in range(10):
            a.audit("agent-1", "deploy", f"step-{i}")
        results = a.get_audits(limit=3)
        assert len(results) == 3

    def test_get_audits_default_limit_50(self):
        a = AgentWorkflowAuditor()
        for i in range(60):
            a.audit("agent-1", "deploy", f"step-{i}")
        results = a.get_audits()
        assert len(results) == 50

    def test_get_audits_returns_copies(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started", {"k": "v"})
        results = a.get_audits()
        results[0]["details"]["k"] = "changed"
        fresh = a.get_audits()
        assert fresh[0]["details"]["k"] == "v"


# ------------------------------------------------------------------
# get_audit_count
# ------------------------------------------------------------------

class TestGetAuditCount:
    def test_count_all(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.audit("agent-2", "build", "started")
        assert a.get_audit_count() == 2

    def test_count_by_agent(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.audit("agent-2", "build", "started")
        a.audit("agent-1", "test", "completed")
        assert a.get_audit_count(agent_id="agent-1") == 2
        assert a.get_audit_count(agent_id="agent-2") == 1

    def test_count_empty(self):
        a = AgentWorkflowAuditor()
        assert a.get_audit_count() == 0
        assert a.get_audit_count(agent_id="ghost") == 0


# ------------------------------------------------------------------
# get_stats
# ------------------------------------------------------------------

class TestGetStats:
    def test_stats_initial(self):
        a = AgentWorkflowAuditor()
        stats = a.get_stats()
        assert stats["current_entries"] == 0
        assert stats["total_audited"] == 0
        assert stats["total_pruned"] == 0
        assert stats["total_queries"] == 0
        assert stats["max_entries"] == 10000
        assert stats["callbacks"] == 0

    def test_stats_after_audit(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.audit("agent-1", "deploy", "completed")
        stats = a.get_stats()
        assert stats["current_entries"] == 2
        assert stats["total_audited"] == 2

    def test_stats_tracks_queries(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.get_audits()
        a.get_audits()
        stats = a.get_stats()
        assert stats["total_queries"] == 2


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------

class TestReset:
    def test_reset_clears_entries(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.reset()
        assert a.get_audit_count() == 0
        stats = a.get_stats()
        assert stats["current_entries"] == 0
        assert stats["total_audited"] == 0

    def test_reset_clears_callbacks(self):
        a = AgentWorkflowAuditor()
        a._callbacks["cb1"] = lambda action, data: None
        a.on_change = lambda action, data: None
        a.reset()
        assert len(a._callbacks) == 0
        assert a.on_change is None

    def test_reset_clears_seq(self):
        a = AgentWorkflowAuditor()
        a.audit("agent-1", "deploy", "started")
        a.reset()
        assert a._state._seq == 0


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------

class TestCallbacks:
    def test_on_change_property(self):
        a = AgentWorkflowAuditor()
        assert a.on_change is None
        fn = lambda action, data: None
        a.on_change = fn
        assert a.on_change is fn

    def test_on_change_called_on_audit(self):
        a = AgentWorkflowAuditor()
        calls = []
        a.on_change = lambda action, data: calls.append((action, data))
        a.audit("agent-1", "deploy", "started")
        assert len(calls) == 1
        assert calls[0][0] == "audit_recorded"
        assert calls[0][1]["agent_id"] == "agent-1"

    def test_callback_called_on_audit(self):
        a = AgentWorkflowAuditor()
        calls = []
        a._callbacks["cb1"] = lambda action, data: calls.append((action, data))
        a.audit("agent-1", "deploy", "started")
        assert len(calls) == 1
        assert calls[0][0] == "audit_recorded"

    def test_on_change_called_before_callbacks(self):
        a = AgentWorkflowAuditor()
        order = []
        a.on_change = lambda action, data: order.append("on_change")
        a._callbacks["cb1"] = lambda action, data: order.append("cb1")
        a.audit("agent-1", "deploy", "started")
        assert order == ["on_change", "cb1"]

    def test_callback_exception_silenced(self):
        a = AgentWorkflowAuditor()
        a._callbacks["bad"] = lambda action, data: 1 / 0
        # Should not raise
        aid = a.audit("agent-1", "deploy", "started")
        assert aid.startswith("awau-")

    def test_on_change_exception_silenced(self):
        a = AgentWorkflowAuditor()
        a.on_change = lambda action, data: 1 / 0
        aid = a.audit("agent-1", "deploy", "started")
        assert aid.startswith("awau-")

    def test_remove_callback_returns_true(self):
        a = AgentWorkflowAuditor()
        a._callbacks["cb1"] = lambda action, data: None
        assert a.remove_callback("cb1") is True
        assert "cb1" not in a._callbacks

    def test_remove_callback_returns_false_if_not_found(self):
        a = AgentWorkflowAuditor()
        assert a.remove_callback("nonexistent") is False


# ------------------------------------------------------------------
# Pruning
# ------------------------------------------------------------------

class TestPruning:
    def test_prune_removes_oldest_quarter(self):
        a = AgentWorkflowAuditor()
        a.__class__.MAX_ENTRIES = 20  # temporarily lower for test
        try:
            for i in range(20):
                a.audit("agent-1", "deploy", f"step-{i}")
            assert a.get_audit_count() == 15  # 20 - 5 (oldest quarter)
        finally:
            a.__class__.MAX_ENTRIES = 10000

    def test_prune_tracks_total_pruned(self):
        a = AgentWorkflowAuditor()
        a.__class__.MAX_ENTRIES = 20
        try:
            for i in range(20):
                a.audit("agent-1", "deploy", f"step-{i}")
            stats = a.get_stats()
            assert stats["total_pruned"] == 5
        finally:
            a.__class__.MAX_ENTRIES = 10000

    def test_prune_removes_oldest_entries(self):
        a = AgentWorkflowAuditor()
        a.__class__.MAX_ENTRIES = 8
        try:
            ids = []
            for i in range(8):
                ids.append(a.audit("agent-1", "deploy", f"step-{i}"))
            # The first 2 (oldest quarter of 8) should be gone
            assert a.get_audit(ids[0]) is None
            assert a.get_audit(ids[1]) is None
            # The rest should still exist
            assert a.get_audit(ids[2]) is not None
        finally:
            a.__class__.MAX_ENTRIES = 10000


# ------------------------------------------------------------------
# Unique IDs
# ------------------------------------------------------------------

class TestUniqueIds:
    def test_many_unique_ids(self):
        a = AgentWorkflowAuditor()
        ids = set()
        for i in range(100):
            ids.add(a.audit("agent-1", "deploy", f"step-{i}"))
        assert len(ids) == 100

    def test_ids_differ_across_agents(self):
        a = AgentWorkflowAuditor()
        id1 = a.audit("agent-1", "deploy", "started")
        id2 = a.audit("agent-2", "deploy", "started")
        assert id1 != id2
