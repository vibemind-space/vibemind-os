"""Tests for AgentWorkflowCacher."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_cacher import AgentWorkflowCacher


# ======================================================================
# Basic caching
# ======================================================================


class TestCacheBasics:
    def test_cache_returns_id(self):
        svc = AgentWorkflowCacher()
        cid = svc.cache("a1", "wf1", {"x": 1})
        assert cid.startswith("awca-")
        assert len(cid) > len("awca-")

    def test_get_cached(self):
        svc = AgentWorkflowCacher()
        cid = svc.cache("a1", "wf1", {"key": "val"})
        entry = svc.get_cached(cid)
        assert entry is not None
        assert entry["agent_id"] == "a1"
        assert entry["workflow_name"] == "wf1"
        assert entry["result"] == {"key": "val"}
        assert entry["created_at"] > 0

    def test_get_cached_not_found(self):
        svc = AgentWorkflowCacher()
        assert svc.get_cached("awca-nonexistent") is None

    def test_get_cached_returns_copy(self):
        svc = AgentWorkflowCacher()
        cid = svc.cache("a1", "wf1", {"v": 1})
        entry1 = svc.get_cached(cid)
        entry2 = svc.get_cached(cid)
        assert entry1 is not entry2
        assert entry1 == entry2

    def test_ttl_default_zero(self):
        svc = AgentWorkflowCacher()
        cid = svc.cache("a1", "wf1", "result")
        entry = svc.get_cached(cid)
        assert entry["ttl"] == 0


# ======================================================================
# TTL / expiration
# ======================================================================


class TestTTL:
    def test_expired_entry_returns_none(self):
        svc = AgentWorkflowCacher()
        cid = svc.cache("a1", "wf1", "res", ttl=1)
        # Manually backdate the entry to simulate expiry
        svc._state.entries[cid]["created_at"] = time.time() - 10
        assert svc.get_cached(cid) is None

    def test_non_expired_entry_returned(self):
        svc = AgentWorkflowCacher()
        cid = svc.cache("a1", "wf1", "res", ttl=3600)
        assert svc.get_cached(cid) is not None

    def test_expired_entries_excluded_from_query(self):
        svc = AgentWorkflowCacher()
        cid1 = svc.cache("a1", "wf1", "fresh", ttl=3600)
        cid2 = svc.cache("a1", "wf1", "stale", ttl=1)
        svc._state.entries[cid2]["created_at"] = time.time() - 10
        results = svc.get_cache_entries(agent_id="a1")
        assert len(results) == 1
        assert results[0]["cache_id"] == cid1

    def test_expired_entries_excluded_from_count(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "ok", ttl=3600)
        cid2 = svc.cache("a1", "wf1", "old", ttl=1)
        svc._state.entries[cid2]["created_at"] = time.time() - 10
        assert svc.get_cache_count("a1") == 1


# ======================================================================
# Querying
# ======================================================================


class TestQuerying:
    def test_get_cache_entries_newest_first(self):
        svc = AgentWorkflowCacher()
        cid1 = svc.cache("a1", "wf1", "r1")
        cid2 = svc.cache("a1", "wf1", "r2")
        cid3 = svc.cache("a1", "wf2", "r3")
        results = svc.get_cache_entries(agent_id="a1")
        assert len(results) == 3
        assert results[0]["cache_id"] == cid3
        assert results[1]["cache_id"] == cid2
        assert results[2]["cache_id"] == cid1

    def test_get_cache_entries_filter_by_workflow(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        svc.cache("a1", "wf2", "r2")
        results = svc.get_cache_entries(agent_id="a1", workflow_name="wf1")
        assert len(results) == 1
        assert results[0]["workflow_name"] == "wf1"

    def test_get_cache_entries_filter_by_agent(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        svc.cache("a2", "wf1", "r2")
        results = svc.get_cache_entries(agent_id="a1")
        assert len(results) == 1
        assert results[0]["agent_id"] == "a1"

    def test_get_cache_entries_no_filter(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        svc.cache("a2", "wf2", "r2")
        results = svc.get_cache_entries()
        assert len(results) == 2

    def test_get_cache_entries_limit(self):
        svc = AgentWorkflowCacher()
        for i in range(10):
            svc.cache("a1", "wf1", {"i": i})
        results = svc.get_cache_entries(agent_id="a1", limit=3)
        assert len(results) == 3

    def test_get_cache_entries_returns_copies(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        results = svc.get_cache_entries(agent_id="a1")
        assert len(results) == 1
        results[0]["agent_id"] = "tampered"
        fresh = svc.get_cache_entries(agent_id="a1")
        assert fresh[0]["agent_id"] == "a1"


# ======================================================================
# Counting
# ======================================================================


class TestCounting:
    def test_get_cache_count_all(self):
        svc = AgentWorkflowCacher()
        assert svc.get_cache_count() == 0
        svc.cache("a1", "wf1", "r1")
        svc.cache("a2", "wf2", "r2")
        assert svc.get_cache_count() == 2

    def test_get_cache_count_by_agent(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        svc.cache("a1", "wf2", "r2")
        svc.cache("a2", "wf1", "r3")
        assert svc.get_cache_count("a1") == 2
        assert svc.get_cache_count("a2") == 1
        assert svc.get_cache_count("a3") == 0


# ======================================================================
# Callbacks
# ======================================================================


class TestCallbacks:
    def test_on_change_fires_on_cache(self):
        svc = AgentWorkflowCacher()
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.cache("a1", "wf1", "r1")
        assert len(events) == 1
        assert events[0][0] == "cached"

    def test_on_change_property_getter_setter(self):
        svc = AgentWorkflowCacher()
        assert svc.on_change is None
        handler = lambda a, d: None
        svc.on_change = handler
        assert svc.on_change is handler
        svc.on_change = None
        assert svc.on_change is None

    def test_on_change_cleared_stops_firing(self):
        svc = AgentWorkflowCacher()
        events = []
        svc.on_change = lambda a, d: events.append(1)
        svc.cache("a1", "wf1", "r1")
        svc.on_change = None
        svc.cache("a1", "wf1", "r2")
        assert len(events) == 1

    def test_register_callback(self):
        svc = AgentWorkflowCacher()
        events = []
        svc.register_callback("cb1", lambda a, d: events.append(a))
        svc.cache("a1", "wf1", "r1")
        assert events == ["cached"]

    def test_remove_callback_found(self):
        svc = AgentWorkflowCacher()
        svc.register_callback("cb1", lambda a, d: None)
        assert svc.remove_callback("cb1") is True
        assert "cb1" not in svc._callbacks

    def test_remove_callback_not_found(self):
        svc = AgentWorkflowCacher()
        assert svc.remove_callback("nonexistent") is False

    def test_on_change_called_before_callbacks(self):
        svc = AgentWorkflowCacher()
        order = []
        svc.on_change = lambda a, d: order.append("on_change")
        svc.register_callback("cb1", lambda a, d: order.append("cb1"))
        svc.cache("a1", "wf1", "r1")
        assert order == ["on_change", "cb1"]

    def test_callback_exception_silenced(self):
        svc = AgentWorkflowCacher()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        svc.register_callback("bad", lambda a, d: 1 / 0)
        # Should not raise
        cid = svc.cache("a1", "wf1", "r1")
        assert svc.get_cached(cid) is not None


# ======================================================================
# Pruning
# ======================================================================


class TestPruning:
    def test_prune_removes_oldest_quarter(self):
        svc = AgentWorkflowCacher()
        svc.MAX_ENTRIES = 4
        # Insert 5 entries; prune runs at start of cache() so after 5th
        # insert we have 5 entries. The 6th insert triggers prune of 5
        # entries: removes oldest quarter (5//4 = 1), leaving 4, then adds
        # the 6th for a total of 5.
        ids = []
        for i in range(6):
            ids.append(svc.cache("a1", "wf1", {"i": i}))
        # The oldest entry should have been removed
        assert svc.get_cached(ids[0]) is None
        # Remaining should be 5 (pruned 1, added 1)
        assert svc.get_cache_count() == 5

    def test_prune_large_batch(self):
        svc = AgentWorkflowCacher()
        svc.MAX_ENTRIES = 8
        for i in range(12):
            svc.cache("a1", "wf1", {"i": i})
        # Should have pruned; count should be <= MAX_ENTRIES + 1
        # (prune happens at start of cache, so after the 9th insert prunes,
        #  then entries 10-12 add more, triggering more prunes)
        assert svc.get_cache_count() <= 10


# ======================================================================
# Unique IDs
# ======================================================================


class TestUniqueIDs:
    def test_ids_are_unique(self):
        svc = AgentWorkflowCacher()
        ids = set()
        for i in range(100):
            cid = svc.cache("a1", "wf1", {"i": i})
            ids.add(cid)
        assert len(ids) == 100

    def test_ids_have_prefix(self):
        svc = AgentWorkflowCacher()
        cid = svc.cache("a1", "wf1", "res")
        assert cid.startswith("awca-")


# ======================================================================
# Stats
# ======================================================================


class TestStats:
    def test_get_stats(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        svc.cache("a1", "wf2", "r2")
        svc.cache("a2", "wf1", "r3")
        stats = svc.get_stats()
        assert stats["total_entries"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_workflows"] == 2
        assert stats["callbacks_registered"] == 0

    def test_get_stats_with_callbacks(self):
        svc = AgentWorkflowCacher()
        svc.register_callback("cb1", lambda a, d: None)
        stats = svc.get_stats()
        assert stats["callbacks_registered"] == 1


# ======================================================================
# Reset
# ======================================================================


class TestReset:
    def test_reset_clears_entries(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        svc.cache("a2", "wf2", "r2")
        svc.reset()
        assert svc.get_cache_count() == 0

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowCacher()
        svc.register_callback("cb1", lambda a, d: None)
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None

    def test_reset_resets_seq(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        assert svc._state._seq > 0
        svc.reset()
        assert svc._state._seq == 0

    def test_reset_clears_stats(self):
        svc = AgentWorkflowCacher()
        svc.cache("a1", "wf1", "r1")
        svc.reset()
        stats = svc.get_stats()
        assert stats["total_entries"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_workflows"] == 0


if __name__ == "__main__":
    import traceback

    test_classes = [
        TestCacheBasics,
        TestTTL,
        TestQuerying,
        TestCounting,
        TestCallbacks,
        TestPruning,
        TestUniqueIDs,
        TestStats,
        TestReset,
    ]
    passed = 0
    failed = 0
    for cls in test_classes:
        instance = cls()
        for name in sorted(dir(instance)):
            if not name.startswith("test_"):
                continue
            try:
                getattr(instance, name)()
                passed += 1
            except Exception as e:
                failed += 1
                print(f"FAIL {cls.__name__}.{name}: {e}")
                traceback.print_exc()
    print(f"{passed}/{passed + failed} tests passed")
