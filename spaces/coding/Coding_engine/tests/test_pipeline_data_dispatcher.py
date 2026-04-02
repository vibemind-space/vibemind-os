"""Tests for PipelineDataDispatcher service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_dispatcher import PipelineDataDispatcher


class TestDispatchBasic:
    """Basic dispatch operations."""

    def test_dispatch_returns_string_id(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"key": "value"}, "target-a")
        assert isinstance(rid, str)
        assert rid.startswith("pddi-")

    def test_dispatch_ids_are_unique(self):
        d = PipelineDataDispatcher()
        ids = [d.dispatch("pipe-1", {"i": i}, "tgt") for i in range(10)]
        assert len(set(ids)) == 10

    def test_dispatch_deep_copies_data(self):
        d = PipelineDataDispatcher()
        original = {"nested": {"a": 1}}
        rid = d.dispatch("pipe-1", original, "tgt")
        original["nested"]["a"] = 999
        record = d.get_dispatch(rid)
        assert record["data"]["nested"]["a"] == 1

    def test_dispatch_deep_copies_metadata(self):
        d = PipelineDataDispatcher()
        meta = {"env": "prod", "extra": "yes"}
        rid = d.dispatch("pipe-1", {"x": 1}, "tgt", metadata=meta)
        meta["env"] = "modified"
        record = d.get_dispatch(rid)
        assert record["metadata"]["env"] == "prod"

    def test_dispatch_default_priority_zero(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"x": 1}, "tgt")
        record = d.get_dispatch(rid)
        assert record["priority"] == 0

    def test_dispatch_custom_priority(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"x": 1}, "tgt", priority=5)
        record = d.get_dispatch(rid)
        assert record["priority"] == 5

    def test_dispatch_default_metadata_empty_dict(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"x": 1}, "tgt")
        record = d.get_dispatch(rid)
        assert record["metadata"] == {}

    def test_dispatch_stores_pipeline_id(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("my-pipeline", {"x": 1}, "tgt")
        record = d.get_dispatch(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_dispatch_stores_target(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"x": 1}, "target-alpha")
        record = d.get_dispatch(rid)
        assert record["target"] == "target-alpha"


class TestGetDispatch:
    """get_dispatch method."""

    def test_get_dispatch_existing(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"a": 1}, "tgt")
        result = d.get_dispatch(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_dispatch_nonexistent(self):
        d = PipelineDataDispatcher()
        assert d.get_dispatch("pddi-nonexistent") is None

    def test_get_dispatch_returns_copy(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"a": 1}, "tgt")
        r1 = d.get_dispatch(rid)
        r2 = d.get_dispatch(rid)
        assert r1 is not r2
        assert r1 == r2

    def test_get_dispatch_contains_data(self):
        d = PipelineDataDispatcher()
        rid = d.dispatch("pipe-1", {"field": "value"}, "tgt")
        record = d.get_dispatch(rid)
        assert record["data"]["field"] == "value"


class TestGetDispatches:
    """get_dispatches listing."""

    def test_get_dispatches_returns_list(self):
        d = PipelineDataDispatcher()
        d.dispatch("pipe-1", {"a": 1}, "tgt")
        result = d.get_dispatches()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_dispatches_newest_first(self):
        d = PipelineDataDispatcher()
        id1 = d.dispatch("pipe-1", {"order": 1}, "tgt")
        id2 = d.dispatch("pipe-1", {"order": 2}, "tgt")
        results = d.get_dispatches()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_dispatches_filter_by_pipeline_id(self):
        d = PipelineDataDispatcher()
        d.dispatch("alpha", {"x": 1}, "tgt")
        d.dispatch("beta", {"x": 2}, "tgt")
        d.dispatch("alpha", {"x": 3}, "tgt")
        results = d.get_dispatches(pipeline_id="alpha")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "alpha" for r in results)

    def test_get_dispatches_filter_by_target(self):
        d = PipelineDataDispatcher()
        d.dispatch("pipe-1", {"x": 1}, "target-a")
        d.dispatch("pipe-1", {"x": 2}, "target-b")
        d.dispatch("pipe-1", {"x": 3}, "target-a")
        results = d.get_dispatches(target="target-a")
        assert len(results) == 2
        assert all(r["target"] == "target-a" for r in results)

    def test_get_dispatches_filter_by_both(self):
        d = PipelineDataDispatcher()
        d.dispatch("alpha", {"x": 1}, "target-a")
        d.dispatch("alpha", {"x": 2}, "target-b")
        d.dispatch("beta", {"x": 3}, "target-a")
        results = d.get_dispatches(pipeline_id="alpha", target="target-a")
        assert len(results) == 1
        assert results[0]["pipeline_id"] == "alpha"
        assert results[0]["target"] == "target-a"

    def test_get_dispatches_respects_limit(self):
        d = PipelineDataDispatcher()
        for i in range(10):
            d.dispatch("pipe-1", {"i": i}, "tgt")
        results = d.get_dispatches(limit=3)
        assert len(results) == 3

    def test_get_dispatches_empty(self):
        d = PipelineDataDispatcher()
        assert d.get_dispatches() == []

    def test_get_dispatches_returns_copies(self):
        d = PipelineDataDispatcher()
        d.dispatch("pipe-1", {"a": 1}, "tgt")
        r1 = d.get_dispatches()
        r2 = d.get_dispatches()
        assert r1[0] is not r2[0]


class TestGetDispatchCount:
    """get_dispatch_count method."""

    def test_count_all(self):
        d = PipelineDataDispatcher()
        for i in range(5):
            d.dispatch("pipe-1", {"i": i}, "tgt")
        assert d.get_dispatch_count() == 5

    def test_count_by_pipeline_id(self):
        d = PipelineDataDispatcher()
        d.dispatch("a", {"x": 1}, "tgt")
        d.dispatch("b", {"x": 2}, "tgt")
        d.dispatch("a", {"x": 3}, "tgt")
        assert d.get_dispatch_count(pipeline_id="a") == 2
        assert d.get_dispatch_count(pipeline_id="b") == 1
        assert d.get_dispatch_count(pipeline_id="c") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        d = PipelineDataDispatcher()
        stats = d.get_stats()
        assert stats["total_dispatches"] == 0
        assert stats["unique_targets"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        d = PipelineDataDispatcher()
        d.dispatch("pipe-a", {"a": 1}, "target-1")
        d.dispatch("pipe-b", {"b": 2}, "target-2")
        d.dispatch("pipe-a", {"c": 3}, "target-1")
        stats = d.get_stats()
        assert stats["total_dispatches"] == 3
        assert stats["unique_targets"] == 2
        assert stats["unique_pipelines"] == 2


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        d = PipelineDataDispatcher()
        d.dispatch("pipe-1", {"a": 1}, "tgt")
        d.dispatch("pipe-1", {"b": 2}, "tgt")
        assert d.get_dispatch_count() == 2
        d.reset()
        assert d.get_dispatch_count() == 0

    def test_reset_fires_event(self):
        d = PipelineDataDispatcher()
        events = []
        d.on_change = lambda action, data: events.append(action)
        d.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_dispatch(self):
        d = PipelineDataDispatcher()
        events = []
        d.on_change = lambda action, data: events.append((action, data))
        d.dispatch("pipe-1", {"x": 1}, "tgt")
        assert len(events) == 1
        assert events[0][0] == "dispatch"

    def test_on_change_property(self):
        d = PipelineDataDispatcher()
        assert d.on_change is None
        cb = lambda a, dt: None
        d.on_change = cb
        assert d.on_change is cb

    def test_callback_exception_is_silent(self):
        d = PipelineDataDispatcher()
        d.on_change = lambda a, dt: (_ for _ in ()).throw(ValueError("boom"))
        rid = d.dispatch("pipe-1", {"x": 1}, "tgt")
        assert rid.startswith("pddi-")

    def test_remove_callback(self):
        d = PipelineDataDispatcher()
        d._callbacks["mycb"] = lambda a, dt: None
        assert d.remove_callback("mycb") is True
        assert d.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        d = PipelineDataDispatcher()
        fired = []
        d._callbacks["tracker"] = lambda a, dt: fired.append(a)
        d.dispatch("pipe-1", {"v": 1}, "tgt")
        assert "dispatch" in fired

    def test_named_callback_exception_silent(self):
        d = PipelineDataDispatcher()
        d._callbacks["bad"] = lambda a, dt: 1 / 0
        rid = d.dispatch("pipe-1", {"v": 1}, "tgt")
        assert rid.startswith("pddi-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest_quarter(self):
        d = PipelineDataDispatcher()
        d.MAX_ENTRIES = 8
        ids = []
        for i in range(10):
            ids.append(d.dispatch("pipe-1", {"i": i}, "tgt"))
        # After 10 inserts with MAX_ENTRIES=8, pruning removes oldest quarter
        remaining = d.get_dispatch_count()
        assert remaining <= 10
        # The very first entries should have been pruned
        assert d.get_dispatch(ids[0]) is None
        # The last entries should still exist
        assert d.get_dispatch(ids[-1]) is not None

    def test_prune_keeps_newest(self):
        d = PipelineDataDispatcher()
        d.MAX_ENTRIES = 4
        ids = []
        for i in range(6):
            ids.append(d.dispatch("pipe-1", {"i": i}, "tgt"))
        assert d.get_dispatch(ids[-1]) is not None
        assert d.get_dispatch(ids[-2]) is not None
