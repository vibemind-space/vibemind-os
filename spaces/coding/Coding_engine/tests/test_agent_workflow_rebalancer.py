"""Tests for AgentWorkflowRebalancer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_rebalancer import AgentWorkflowRebalancer


class TestRebalanceBasic:
    """Basic rebalance and retrieval."""

    def test_rebalance_returns_id_with_prefix(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1")
        assert rid.startswith("awrb-")
        assert len(rid) > 5

    def test_rebalance_fields(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1", strategy="round_robin")
        entry = svc.get_rebalance(rid)
        assert entry is not None
        assert entry["record_id"] == rid
        assert entry["agent_id"] == "a1"
        assert entry["workflow_name"] == "wf1"
        assert entry["strategy"] == "round_robin"
        assert "created_at" in entry
        assert isinstance(entry["created_at"], float)
        assert "seq" in entry

    def test_default_strategy_is_even(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1")
        entry = svc.get_rebalance(rid)
        assert entry["strategy"] == "even"

    def test_metadata_deepcopy(self):
        meta = {"nested": {"x": 1}}
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_rebalance(rid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1")
        entry = svc.get_rebalance(rid)
        assert entry["metadata"] == {}

    def test_empty_agent_id_returns_empty_string(self):
        svc = AgentWorkflowRebalancer()
        assert svc.rebalance("", "wf1") == ""

    def test_empty_workflow_name_returns_empty_string(self):
        svc = AgentWorkflowRebalancer()
        assert svc.rebalance("a1", "") == ""

    def test_both_empty_returns_empty_string(self):
        svc = AgentWorkflowRebalancer()
        assert svc.rebalance("", "") == ""


class TestGetRebalance:
    """Get single rebalance record."""

    def test_get_found(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1")
        entry = svc.get_rebalance(rid)
        assert entry is not None
        assert entry["agent_id"] == "a1"

    def test_get_not_found(self):
        svc = AgentWorkflowRebalancer()
        assert svc.get_rebalance("awrb-nonexistent") is None

    def test_get_returns_copy(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1")
        entry = svc.get_rebalance(rid)
        entry["agent_id"] = "mutated"
        original = svc.get_rebalance(rid)
        assert original["agent_id"] == "a1"


class TestGetRebalances:
    """Querying multiple rebalance records."""

    def test_get_all(self):
        svc = AgentWorkflowRebalancer()
        svc.rebalance("a1", "wf1")
        svc.rebalance("a2", "wf2")
        results = svc.get_rebalances()
        assert len(results) == 2

    def test_filter_by_agent(self):
        svc = AgentWorkflowRebalancer()
        svc.rebalance("a1", "wf1")
        svc.rebalance("a2", "wf2")
        svc.rebalance("a1", "wf3")
        results = svc.get_rebalances(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_newest_first(self):
        svc = AgentWorkflowRebalancer()
        id1 = svc.rebalance("a1", "wf1")
        id2 = svc.rebalance("a1", "wf2")
        results = svc.get_rebalances()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_respects_limit(self):
        svc = AgentWorkflowRebalancer()
        for i in range(10):
            svc.rebalance("a1", f"wf{i}")
        results = svc.get_rebalances(limit=3)
        assert len(results) == 3

    def test_empty(self):
        svc = AgentWorkflowRebalancer()
        results = svc.get_rebalances()
        assert results == []

    def test_returns_copies(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1")
        results = svc.get_rebalances()
        results[0]["agent_id"] = "mutated"
        entry = svc.get_rebalance(rid)
        assert entry["agent_id"] == "a1"


class TestGetRebalanceCount:
    """Counting rebalances."""

    def test_count_all(self):
        svc = AgentWorkflowRebalancer()
        svc.rebalance("a1", "wf1")
        svc.rebalance("a2", "wf2")
        assert svc.get_rebalance_count() == 2

    def test_count_by_agent(self):
        svc = AgentWorkflowRebalancer()
        svc.rebalance("a1", "wf1")
        svc.rebalance("a2", "wf2")
        svc.rebalance("a1", "wf3")
        assert svc.get_rebalance_count(agent_id="a1") == 2
        assert svc.get_rebalance_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentWorkflowRebalancer()
        assert svc.get_rebalance_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentWorkflowRebalancer()
        stats = svc.get_stats()
        assert stats["total_rebalances"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentWorkflowRebalancer()
        svc.rebalance("a1", "wf1")
        svc.rebalance("a2", "wf2")
        svc.rebalance("a1", "wf3")
        stats = svc.get_stats()
        assert stats["total_rebalances"] == 3
        assert stats["unique_agents"] == 2

    def test_stats_returns_dict(self):
        svc = AgentWorkflowRebalancer()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_rebalance(self):
        events = []
        svc = AgentWorkflowRebalancer()
        svc.on_change = lambda action: events.append(action)
        svc.rebalance("a1", "wf1")
        assert len(events) == 1
        assert events[0] == "rebalance"

    def test_on_change_getter(self):
        svc = AgentWorkflowRebalancer()
        assert svc.on_change is None
        fn = lambda a: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentWorkflowRebalancer()
        svc._state.callbacks["cb1"] = lambda a: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_remove_callback_nonexistent(self):
        svc = AgentWorkflowRebalancer()
        assert svc.remove_callback("nope") is False

    def test_callback_exception_silenced(self):
        svc = AgentWorkflowRebalancer()
        svc.on_change = lambda a: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = svc.rebalance("a1", "wf1")
        assert rid.startswith("awrb-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentWorkflowRebalancer()
        svc._state.callbacks["my_cb"] = lambda action: events.append(action)
        svc.rebalance("a1", "wf1")
        assert "rebalance" in events

    def test_named_callback_exception_silenced(self):
        svc = AgentWorkflowRebalancer()
        svc._state.callbacks["bad"] = lambda a: (_ for _ in ()).throw(ValueError("x"))
        rid = svc.rebalance("a1", "wf1")
        assert rid.startswith("awrb-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentWorkflowRebalancer()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.rebalance("a1", f"wf{i}"))
        assert svc.get_rebalance(ids[0]) is None
        assert svc.get_rebalance_count() <= 5

    def test_prune_keeps_newest(self):
        svc = AgentWorkflowRebalancer()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.rebalance("a1", f"wf{i}"))
        assert svc.get_rebalance(ids[-1]) is not None


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowRebalancer()
        svc.rebalance("a1", "wf1")
        svc.reset()
        assert svc.get_rebalance_count() == 0
        assert svc.get_stats()["total_rebalances"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowRebalancer()
        svc._state.callbacks["cb1"] = lambda a: None
        svc.on_change = lambda a: None
        svc.reset()
        assert svc.on_change is None
        assert len(svc._state.callbacks) == 0

    def test_reset_allows_new_rebalances(self):
        svc = AgentWorkflowRebalancer()
        svc.rebalance("a1", "wf1")
        svc.reset()
        rid = svc.rebalance("a2", "wf2")
        assert rid.startswith("awrb-")
        assert svc.get_rebalance_count() == 1


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentWorkflowRebalancer()
        ids = set()
        for i in range(50):
            ids.add(svc.rebalance("a1", f"wf{i}"))
        assert len(ids) == 50

    def test_id_prefix(self):
        svc = AgentWorkflowRebalancer()
        rid = svc.rebalance("a1", "wf1")
        assert rid.startswith("awrb-")
