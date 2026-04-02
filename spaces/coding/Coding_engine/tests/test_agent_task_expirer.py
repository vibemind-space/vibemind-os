"""Tests for AgentTaskExpirer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_expirer import AgentTaskExpirer


class TestExpireBasic:
    """Basic expire and retrieval."""

    def test_expire_returns_id(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1")
        assert rid.startswith("atex-")
        assert len(rid) > 5

    def test_expire_empty_task_id_returns_empty(self):
        svc = AgentTaskExpirer()
        assert svc.expire("", "a1") == ""

    def test_expire_empty_agent_id_returns_empty(self):
        svc = AgentTaskExpirer()
        assert svc.expire("t1", "") == ""

    def test_expire_both_empty_returns_empty(self):
        svc = AgentTaskExpirer()
        assert svc.expire("", "") == ""

    def test_get_expiration_existing(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1", reason="timeout")
        entry = svc.get_expiration(rid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["reason"] == "timeout"

    def test_get_expiration_nonexistent(self):
        svc = AgentTaskExpirer()
        assert svc.get_expiration("atex-nonexistent") is None

    def test_default_reason_is_empty(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1")
        entry = svc.get_expiration(rid)
        assert entry["reason"] == ""

    def test_entry_has_created_at(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1")
        entry = svc.get_expiration(rid)
        assert "created_at" in entry
        assert isinstance(entry["created_at"], float)

    def test_entry_has_record_id(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1")
        entry = svc.get_expiration(rid)
        assert entry["record_id"] == rid


class TestMetadata:
    """Metadata behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1", metadata={"key": "val"})
        entry = svc.get_expiration(rid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_default_empty(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1")
        entry = svc.get_expiration(rid)
        assert entry["metadata"] == {}

    def test_metadata_not_shared(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_expiration(rid)
        assert entry["metadata"]["nested"]["x"] == 1


class TestGetExpirations:
    """Querying multiple expirations."""

    def test_get_expirations_all(self):
        svc = AgentTaskExpirer()
        svc.expire("t1", "a1")
        svc.expire("t2", "a2")
        results = svc.get_expirations()
        assert len(results) == 2

    def test_get_expirations_filter_by_agent(self):
        svc = AgentTaskExpirer()
        svc.expire("t1", "a1")
        svc.expire("t2", "a2")
        svc.expire("t3", "a1")
        results = svc.get_expirations(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_expirations_newest_first(self):
        svc = AgentTaskExpirer()
        id1 = svc.expire("t1", "a1")
        id2 = svc.expire("t2", "a1")
        results = svc.get_expirations()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_expirations_respects_limit(self):
        svc = AgentTaskExpirer()
        for i in range(10):
            svc.expire(f"t{i}", "a1")
        results = svc.get_expirations(limit=3)
        assert len(results) == 3

    def test_get_expirations_empty(self):
        svc = AgentTaskExpirer()
        results = svc.get_expirations()
        assert results == []

    def test_get_expirations_returns_copies(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1")
        results = svc.get_expirations()
        results[0]["task_id"] = "mutated"
        entry = svc.get_expiration(rid)
        assert entry["task_id"] == "t1"


class TestGetExpirationCount:
    """Counting expirations."""

    def test_count_all(self):
        svc = AgentTaskExpirer()
        svc.expire("t1", "a1")
        svc.expire("t2", "a2")
        assert svc.get_expiration_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskExpirer()
        svc.expire("t1", "a1")
        svc.expire("t2", "a2")
        svc.expire("t3", "a1")
        assert svc.get_expiration_count(agent_id="a1") == 2
        assert svc.get_expiration_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskExpirer()
        assert svc.get_expiration_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskExpirer()
        stats = svc.get_stats()
        assert stats["total_expirations"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentTaskExpirer()
        svc.expire("t1", "a1")
        svc.expire("t2", "a2")
        svc.expire("t3", "a1")
        stats = svc.get_stats()
        assert stats["total_expirations"] == 3
        assert stats["unique_agents"] == 2

    def test_stats_returns_dict(self):
        svc = AgentTaskExpirer()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskExpirer()
        svc.expire("t1", "a1")
        svc.reset()
        assert svc.get_expiration_count() == 0
        assert svc.get_stats()["total_expirations"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskExpirer()
        svc._state.callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None
        assert len(svc._state.callbacks) == 0

    def test_reset_allows_new_expirations(self):
        svc = AgentTaskExpirer()
        svc.expire("t1", "a1")
        svc.reset()
        rid = svc.expire("t2", "a2")
        assert rid.startswith("atex-")
        assert svc.get_expiration_count() == 1


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_expire(self):
        events = []
        svc = AgentTaskExpirer()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.expire("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "expired"

    def test_on_change_getter(self):
        svc = AgentTaskExpirer()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_on_change_setter_none_removes(self):
        svc = AgentTaskExpirer()
        svc.on_change = lambda a, d: None
        assert svc.on_change is not None
        svc.on_change = None
        assert svc.on_change is None

    def test_remove_callback(self):
        svc = AgentTaskExpirer()
        svc._state.callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskExpirer()
        assert svc.remove_callback("nope") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskExpirer()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = svc.expire("t1", "a1")
        assert rid.startswith("atex-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskExpirer()
        svc._state.callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.expire("t1", "a1")
        assert "expired" in events

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskExpirer()
        svc._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("x"))
        rid = svc.expire("t1", "a1")
        assert rid.startswith("atex-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentTaskExpirer()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.expire(f"t{i}", "a1"))
        assert svc.get_expiration(ids[0]) is None
        assert svc.get_expiration(ids[1]) is None
        assert svc.get_expiration_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskExpirer()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.expire(f"t{i}", "a1"))
        assert svc.get_expiration(ids[-1]) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskExpirer()
        ids = set()
        for i in range(50):
            ids.add(svc.expire(f"t{i}", "a1"))
        assert len(ids) == 50

    def test_id_prefix(self):
        svc = AgentTaskExpirer()
        rid = svc.expire("t1", "a1")
        assert rid.startswith("atex-")
