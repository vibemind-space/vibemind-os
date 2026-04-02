"""Tests for PipelineStepWeigher service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_weigher import PipelineStepWeigher


class TestWeigh:
    """weigh operations."""

    def test_weigh_returns_string_id(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a")
        assert isinstance(rid, str)
        assert rid.startswith("pswg-")

    def test_weigh_ids_are_unique(self):
        w = PipelineStepWeigher()
        ids = [w.weigh("pipe-1", f"step-{i}") for i in range(20)]
        assert len(set(ids)) == 20

    def test_weigh_default_weight_one(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a")
        record = w.get_weight(rid)
        assert record["weight"] == 1.0

    def test_weigh_custom_weight(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a", weight=5.5)
        record = w.get_weight(rid)
        assert record["weight"] == 5.5

    def test_weigh_with_metadata(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a", metadata={"key": "val"})
        record = w.get_weight(rid)
        assert record["metadata"]["key"] == "val"

    def test_weigh_metadata_default_empty_dict(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a")
        record = w.get_weight(rid)
        assert record["metadata"] == {}

    def test_weigh_metadata_is_copied(self):
        w = PipelineStepWeigher()
        meta = {"nested": {"x": 1}}
        rid = w.weigh("pipe-1", "step-a", metadata=meta)
        meta["nested"]["x"] = 999
        record = w.get_weight(rid)
        assert record["metadata"]["nested"]["x"] == 1

    def test_weigh_stores_pipeline_id(self):
        w = PipelineStepWeigher()
        rid = w.weigh("my-pipeline", "step-a")
        record = w.get_weight(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_weigh_stores_step_name(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "my-step")
        record = w.get_weight(rid)
        assert record["step_name"] == "my-step"

    def test_weigh_zero_weight(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a", weight=0.0)
        record = w.get_weight(rid)
        assert record["weight"] == 0.0

    def test_weigh_negative_weight(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a", weight=-3.2)
        record = w.get_weight(rid)
        assert record["weight"] == -3.2


class TestGetWeight:
    """get_weight method."""

    def test_get_weight_existing(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a", weight=5.0)
        result = w.get_weight(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_weight_nonexistent(self):
        w = PipelineStepWeigher()
        assert w.get_weight("pswg-nonexistent") is None

    def test_get_weight_returns_dict_copy(self):
        w = PipelineStepWeigher()
        rid = w.weigh("pipe-1", "step-a")
        r1 = w.get_weight(rid)
        r2 = w.get_weight(rid)
        assert r1 is not r2
        assert r1 == r2


class TestGetWeights:
    """get_weights listing."""

    def test_get_weights_returns_list(self):
        w = PipelineStepWeigher()
        w.weigh("pipe-1", "step-a")
        result = w.get_weights()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_weights_newest_first(self):
        w = PipelineStepWeigher()
        id1 = w.weigh("pipe-1", "step-a")
        id2 = w.weigh("pipe-1", "step-b")
        results = w.get_weights()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_weights_filter_by_pipeline_id(self):
        w = PipelineStepWeigher()
        w.weigh("pipe-a", "step-1")
        w.weigh("pipe-b", "step-2")
        w.weigh("pipe-a", "step-3")
        results = w.get_weights(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_weights_respects_limit(self):
        w = PipelineStepWeigher()
        for i in range(10):
            w.weigh("pipe-1", f"step-{i}")
        results = w.get_weights(limit=3)
        assert len(results) == 3

    def test_get_weights_empty(self):
        w = PipelineStepWeigher()
        assert w.get_weights() == []

    def test_get_weights_filter_returns_empty_for_unknown_pipeline(self):
        w = PipelineStepWeigher()
        w.weigh("pipe-a", "step-1")
        results = w.get_weights(pipeline_id="pipe-unknown")
        assert results == []

    def test_get_weights_returns_dicts(self):
        w = PipelineStepWeigher()
        w.weigh("pipe-1", "step-a")
        w.weigh("pipe-1", "step-b")
        results = w.get_weights()
        assert all(isinstance(r, dict) for r in results)


class TestGetWeightCount:
    """get_weight_count method."""

    def test_count_all(self):
        w = PipelineStepWeigher()
        for i in range(5):
            w.weigh("pipe-1", f"step-{i}")
        assert w.get_weight_count() == 5

    def test_count_by_pipeline_id(self):
        w = PipelineStepWeigher()
        w.weigh("pipe-a", "step-1")
        w.weigh("pipe-b", "step-2")
        w.weigh("pipe-a", "step-3")
        assert w.get_weight_count(pipeline_id="pipe-a") == 2
        assert w.get_weight_count(pipeline_id="pipe-b") == 1
        assert w.get_weight_count(pipeline_id="pipe-c") == 0

    def test_count_empty(self):
        w = PipelineStepWeigher()
        assert w.get_weight_count() == 0


class TestGetStats:
    """get_stats method."""

    def test_stats_empty(self):
        w = PipelineStepWeigher()
        stats = w.get_stats()
        assert stats["total_weights"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        w = PipelineStepWeigher()
        w.weigh("pipe-a", "step-1")
        w.weigh("pipe-b", "step-2")
        w.weigh("pipe-a", "step-3")
        stats = w.get_stats()
        assert stats["total_weights"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_returns_dict(self):
        w = PipelineStepWeigher()
        assert isinstance(w.get_stats(), dict)


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        w = PipelineStepWeigher()
        w.weigh("pipe-1", "step-a")
        w.weigh("pipe-1", "step-b")
        assert w.get_weight_count() == 2
        w.reset()
        assert w.get_weight_count() == 0

    def test_reset_clears_callbacks(self):
        w = PipelineStepWeigher()
        w._state.callbacks["mycb"] = lambda a, d: None
        w.reset()
        assert len(w._state.callbacks) == 0

    def test_reset_clears_on_change(self):
        w = PipelineStepWeigher()
        w.on_change = lambda a, d: None
        w.reset()
        assert w.on_change is None


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_weigh(self):
        w = PipelineStepWeigher()
        events = []
        w.on_change = lambda action, data: events.append((action, data))
        w.weigh("pipe-1", "step-a")
        assert len(events) == 1
        assert events[0][0] == "weigh"

    def test_on_change_property_getter(self):
        w = PipelineStepWeigher()
        assert w.on_change is None
        cb = lambda a, d: None
        w.on_change = cb
        assert w.on_change is cb

    def test_on_change_exception_is_silent(self):
        w = PipelineStepWeigher()
        w.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = w.weigh("pipe-1", "step-a")
        assert rid.startswith("pswg-")

    def test_remove_callback_returns_true_if_found(self):
        w = PipelineStepWeigher()
        w._state.callbacks["mycb"] = lambda a, d: None
        assert w.remove_callback("mycb") is True

    def test_remove_callback_returns_false_if_not_found(self):
        w = PipelineStepWeigher()
        assert w.remove_callback("nonexistent") is False

    def test_named_callback_fires(self):
        w = PipelineStepWeigher()
        fired = []
        w._state.callbacks["tracker"] = lambda a, d: fired.append(a)
        w.weigh("pipe-1", "step-a")
        assert "weigh" in fired

    def test_named_callback_exception_silent(self):
        w = PipelineStepWeigher()
        w._state.callbacks["bad"] = lambda a, d: 1 / 0
        rid = w.weigh("pipe-1", "step-a")
        assert rid.startswith("pswg-")

    def test_on_change_fires_before_named_callbacks(self):
        w = PipelineStepWeigher()
        order = []
        w.on_change = lambda a, d: order.append("on_change")
        w._state.callbacks["named"] = lambda a, d: order.append("named")
        w.weigh("pipe-1", "step-a")
        assert order == ["on_change", "named"]


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        w = PipelineStepWeigher()
        w.MAX_ENTRIES = 8
        ids = []
        for i in range(10):
            ids.append(w.weigh("pipe-1", f"step-{i}"))
        remaining = w.get_weight_count()
        assert remaining == 8
        assert w.get_weight(ids[0]) is None
        assert w.get_weight(ids[1]) is None
        assert w.get_weight(ids[9]) is not None

    def test_prune_preserves_newest(self):
        w = PipelineStepWeigher()
        w.MAX_ENTRIES = 4
        ids = []
        for i in range(6):
            ids.append(w.weigh("pipe-1", f"step-{i}"))
        assert w.get_weight(ids[-1]) is not None


class TestUniqueIds:
    """ID uniqueness guarantees."""

    def test_ids_unique_across_many(self):
        w = PipelineStepWeigher()
        ids = set()
        for i in range(100):
            rid = w.weigh("pipe-1", f"step-{i}")
            ids.add(rid)
        assert len(ids) == 100

    def test_ids_have_correct_prefix(self):
        w = PipelineStepWeigher()
        for i in range(5):
            rid = w.weigh("pipe-1", f"step-{i}")
            assert rid.startswith("pswg-")
