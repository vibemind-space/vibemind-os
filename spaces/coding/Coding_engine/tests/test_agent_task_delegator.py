"""Tests for AgentTaskDelegator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_delegator import AgentTaskDelegator


class TestDelegateBasic:
    """Basic delegation creation and retrieval."""

    def test_delegate_returns_id(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "agent-a", "agent-b")
        assert did.startswith("atdl-")
        assert len(did) > 5

    def test_delegate_empty_task_id_returns_empty(self):
        svc = AgentTaskDelegator()
        assert svc.delegate("", "agent-a", "agent-b") == ""

    def test_delegate_empty_from_agent_returns_empty(self):
        svc = AgentTaskDelegator()
        assert svc.delegate("t1", "", "agent-b") == ""

    def test_delegate_empty_to_agent_returns_empty(self):
        svc = AgentTaskDelegator()
        assert svc.delegate("t1", "agent-a", "") == ""

    def test_get_delegation_existing(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "agent-a", "agent-b", reason="needs work", metadata={"k": "v"})
        entry = svc.get_delegation(did)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["from_agent"] == "agent-a"
        assert entry["to_agent"] == "agent-b"
        assert entry["reason"] == "needs work"
        assert entry["status"] == "pending"
        assert entry["metadata"] == {"k": "v"}

    def test_get_delegation_nonexistent(self):
        svc = AgentTaskDelegator()
        assert svc.get_delegation("atdl-nonexistent") is None

    def test_default_reason_is_empty(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "agent-a", "agent-b")
        entry = svc.get_delegation(did)
        assert entry["reason"] == ""

    def test_default_status_is_pending(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "agent-a", "agent-b")
        entry = svc.get_delegation(did)
        assert entry["status"] == "pending"


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b", metadata={"key": "val"})
        entry = svc.get_delegation(did)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_delegation(did)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        entry = svc.get_delegation(did)
        assert entry["metadata"] == {}


class TestAcceptDelegation:
    """Accepting delegations."""

    def test_accept_pending_delegation(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        assert svc.accept_delegation(did) is True
        entry = svc.get_delegation(did)
        assert entry["status"] == "accepted"
        assert entry["accepted_at"] is not None

    def test_accept_nonexistent_returns_false(self):
        svc = AgentTaskDelegator()
        assert svc.accept_delegation("atdl-nope") is False

    def test_accept_already_accepted_returns_false(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        svc.accept_delegation(did)
        assert svc.accept_delegation(did) is False

    def test_accept_completed_returns_false(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        svc.complete_delegation(did)
        assert svc.accept_delegation(did) is False


class TestCompleteDelegation:
    """Completing delegations."""

    def test_complete_pending_delegation(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        assert svc.complete_delegation(did, result="done") is True
        entry = svc.get_delegation(did)
        assert entry["status"] == "completed"
        assert entry["result"] == "done"
        assert entry["completed_at"] is not None

    def test_complete_accepted_delegation(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        svc.accept_delegation(did)
        assert svc.complete_delegation(did, result="finished") is True
        entry = svc.get_delegation(did)
        assert entry["status"] == "completed"

    def test_complete_nonexistent_returns_false(self):
        svc = AgentTaskDelegator()
        assert svc.complete_delegation("atdl-nope") is False

    def test_complete_already_completed_returns_false(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        svc.complete_delegation(did)
        assert svc.complete_delegation(did) is False

    def test_complete_default_result_empty(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        svc.complete_delegation(did)
        entry = svc.get_delegation(did)
        assert entry["result"] == ""


class TestGetDelegations:
    """Querying multiple delegations."""

    def test_get_delegations_all(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        svc.delegate("t2", "c", "d")
        results = svc.get_delegations()
        assert len(results) == 2

    def test_get_delegations_filter_by_from_agent(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        svc.delegate("t2", "c", "d")
        svc.delegate("t3", "a", "d")
        results = svc.get_delegations(from_agent="a")
        assert len(results) == 2
        assert all(r["from_agent"] == "a" for r in results)

    def test_get_delegations_filter_by_to_agent(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        svc.delegate("t2", "c", "b")
        svc.delegate("t3", "a", "d")
        results = svc.get_delegations(to_agent="b")
        assert len(results) == 2
        assert all(r["to_agent"] == "b" for r in results)

    def test_get_delegations_newest_first(self):
        svc = AgentTaskDelegator()
        id1 = svc.delegate("t1", "a", "b")
        id2 = svc.delegate("t2", "a", "b")
        results = svc.get_delegations()
        assert results[0]["delegation_id"] == id2
        assert results[1]["delegation_id"] == id1

    def test_get_delegations_respects_limit(self):
        svc = AgentTaskDelegator()
        for i in range(10):
            svc.delegate(f"t{i}", "a", "b")
        results = svc.get_delegations(limit=3)
        assert len(results) == 3


class TestGetDelegationCount:
    """Counting delegations."""

    def test_count_all(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        svc.delegate("t2", "c", "d")
        assert svc.get_delegation_count() == 2

    def test_count_by_from_agent(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        svc.delegate("t2", "c", "d")
        svc.delegate("t3", "a", "d")
        assert svc.get_delegation_count(from_agent="a") == 2
        assert svc.get_delegation_count(from_agent="c") == 1

    def test_count_by_to_agent(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        svc.delegate("t2", "c", "b")
        assert svc.get_delegation_count(to_agent="b") == 2

    def test_count_empty(self):
        svc = AgentTaskDelegator()
        assert svc.get_delegation_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskDelegator()
        stats = svc.get_stats()
        assert stats["total_delegations"] == 0
        assert stats["accepted_count"] == 0
        assert stats["completed_count"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentTaskDelegator()
        d1 = svc.delegate("t1", "a", "b")
        d2 = svc.delegate("t2", "c", "d")
        d3 = svc.delegate("t3", "a", "d")
        svc.accept_delegation(d1)
        svc.complete_delegation(d2, result="ok")
        stats = svc.get_stats()
        assert stats["total_delegations"] == 3
        assert stats["accepted_count"] == 2  # d1 accepted, d2 completed (was pending->completed)
        assert stats["completed_count"] == 1
        assert stats["unique_agents"] == 4  # a, b, c, d


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        svc.reset()
        assert svc.get_delegation_count() == 0
        assert svc.get_stats()["total_delegations"] == 0

    def test_reset_clears_on_change(self):
        svc = AgentTaskDelegator()
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_delegate(self):
        events = []
        svc = AgentTaskDelegator()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.delegate("t1", "a", "b")
        assert len(events) == 1
        assert events[0][0] == "delegation_created"

    def test_on_change_fires_on_accept(self):
        events = []
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        svc.on_change = lambda action, data: events.append((action, data))
        svc.accept_delegation(did)
        assert len(events) == 1
        assert events[0][0] == "delegation_accepted"

    def test_on_change_fires_on_complete(self):
        events = []
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        svc.on_change = lambda action, data: events.append((action, data))
        svc.complete_delegation(did, result="done")
        assert len(events) == 1
        assert events[0][0] == "delegation_completed"

    def test_on_change_getter(self):
        svc = AgentTaskDelegator()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskDelegator()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskDelegator()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        did = svc.delegate("t1", "a", "b")
        assert did.startswith("atdl-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskDelegator()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.delegate("t1", "a", "b")
        assert "delegation_created" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskDelegator()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.delegate(f"t{i}", "a", "b"))
        assert svc.get_delegation(ids[0]) is None
        assert svc.get_delegation_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskDelegator()
        ids = set()
        for i in range(50):
            ids.add(svc.delegate(f"t{i}", "a", "b"))
        assert len(ids) == 50


class TestReturnTypes:
    """All public methods return expected types."""

    def test_delegate_returns_dict_via_get(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        assert isinstance(svc.get_delegation(did), dict)

    def test_get_delegations_returns_list_of_dicts(self):
        svc = AgentTaskDelegator()
        svc.delegate("t1", "a", "b")
        results = svc.get_delegations()
        assert isinstance(results, list)
        assert all(isinstance(r, dict) for r in results)

    def test_get_stats_returns_dict(self):
        svc = AgentTaskDelegator()
        assert isinstance(svc.get_stats(), dict)

    def test_accept_returns_bool(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        assert isinstance(svc.accept_delegation(did), bool)

    def test_complete_returns_bool(self):
        svc = AgentTaskDelegator()
        did = svc.delegate("t1", "a", "b")
        assert isinstance(svc.complete_delegation(did), bool)

    def test_get_delegation_count_returns_int(self):
        svc = AgentTaskDelegator()
        assert isinstance(svc.get_delegation_count(), int)
