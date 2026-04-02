"""Tests for AgentTaskDelegatorV2 service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_delegator_v2 import AgentTaskDelegatorV2


class TestBasic:
    """Basic delegation creation and field validation."""

    def test_delegate_returns_id_with_prefix(self):
        svc = AgentTaskDelegatorV2()
        rid = svc.delegate_v2("t1", "agent-a")
        assert rid.startswith("atdv-")
        assert len(rid) > 5

    def test_delegate_fields_stored(self):
        svc = AgentTaskDelegatorV2()
        rid = svc.delegate_v2("t1", "agent-a", target_agent="agent-b", metadata={"k": "v"})
        entry = svc.get_delegation(rid)
        assert entry is not None
        assert entry["record_id"] == rid
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "agent-a"
        assert entry["target_agent"] == "agent-b"
        assert entry["metadata"] == {"k": "v"}
        assert "created_at" in entry
        assert "updated_at" in entry

    def test_default_target_agent_empty(self):
        svc = AgentTaskDelegatorV2()
        rid = svc.delegate_v2("t1", "agent-a")
        entry = svc.get_delegation(rid)
        assert entry["target_agent"] == ""

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskDelegatorV2()
        rid = svc.delegate_v2("t1", "a", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_delegation(rid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_empty_task_id_returns_empty(self):
        svc = AgentTaskDelegatorV2()
        assert svc.delegate_v2("", "agent-a") == ""

    def test_empty_agent_id_returns_empty(self):
        svc = AgentTaskDelegatorV2()
        assert svc.delegate_v2("t1", "") == ""

    def test_default_metadata_empty_dict(self):
        svc = AgentTaskDelegatorV2()
        rid = svc.delegate_v2("t1", "a")
        entry = svc.get_delegation(rid)
        assert entry["metadata"] == {}


class TestGet:
    """Getting single delegations."""

    def test_get_existing(self):
        svc = AgentTaskDelegatorV2()
        rid = svc.delegate_v2("t1", "a")
        entry = svc.get_delegation(rid)
        assert entry is not None
        assert isinstance(entry, dict)

    def test_get_nonexistent_returns_none(self):
        svc = AgentTaskDelegatorV2()
        assert svc.get_delegation("atdv-nonexistent") is None

    def test_get_returns_copy(self):
        svc = AgentTaskDelegatorV2()
        rid = svc.delegate_v2("t1", "a")
        e1 = svc.get_delegation(rid)
        e2 = svc.get_delegation(rid)
        assert e1 is not e2
        assert e1 == e2


class TestList:
    """Querying multiple delegations."""

    def test_get_all(self):
        svc = AgentTaskDelegatorV2()
        svc.delegate_v2("t1", "a")
        svc.delegate_v2("t2", "b")
        results = svc.get_delegations()
        assert len(results) == 2

    def test_filter_by_agent_id(self):
        svc = AgentTaskDelegatorV2()
        svc.delegate_v2("t1", "a")
        svc.delegate_v2("t2", "b")
        svc.delegate_v2("t3", "a")
        results = svc.get_delegations(agent_id="a")
        assert len(results) == 2
        assert all(r["agent_id"] == "a" for r in results)

    def test_newest_first(self):
        svc = AgentTaskDelegatorV2()
        id1 = svc.delegate_v2("t1", "a")
        id2 = svc.delegate_v2("t2", "a")
        results = svc.get_delegations()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_respects_limit(self):
        svc = AgentTaskDelegatorV2()
        for i in range(10):
            svc.delegate_v2(f"t{i}", "a")
        results = svc.get_delegations(limit=3)
        assert len(results) == 3


class TestCount:
    """Counting delegations."""

    def test_count_all(self):
        svc = AgentTaskDelegatorV2()
        svc.delegate_v2("t1", "a")
        svc.delegate_v2("t2", "b")
        assert svc.get_delegation_count() == 2

    def test_count_by_agent_id(self):
        svc = AgentTaskDelegatorV2()
        svc.delegate_v2("t1", "a")
        svc.delegate_v2("t2", "b")
        svc.delegate_v2("t3", "a")
        assert svc.get_delegation_count(agent_id="a") == 2
        assert svc.get_delegation_count(agent_id="b") == 1

    def test_count_empty(self):
        svc = AgentTaskDelegatorV2()
        assert svc.get_delegation_count() == 0


class TestStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskDelegatorV2()
        stats = svc.get_stats()
        assert stats["total_delegations"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentTaskDelegatorV2()
        svc.delegate_v2("t1", "a")
        svc.delegate_v2("t2", "b")
        svc.delegate_v2("t3", "a")
        stats = svc.get_stats()
        assert stats["total_delegations"] == 3
        assert stats["unique_agents"] == 2


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_delegate(self):
        events = []
        svc = AgentTaskDelegatorV2()
        svc.on_change = lambda action, **kw: events.append((action, kw))
        svc.delegate_v2("t1", "a")
        assert len(events) == 1
        assert events[0][0] == "delegation_created"

    def test_on_change_getter(self):
        svc = AgentTaskDelegatorV2()
        assert svc.on_change is None
        fn = lambda action, **kw: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskDelegatorV2()
        svc._state.callbacks["cb1"] = lambda action, **kw: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskDelegatorV2()
        svc.on_change = lambda action, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = svc.delegate_v2("t1", "a")
        assert rid.startswith("atdv-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskDelegatorV2()
        svc._state.callbacks["my_cb"] = lambda action, **kw: events.append(action)
        svc.delegate_v2("t1", "a")
        assert "delegation_created" in events

    def test_on_change_receives_details(self):
        details = []
        svc = AgentTaskDelegatorV2()
        svc.on_change = lambda action, **kw: details.append(kw)
        svc.delegate_v2("t1", "a")
        assert "record_id" in details[0]
        assert "task_id" in details[0]


class TestPrune:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_removes_oldest_quarter(self):
        svc = AgentTaskDelegatorV2()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.delegate_v2(f"t{i}", "a"))
        # After exceeding 5, oldest quarter should be removed
        assert svc.get_delegation_count() <= 6
        # The very first entries should have been pruned
        assert svc.get_delegation(ids[0]) is None

    def test_prune_keeps_newest(self):
        svc = AgentTaskDelegatorV2()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.delegate_v2(f"t{i}", "a"))
        # The newest entry should still exist
        assert svc.get_delegation(ids[-1]) is not None


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskDelegatorV2()
        svc.delegate_v2("t1", "a")
        svc.reset()
        assert svc.get_delegation_count() == 0
        assert svc.get_stats()["total_delegations"] == 0

    def test_reset_clears_on_change(self):
        svc = AgentTaskDelegatorV2()
        svc.on_change = lambda action, **kw: None
        svc.reset()
        assert svc.on_change is None

    def test_reset_clears_callbacks(self):
        svc = AgentTaskDelegatorV2()
        svc._state.callbacks["cb1"] = lambda action, **kw: None
        svc.reset()
        assert svc.remove_callback("cb1") is False
