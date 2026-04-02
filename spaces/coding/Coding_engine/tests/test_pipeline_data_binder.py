"""Tests for PipelineDataBinder service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_binder import PipelineDataBinder


class TestBindBasic:
    """Basic bind operations."""

    def test_bind_returns_string_id(self):
        binder = PipelineDataBinder()
        bid = binder.bind("pipe-1", "field_a", 42)
        assert isinstance(bid, str)
        assert bid.startswith("pdbi-")

    def test_bind_ids_are_unique(self):
        binder = PipelineDataBinder()
        ids = [binder.bind("pipe-1", f"f{i}", i) for i in range(10)]
        assert len(set(ids)) == 10

    def test_bind_stores_pipeline_id(self):
        binder = PipelineDataBinder()
        bid = binder.bind("pipe-x", "field", "val")
        rec = binder.get_binding(bid)
        assert rec["pipeline_id"] == "pipe-x"

    def test_bind_stores_field_name(self):
        binder = PipelineDataBinder()
        bid = binder.bind("pipe-1", "temperature", 98.6)
        rec = binder.get_binding(bid)
        assert rec["field_name"] == "temperature"

    def test_bind_stores_value(self):
        binder = PipelineDataBinder()
        bid = binder.bind("pipe-1", "data", {"nested": [1, 2, 3]})
        rec = binder.get_binding(bid)
        assert rec["value"] == {"nested": [1, 2, 3]}

    def test_bind_default_metadata_empty_dict(self):
        binder = PipelineDataBinder()
        bid = binder.bind("pipe-1", "f", "v")
        rec = binder.get_binding(bid)
        assert rec["metadata"] == {}

    def test_bind_with_metadata(self):
        binder = PipelineDataBinder()
        bid = binder.bind("pipe-1", "f", "v", metadata={"source": "sensor"})
        rec = binder.get_binding(bid)
        assert rec["metadata"]["source"] == "sensor"


class TestGetBinding:
    """get_binding method."""

    def test_get_binding_existing(self):
        binder = PipelineDataBinder()
        bid = binder.bind("p1", "f1", 100)
        result = binder.get_binding(bid)
        assert result is not None
        assert result["binding_id"] == bid

    def test_get_binding_missing_returns_none(self):
        binder = PipelineDataBinder()
        assert binder.get_binding("pdbi-nonexistent") is None

    def test_get_binding_returns_copy(self):
        binder = PipelineDataBinder()
        bid = binder.bind("p1", "f1", "val")
        r1 = binder.get_binding(bid)
        r2 = binder.get_binding(bid)
        assert r1 is not r2
        assert r1 == r2


class TestGetBindings:
    """get_bindings method."""

    def test_get_bindings_all(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.bind("p2", "f2", 2)
        results = binder.get_bindings()
        assert len(results) == 2

    def test_get_bindings_filtered_by_pipeline_id(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.bind("p2", "f2", 2)
        binder.bind("p1", "f3", 3)
        results = binder.get_bindings(pipeline_id="p1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "p1" for r in results)

    def test_get_bindings_newest_first(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "first", 1)
        binder.bind("p1", "second", 2)
        binder.bind("p1", "third", 3)
        results = binder.get_bindings(pipeline_id="p1")
        assert results[0]["field_name"] == "third"
        assert results[-1]["field_name"] == "first"

    def test_get_bindings_respects_limit(self):
        binder = PipelineDataBinder()
        for i in range(10):
            binder.bind("p1", f"f{i}", i)
        results = binder.get_bindings(limit=3)
        assert len(results) == 3

    def test_get_bindings_returns_copies(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        r1 = binder.get_bindings()
        r2 = binder.get_bindings()
        assert r1[0] is not r2[0]

    def test_get_bindings_empty_pipeline_returns_all(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.bind("p2", "f2", 2)
        results = binder.get_bindings(pipeline_id="")
        assert len(results) == 2


class TestGetBindingCount:
    """get_binding_count method."""

    def test_count_all(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.bind("p2", "f2", 2)
        assert binder.get_binding_count() == 2

    def test_count_filtered(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.bind("p2", "f2", 2)
        binder.bind("p1", "f3", 3)
        assert binder.get_binding_count(pipeline_id="p1") == 2

    def test_count_empty(self):
        binder = PipelineDataBinder()
        assert binder.get_binding_count() == 0


class TestCallbacks:
    """Callback and on_change functionality."""

    def test_on_change_property_default_none(self):
        binder = PipelineDataBinder()
        assert binder.on_change is None

    def test_on_change_setter(self):
        binder = PipelineDataBinder()
        fn = lambda action, data: None
        binder.on_change = fn
        assert binder.on_change is fn

    def test_on_change_fires_on_bind(self):
        binder = PipelineDataBinder()
        events = []
        binder.on_change = lambda action, data: events.append(action)
        binder.bind("p1", "f1", 1)
        assert "bind" in events

    def test_callback_fires_on_bind(self):
        binder = PipelineDataBinder()
        events = []
        binder.register_callback("my_cb", lambda action, data: events.append(action))
        binder.bind("p1", "f1", 1)
        assert "bind" in events

    def test_on_change_fires_before_callbacks(self):
        binder = PipelineDataBinder()
        order = []
        binder.on_change = lambda a, d: order.append("on_change")
        binder.register_callback("cb", lambda a, d: order.append("cb"))
        binder.bind("p1", "f1", 1)
        assert order == ["on_change", "cb"]

    def test_callback_exception_silenced(self):
        binder = PipelineDataBinder()
        binder.register_callback("bad", lambda a, d: 1 / 0)
        binder.bind("p1", "f1", 1)  # should not raise

    def test_on_change_exception_silenced(self):
        binder = PipelineDataBinder()
        binder.on_change = lambda a, d: 1 / 0
        binder.bind("p1", "f1", 1)  # should not raise

    def test_remove_callback_existing(self):
        binder = PipelineDataBinder()
        binder.register_callback("cb1", lambda a, d: None)
        assert binder.remove_callback("cb1") is True

    def test_remove_callback_missing(self):
        binder = PipelineDataBinder()
        assert binder.remove_callback("nope") is False

    def test_removed_callback_not_called(self):
        binder = PipelineDataBinder()
        events = []
        binder.register_callback("cb1", lambda a, d: events.append("cb1"))
        binder.remove_callback("cb1")
        binder.bind("p1", "f1", 1)
        assert events == []


class TestPruning:
    """Pruning when entries exceed MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        binder = PipelineDataBinder()
        binder.MAX_ENTRIES = 20
        for i in range(25):
            binder.bind("p1", f"f{i}", i)
        # After inserting 25 with MAX_ENTRIES=20, pruning removes oldest quarter
        assert len(binder._state.entries) <= 20


class TestGetStats:
    """get_stats method."""

    def test_stats_empty(self):
        binder = PipelineDataBinder()
        stats = binder.get_stats()
        assert stats["total_bindings"] == 0

    def test_stats_with_data(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.bind("p2", "f2", 2)
        binder.bind("p1", "f1", 3)
        stats = binder.get_stats()
        assert stats["total_bindings"] == 3
        assert stats["unique_pipelines"] == 2
        assert stats["unique_fields"] == 2


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.reset()
        assert binder.get_binding_count() == 0

    def test_reset_clears_seq(self):
        binder = PipelineDataBinder()
        binder.bind("p1", "f1", 1)
        binder.reset()
        assert binder._state._seq == 0

    def test_reset_clears_callbacks(self):
        binder = PipelineDataBinder()
        binder.register_callback("cb1", lambda a, d: None)
        binder.reset()
        assert len(binder._callbacks) == 0

    def test_reset_clears_on_change(self):
        binder = PipelineDataBinder()
        binder.on_change = lambda a, d: None
        binder.reset()
        assert binder.on_change is None
