"""Tests for PipelineDataThrottler service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_throttler import PipelineDataThrottler


class TestThrottleBasic:
    """Basic throttle operations."""

    def test_throttle_returns_string_id(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a")
        assert isinstance(rid, str)
        assert rid.startswith("pdth-")

    def test_throttle_ids_are_unique(self):
        s = PipelineDataThrottler()
        ids = [s.throttle("pipe-1", f"key-{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_throttle_stores_pipeline_id(self):
        s = PipelineDataThrottler()
        rid = s.throttle("my-pipeline", "key-a")
        record = s.get_throttle(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_throttle_stores_data_key(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "data-key-x")
        record = s.get_throttle(rid)
        assert record["data_key"] == "data-key-x"

    def test_throttle_default_rate_limit(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a")
        record = s.get_throttle(rid)
        assert record["rate_limit"] == 100

    def test_throttle_custom_rate_limit(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a", rate_limit=500)
        record = s.get_throttle(rid)
        assert record["rate_limit"] == 500

    def test_throttle_with_metadata(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a", metadata={"source": "test"})
        record = s.get_throttle(rid)
        assert record["metadata"]["source"] == "test"

    def test_throttle_default_metadata_empty_dict(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a")
        record = s.get_throttle(rid)
        assert record["metadata"] == {}

    def test_throttle_metadata_is_deep_copied(self):
        s = PipelineDataThrottler()
        meta = {"nested": {"key": "value"}}
        rid = s.throttle("pipe-1", "key-a", metadata=meta)
        meta["nested"]["key"] = "changed"
        record = s.get_throttle(rid)
        assert record["metadata"]["nested"]["key"] == "value"

    def test_throttle_has_created_at(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a")
        record = s.get_throttle(rid)
        assert "created_at" in record
        assert isinstance(record["created_at"], float)


class TestThrottleValidation:
    """Validation of throttle inputs."""

    def test_empty_pipeline_id_returns_empty_string(self):
        s = PipelineDataThrottler()
        assert s.throttle("", "key-a") == ""

    def test_empty_data_key_returns_empty_string(self):
        s = PipelineDataThrottler()
        assert s.throttle("pipe-1", "") == ""

    def test_both_empty_returns_empty_string(self):
        s = PipelineDataThrottler()
        assert s.throttle("", "") == ""

    def test_empty_pipeline_id_does_not_store(self):
        s = PipelineDataThrottler()
        s.throttle("", "key-a")
        assert s.get_throttle_count() == 0

    def test_empty_data_key_does_not_store(self):
        s = PipelineDataThrottler()
        s.throttle("pipe-1", "")
        assert s.get_throttle_count() == 0


class TestGetThrottle:
    """get_throttle method."""

    def test_get_throttle_existing(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a")
        result = s.get_throttle(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_throttle_nonexistent(self):
        s = PipelineDataThrottler()
        assert s.get_throttle("pdth-nonexistent") is None

    def test_get_throttle_returns_dict(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a")
        result = s.get_throttle(rid)
        assert isinstance(result, dict)

    def test_get_throttle_returns_copy(self):
        s = PipelineDataThrottler()
        rid = s.throttle("pipe-1", "key-a")
        r1 = s.get_throttle(rid)
        r2 = s.get_throttle(rid)
        assert r1 is not r2


class TestGetThrottles:
    """get_throttles listing."""

    def test_get_throttles_returns_list(self):
        s = PipelineDataThrottler()
        s.throttle("pipe-1", "key-a")
        result = s.get_throttles()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_throttles_newest_first(self):
        s = PipelineDataThrottler()
        id1 = s.throttle("pipe-1", "key-1")
        id2 = s.throttle("pipe-1", "key-2")
        results = s.get_throttles()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_throttles_filter_by_pipeline_id(self):
        s = PipelineDataThrottler()
        s.throttle("pipe-a", "key-1")
        s.throttle("pipe-b", "key-2")
        s.throttle("pipe-a", "key-3")
        results = s.get_throttles(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_throttles_respects_limit(self):
        s = PipelineDataThrottler()
        for i in range(10):
            s.throttle("pipe-1", f"key-{i}")
        results = s.get_throttles(limit=3)
        assert len(results) == 3

    def test_get_throttles_empty(self):
        s = PipelineDataThrottler()
        assert s.get_throttles() == []

    def test_get_throttles_returns_list_of_dicts(self):
        s = PipelineDataThrottler()
        s.throttle("pipe-1", "key-1")
        s.throttle("pipe-1", "key-2")
        results = s.get_throttles()
        assert all(isinstance(r, dict) for r in results)


class TestGetThrottleCount:
    """get_throttle_count method."""

    def test_count_all(self):
        s = PipelineDataThrottler()
        for i in range(5):
            s.throttle("pipe-1", f"key-{i}")
        assert s.get_throttle_count() == 5

    def test_count_by_pipeline_id(self):
        s = PipelineDataThrottler()
        s.throttle("pipe-a", "key-1")
        s.throttle("pipe-b", "key-2")
        s.throttle("pipe-a", "key-3")
        assert s.get_throttle_count(pipeline_id="pipe-a") == 2
        assert s.get_throttle_count(pipeline_id="pipe-b") == 1
        assert s.get_throttle_count(pipeline_id="pipe-c") == 0

    def test_count_empty(self):
        s = PipelineDataThrottler()
        assert s.get_throttle_count() == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        s = PipelineDataThrottler()
        stats = s.get_stats()
        assert stats["total_throttles"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        s = PipelineDataThrottler()
        s.throttle("pipe-a", "key-1")
        s.throttle("pipe-b", "key-2")
        s.throttle("pipe-a", "key-3")
        stats = s.get_stats()
        assert stats["total_throttles"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_returns_dict(self):
        s = PipelineDataThrottler()
        stats = s.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        s = PipelineDataThrottler()
        s.throttle("pipe-1", "key-a")
        s.throttle("pipe-1", "key-b")
        assert s.get_throttle_count() == 2
        s.reset()
        assert s.get_throttle_count() == 0

    def test_reset_clears_on_change(self):
        s = PipelineDataThrottler()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_reset_creates_new_state(self):
        s = PipelineDataThrottler()
        old_state = s._state
        s.reset()
        assert s._state is not old_state


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_throttle(self):
        s = PipelineDataThrottler()
        events = []
        s.on_change = lambda action, data: events.append((action, data))
        s.throttle("pipe-1", "key-a")
        assert len(events) == 1
        assert events[0][0] == "throttled"

    def test_on_change_property(self):
        s = PipelineDataThrottler()
        assert s.on_change is None
        cb = lambda a, d: None
        s.on_change = cb
        assert s.on_change is cb

    def test_on_change_exception_is_silent(self):
        s = PipelineDataThrottler()
        s.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = s.throttle("pipe-1", "key-a")
        assert rid.startswith("pdth-")

    def test_remove_callback(self):
        s = PipelineDataThrottler()
        s._state.callbacks["mycb"] = lambda a, d: None
        assert s.remove_callback("mycb") is True
        assert s.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        s = PipelineDataThrottler()
        fired = []
        s._state.callbacks["tracker"] = lambda a, d: fired.append(a)
        s.throttle("pipe-1", "key-a")
        assert "throttled" in fired

    def test_named_callback_exception_silent(self):
        s = PipelineDataThrottler()
        s._state.callbacks["bad"] = lambda a, d: 1 / 0
        rid = s.throttle("pipe-1", "key-a")
        assert rid.startswith("pdth-")

    def test_remove_callback_nonexistent_returns_false(self):
        s = PipelineDataThrottler()
        assert s.remove_callback("nope") is False


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        s = PipelineDataThrottler()
        s.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(s.throttle("pipe-1", f"key-{i}"))
        assert s.get_throttle_count() == 5
        assert s.get_throttle(ids[0]) is None
        assert s.get_throttle(ids[1]) is None
        assert s.get_throttle(ids[6]) is not None

    def test_prune_keeps_newest(self):
        s = PipelineDataThrottler()
        s.MAX_ENTRIES = 3
        ids = []
        for i in range(6):
            ids.append(s.throttle("pipe-1", f"key-{i}"))
        for rid in ids[-3:]:
            assert s.get_throttle(rid) is not None
