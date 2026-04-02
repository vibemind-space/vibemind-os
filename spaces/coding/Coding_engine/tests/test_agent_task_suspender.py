"""Tests for AgentTaskSuspender service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_suspender import AgentTaskSuspender


class TestIdGeneration:
    """ID prefix and uniqueness."""

    def test_prefix(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1")
        assert rid.startswith("atsu-")

    def test_id_length(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1")
        assert len(rid) > 5

    def test_unique_ids(self):
        svc = AgentTaskSuspender()
        ids = {svc.suspend(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20


class TestSuspendBasic:
    """Basic suspend and retrieval."""

    def test_returns_non_empty(self):
        svc = AgentTaskSuspender()
        assert len(svc.suspend("t1", "a1")) > 0

    def test_stores_fields(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1", reason="overload")
        e = svc.get_suspension(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["reason"] == "overload"

    def test_created_at_timestamp(self):
        svc = AgentTaskSuspender()
        before = time.time()
        rid = svc.suspend("t1", "a1")
        assert svc.get_suspension(rid)["created_at"] >= before


class TestSuspendValidation:
    """Validation: empty ids return empty string."""

    def test_empty_task_id(self):
        assert AgentTaskSuspender().suspend("", "a1") == ""

    def test_empty_agent_id(self):
        assert AgentTaskSuspender().suspend("t1", "") == ""

    def test_both_empty(self):
        assert AgentTaskSuspender().suspend("", "") == ""


class TestReasonAndMetadata:
    """Reason and metadata handling."""

    def test_reason_stored(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1", reason="maintenance")
        assert svc.get_suspension(rid)["reason"] == "maintenance"

    def test_default_reason_empty(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1")
        assert svc.get_suspension(rid)["reason"] == ""

    def test_metadata_stored(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1", metadata={"x": 1})
        assert svc.get_suspension(rid)["metadata"]["x"] == 1

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        assert svc.get_suspension(rid)["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1")
        assert svc.get_suspension(rid)["metadata"] == {}


class TestGetSuspension:
    """Single suspension retrieval."""

    def test_found(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1")
        assert svc.get_suspension(rid) is not None

    def test_not_found(self):
        assert AgentTaskSuspender().get_suspension("xxx") is None

    def test_returns_copy(self):
        svc = AgentTaskSuspender()
        rid = svc.suspend("t1", "a1")
        a = svc.get_suspension(rid)
        b = svc.get_suspension(rid)
        assert a is not b


class TestGetSuspensions:
    """Querying multiple suspensions."""

    def test_get_all(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.suspend("t2", "a2")
        assert len(svc.get_suspensions()) == 2

    def test_filter_by_agent(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.suspend("t2", "a2")
        svc.suspend("t3", "a1")
        results = svc.get_suspensions(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_newest_first(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.suspend("t2", "a1")
        assert svc.get_suspensions(agent_id="a1")[0]["task_id"] == "t2"

    def test_ordering_tiebreak(self):
        svc = AgentTaskSuspender()
        id1 = svc.suspend("t1", "a1")
        id2 = svc.suspend("t2", "a1")
        id3 = svc.suspend("t3", "a1")
        results = svc.get_suspensions()
        assert results[0]["record_id"] == id3
        assert results[2]["record_id"] == id1

    def test_limit(self):
        svc = AgentTaskSuspender()
        for i in range(10):
            svc.suspend(f"t{i}", "a1")
        assert len(svc.get_suspensions(limit=3)) == 3

    def test_empty_for_unknown_agent(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        assert svc.get_suspensions(agent_id="unknown") == []


class TestGetSuspensionCount:
    """Counting suspensions."""

    def test_total(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.suspend("t2", "a2")
        assert svc.get_suspension_count() == 2

    def test_filtered(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.suspend("t2", "a2")
        svc.suspend("t3", "a1")
        assert svc.get_suspension_count(agent_id="a1") == 2
        assert svc.get_suspension_count(agent_id="a2") == 1

    def test_empty(self):
        assert AgentTaskSuspender().get_suspension_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        stats = AgentTaskSuspender().get_stats()
        assert stats["total_suspensions"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.suspend("t2", "a2")
        svc.suspend("t3", "a1")
        stats = svc.get_stats()
        assert stats["total_suspensions"] == 3
        assert stats["unique_agents"] == 2


class TestOnChange:
    """on_change callback."""

    def test_on_change_default_none(self):
        assert AgentTaskSuspender().on_change is None

    def test_on_change_getter_setter(self):
        svc = AgentTaskSuspender()
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_on_change_fires(self):
        events = []
        svc = AgentTaskSuspender()
        svc.on_change = lambda action, data: events.append(action)
        svc.suspend("t1", "a1")
        assert "suspend" in events

    def test_on_change_set_to_none(self):
        svc = AgentTaskSuspender()
        svc.on_change = lambda a, d: None
        svc.on_change = None
        assert svc.on_change is None

    def test_on_change_exception_silenced(self):
        svc = AgentTaskSuspender()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError)
        assert svc.suspend("t1", "a1").startswith("atsu-")


class TestRemoveCallback:
    """remove_callback return values."""

    def test_remove_existing_returns_true(self):
        svc = AgentTaskSuspender()
        svc._state.callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True

    def test_remove_nonexistent_returns_false(self):
        assert AgentTaskSuspender().remove_callback("x") is False

    def test_named_callback_fires(self):
        events = []
        svc = AgentTaskSuspender()
        svc._state.callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.suspend("t1", "a1")
        assert "suspend" in events

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskSuspender()
        svc._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError)
        assert svc.suspend("t1", "a1").startswith("atsu-")


class TestPrune:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_reduces_count(self):
        svc = AgentTaskSuspender()
        svc.MAX_ENTRIES = 5
        for i in range(8):
            svc.suspend(f"t{i}", "a1")
        assert svc.get_suspension_count() < 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskSuspender()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(7):
            ids.append(svc.suspend(f"t{i}", "a1"))
        assert svc.get_suspension(ids[-1]) is not None


class TestReset:
    """Reset clears all state."""

    def test_clears_entries(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.reset()
        assert svc.get_suspension_count() == 0
        assert svc.get_stats()["total_suspensions"] == 0

    def test_clears_callbacks(self):
        svc = AgentTaskSuspender()
        svc._state.callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._state.callbacks) == 0
        assert svc.on_change is None

    def test_allows_new_entries(self):
        svc = AgentTaskSuspender()
        svc.suspend("t1", "a1")
        svc.reset()
        rid = svc.suspend("t2", "a2")
        assert rid.startswith("atsu-")
        assert svc.get_suspension_count() == 1
