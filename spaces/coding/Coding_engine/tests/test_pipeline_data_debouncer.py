"""Tests for PipelineDataDebouncer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_debouncer import PipelineDataDebouncer


class TestDebounceBasic:
    """Basic debounce operations."""

    def test_debounce_returns_string_id(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a")
        assert isinstance(rid, str)
        assert rid.startswith("pddb-")

    def test_debounce_ids_are_unique(self):
        s = PipelineDataDebouncer()
        ids = [s.debounce("pipe-1", f"key-{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_debounce_stores_pipeline_id(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("my-pipeline", "key-a")
        record = s.get_debounce(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_debounce_stores_data_key(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "data-key-x")
        record = s.get_debounce(rid)
        assert record["data_key"] == "data-key-x"

    def test_debounce_default_interval(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a")
        record = s.get_debounce(rid)
        assert record["interval"] == 1.0

    def test_debounce_custom_interval(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a", interval=5.0)
        record = s.get_debounce(rid)
        assert record["interval"] == 5.0

    def test_debounce_with_metadata(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a", metadata={"source": "test"})
        record = s.get_debounce(rid)
        assert record["metadata"]["source"] == "test"

    def test_debounce_default_metadata_empty_dict(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a")
        record = s.get_debounce(rid)
        assert record["metadata"] == {}

    def test_debounce_metadata_is_deep_copied(self):
        s = PipelineDataDebouncer()
        meta = {"nested": {"key": "value"}}
        rid = s.debounce("pipe-1", "key-a", metadata=meta)
        meta["nested"]["key"] = "changed"
        record = s.get_debounce(rid)
        assert record["metadata"]["nested"]["key"] == "value"

    def test_debounce_has_created_at(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a")
        record = s.get_debounce(rid)
        assert "created_at" in record
        assert isinstance(record["created_at"], float)


class TestDebounceValidation:
    """Validation of debounce inputs."""

    def test_empty_pipeline_id_returns_empty_string(self):
        s = PipelineDataDebouncer()
        assert s.debounce("", "key-a") == ""

    def test_empty_data_key_returns_empty_string(self):
        s = PipelineDataDebouncer()
        assert s.debounce("pipe-1", "") == ""

    def test_both_empty_returns_empty_string(self):
        s = PipelineDataDebouncer()
        assert s.debounce("", "") == ""

    def test_empty_pipeline_id_does_not_store(self):
        s = PipelineDataDebouncer()
        s.debounce("", "key-a")
        assert s.get_debounce_count() == 0

    def test_empty_data_key_does_not_store(self):
        s = PipelineDataDebouncer()
        s.debounce("pipe-1", "")
        assert s.get_debounce_count() == 0


class TestGetDebounce:
    """get_debounce method."""

    def test_get_debounce_existing(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a")
        result = s.get_debounce(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_debounce_nonexistent(self):
        s = PipelineDataDebouncer()
        assert s.get_debounce("pddb-nonexistent") is None

    def test_get_debounce_returns_dict(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a")
        result = s.get_debounce(rid)
        assert isinstance(result, dict)

    def test_get_debounce_returns_copy(self):
        s = PipelineDataDebouncer()
        rid = s.debounce("pipe-1", "key-a")
        r1 = s.get_debounce(rid)
        r2 = s.get_debounce(rid)
        assert r1 is not r2


class TestGetDebounces:
    """get_debounces listing."""

    def test_get_debounces_returns_list(self):
        s = PipelineDataDebouncer()
        s.debounce("pipe-1", "key-a")
        result = s.get_debounces()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_debounces_newest_first(self):
        s = PipelineDataDebouncer()
        id1 = s.debounce("pipe-1", "key-1")
        id2 = s.debounce("pipe-1", "key-2")
        results = s.get_debounces()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_debounces_filter_by_pipeline_id(self):
        s = PipelineDataDebouncer()
        s.debounce("pipe-a", "key-1")
        s.debounce("pipe-b", "key-2")
        s.debounce("pipe-a", "key-3")
        results = s.get_debounces(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_debounces_respects_limit(self):
        s = PipelineDataDebouncer()
        for i in range(10):
            s.debounce("pipe-1", f"key-{i}")
        results = s.get_debounces(limit=3)
        assert len(results) == 3

    def test_get_debounces_empty(self):
        s = PipelineDataDebouncer()
        assert s.get_debounces() == []

    def test_get_debounces_returns_list_of_dicts(self):
        s = PipelineDataDebouncer()
        s.debounce("pipe-1", "key-1")
        s.debounce("pipe-1", "key-2")
        results = s.get_debounces()
        assert all(isinstance(r, dict) for r in results)


class TestGetDebounceCount:
    """get_debounce_count method."""

    def test_count_all(self):
        s = PipelineDataDebouncer()
        for i in range(5):
            s.debounce("pipe-1", f"key-{i}")
        assert s.get_debounce_count() == 5

    def test_count_by_pipeline_id(self):
        s = PipelineDataDebouncer()
        s.debounce("pipe-a", "key-1")
        s.debounce("pipe-b", "key-2")
        s.debounce("pipe-a", "key-3")
        assert s.get_debounce_count(pipeline_id="pipe-a") == 2
        assert s.get_debounce_count(pipeline_id="pipe-b") == 1
        assert s.get_debounce_count(pipeline_id="pipe-c") == 0

    def test_count_empty(self):
        s = PipelineDataDebouncer()
        assert s.get_debounce_count() == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        s = PipelineDataDebouncer()
        stats = s.get_stats()
        assert stats["total_debounces"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        s = PipelineDataDebouncer()
        s.debounce("pipe-a", "key-1")
        s.debounce("pipe-b", "key-2")
        s.debounce("pipe-a", "key-3")
        stats = s.get_stats()
        assert stats["total_debounces"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_returns_dict(self):
        s = PipelineDataDebouncer()
        stats = s.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        s = PipelineDataDebouncer()
        s.debounce("pipe-1", "key-a")
        s.debounce("pipe-1", "key-b")
        assert s.get_debounce_count() == 2
        s.reset()
        assert s.get_debounce_count() == 0

    def test_reset_clears_on_change(self):
        s = PipelineDataDebouncer()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_reset_creates_new_state(self):
        s = PipelineDataDebouncer()
        old_state = s._state
        s.reset()
        assert s._state is not old_state


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_debounce(self):
        s = PipelineDataDebouncer()
        events = []
        s.on_change = lambda action, data: events.append((action, data))
        s.debounce("pipe-1", "key-a")
        assert len(events) == 1
        assert events[0][0] == "debounced"

    def test_on_change_property(self):
        s = PipelineDataDebouncer()
        assert s.on_change is None
        cb = lambda a, d: None
        s.on_change = cb
        assert s.on_change is cb

    def test_on_change_exception_is_silent(self):
        s = PipelineDataDebouncer()
        s.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = s.debounce("pipe-1", "key-a")
        assert rid.startswith("pddb-")

    def test_remove_callback(self):
        s = PipelineDataDebouncer()
        s._state.callbacks["mycb"] = lambda a, d: None
        assert s.remove_callback("mycb") is True
        assert s.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        s = PipelineDataDebouncer()
        fired = []
        s._state.callbacks["tracker"] = lambda a, d: fired.append(a)
        s.debounce("pipe-1", "key-a")
        assert "debounced" in fired

    def test_named_callback_exception_silent(self):
        s = PipelineDataDebouncer()
        s._state.callbacks["bad"] = lambda a, d: 1 / 0
        rid = s.debounce("pipe-1", "key-a")
        assert rid.startswith("pddb-")

    def test_remove_callback_nonexistent_returns_false(self):
        s = PipelineDataDebouncer()
        assert s.remove_callback("nope") is False


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        s = PipelineDataDebouncer()
        s.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(s.debounce("pipe-1", f"key-{i}"))
        assert s.get_debounce_count() == 5
        assert s.get_debounce(ids[0]) is None
        assert s.get_debounce(ids[1]) is None
        assert s.get_debounce(ids[6]) is not None

    def test_prune_keeps_newest(self):
        s = PipelineDataDebouncer()
        s.MAX_ENTRIES = 3
        ids = []
        for i in range(6):
            ids.append(s.debounce("pipe-1", f"key-{i}"))
        for rid in ids[-3:]:
            assert s.get_debounce(rid) is not None
