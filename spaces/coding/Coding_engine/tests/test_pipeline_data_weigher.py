"""Tests for PipelineDataWeigher service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_weigher import PipelineDataWeigher


class TestWeighBasic:
    """Basic weigh operations."""

    def test_weigh_returns_id_with_prefix(self):
        s = PipelineDataWeigher()
        rid = s.weigh("pipe-1", "key-a")
        assert isinstance(rid, str)
        assert rid.startswith("pdwg-")

    def test_weigh_fields_correct(self):
        s = PipelineDataWeigher()
        rid = s.weigh("pipe-1", "key-a", weight=2.5, metadata={"x": 1})
        rec = s.get_weight(rid)
        assert rec["record_id"] == rid
        assert rec["pipeline_id"] == "pipe-1"
        assert rec["data_key"] == "key-a"
        assert rec["weight"] == 2.5
        assert rec["metadata"] == {"x": 1}
        assert "created_at" in rec

    def test_weigh_default_weight_is_one(self):
        s = PipelineDataWeigher()
        rid = s.weigh("pipe-1", "key-a")
        rec = s.get_weight(rid)
        assert rec["weight"] == 1.0

    def test_weigh_metadata_deepcopy(self):
        s = PipelineDataWeigher()
        meta = {"nested": [1, 2, 3]}
        rid = s.weigh("pipe-1", "key-a", metadata=meta)
        meta["nested"].append(99)
        rec = s.get_weight(rid)
        assert 99 not in rec["metadata"]["nested"]

    def test_weigh_empty_pipeline_id_returns_empty(self):
        s = PipelineDataWeigher()
        assert s.weigh("", "key-a") == ""

    def test_weigh_empty_data_key_returns_empty(self):
        s = PipelineDataWeigher()
        assert s.weigh("pipe-1", "") == ""


class TestGetWeight:
    """get_weight lookups."""

    def test_get_weight_found(self):
        s = PipelineDataWeigher()
        rid = s.weigh("pipe-1", "key-a")
        rec = s.get_weight(rid)
        assert rec is not None
        assert rec["record_id"] == rid

    def test_get_weight_not_found(self):
        s = PipelineDataWeigher()
        assert s.get_weight("pdwg-nonexistent") is None

    def test_get_weight_returns_copy(self):
        s = PipelineDataWeigher()
        rid = s.weigh("pipe-1", "key-a")
        rec1 = s.get_weight(rid)
        rec2 = s.get_weight(rid)
        assert rec1 is not rec2


class TestGetWeights:
    """get_weights listing."""

    def test_get_weights_all(self):
        s = PipelineDataWeigher()
        s.weigh("pipe-1", "k1")
        s.weigh("pipe-2", "k2")
        s.weigh("pipe-1", "k3")
        result = s.get_weights()
        assert len(result) == 3

    def test_get_weights_filter_by_pipeline(self):
        s = PipelineDataWeigher()
        s.weigh("pipe-1", "k1")
        s.weigh("pipe-2", "k2")
        s.weigh("pipe-1", "k3")
        result = s.get_weights(pipeline_id="pipe-1")
        assert len(result) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in result)

    def test_get_weights_newest_first(self):
        s = PipelineDataWeigher()
        r1 = s.weigh("pipe-1", "k1")
        r2 = s.weigh("pipe-1", "k2")
        r3 = s.weigh("pipe-1", "k3")
        result = s.get_weights()
        assert result[0]["record_id"] == r3
        assert result[-1]["record_id"] == r1


class TestGetWeightCount:
    """get_weight_count operations."""

    def test_get_weight_count_total(self):
        s = PipelineDataWeigher()
        s.weigh("pipe-1", "k1")
        s.weigh("pipe-2", "k2")
        assert s.get_weight_count() == 2

    def test_get_weight_count_filtered(self):
        s = PipelineDataWeigher()
        s.weigh("pipe-1", "k1")
        s.weigh("pipe-2", "k2")
        s.weigh("pipe-1", "k3")
        assert s.get_weight_count("pipe-1") == 2
        assert s.get_weight_count("pipe-2") == 1


class TestGetStats:
    """get_stats operations."""

    def test_get_stats(self):
        s = PipelineDataWeigher()
        s.weigh("pipe-1", "k1")
        s.weigh("pipe-2", "k2")
        s.weigh("pipe-1", "k3")
        stats = s.get_stats()
        assert stats["total_weights"] == 3
        assert stats["unique_pipelines"] == 2


class TestOnChangeCallback:
    """on_change callback behavior."""

    def test_on_change_called_on_weigh(self):
        s = PipelineDataWeigher()
        calls = []
        s.on_change = lambda action, **kw: calls.append(action)
        s.weigh("pipe-1", "k1")
        assert "weigh" in calls


class TestRemoveCallback:
    """remove_callback behavior."""

    def test_remove_callback_true(self):
        s = PipelineDataWeigher()
        s._state.callbacks["cb1"] = lambda action, **kw: None
        assert s.remove_callback("cb1") is True
        assert "cb1" not in s._state.callbacks

    def test_remove_callback_false(self):
        s = PipelineDataWeigher()
        assert s.remove_callback("nonexistent") is False


class TestPrune:
    """Pruning when exceeding MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        s = PipelineDataWeigher()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.weigh("pipe-1", f"key-{i}")
        assert len(s._state.entries) <= 6  # 8 - 8//4 = 6


class TestReset:
    """reset clears state and on_change."""

    def test_reset_clears_state(self):
        s = PipelineDataWeigher()
        s.weigh("pipe-1", "k1")
        s.on_change = lambda a, **kw: None
        s.reset()
        assert len(s._state.entries) == 0
        assert s._state._seq == 0
        assert s._on_change is None
