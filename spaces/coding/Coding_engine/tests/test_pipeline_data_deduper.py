"""Tests for PipelineDataDeduper service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_deduper import PipelineDataDeduper


class TestDedupeBasic:
    """Basic dedupe operations."""

    def test_dedupe_returns_id_with_prefix(self):
        d = PipelineDataDeduper()
        rid = d.dedupe("pipe-1", "key-a")
        assert isinstance(rid, str)
        assert rid.startswith("pddd-")

    def test_dedupe_ids_are_unique(self):
        d = PipelineDataDeduper()
        ids = [d.dedupe("pipe-1", f"key-{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_dedupe_stores_fields(self):
        d = PipelineDataDeduper()
        rid = d.dedupe("pipe-1", "key-a", strategy="fuzzy", metadata={"x": 1})
        rec = d.get_dedupe(rid)
        assert rec["record_id"] == rid
        assert rec["pipeline_id"] == "pipe-1"
        assert rec["data_key"] == "key-a"
        assert rec["strategy"] == "fuzzy"
        assert rec["metadata"] == {"x": 1}
        assert "created_at" in rec

    def test_dedupe_default_strategy_is_exact(self):
        d = PipelineDataDeduper()
        rid = d.dedupe("pipe-1", "key-a")
        rec = d.get_dedupe(rid)
        assert rec["strategy"] == "exact"

    def test_dedupe_metadata_deepcopy(self):
        d = PipelineDataDeduper()
        meta = {"nested": {"val": 1}}
        rid = d.dedupe("pipe-1", "key-a", metadata=meta)
        meta["nested"]["val"] = 999
        rec = d.get_dedupe(rid)
        assert rec["metadata"]["nested"]["val"] == 1

    def test_dedupe_default_metadata_empty_dict(self):
        d = PipelineDataDeduper()
        rid = d.dedupe("pipe-1", "key-a")
        rec = d.get_dedupe(rid)
        assert rec["metadata"] == {}


class TestDedupeEmptyInput:
    """Empty input handling."""

    def test_empty_pipeline_id_returns_empty(self):
        d = PipelineDataDeduper()
        assert d.dedupe("", "key-a") == ""

    def test_empty_data_key_returns_empty(self):
        d = PipelineDataDeduper()
        assert d.dedupe("pipe-1", "") == ""


class TestGetDedupe:
    """get_dedupe tests."""

    def test_get_found(self):
        d = PipelineDataDeduper()
        rid = d.dedupe("pipe-1", "key-a")
        rec = d.get_dedupe(rid)
        assert rec is not None
        assert rec["record_id"] == rid

    def test_get_not_found(self):
        d = PipelineDataDeduper()
        assert d.get_dedupe("pddd-nonexistent") is None

    def test_get_returns_copy(self):
        d = PipelineDataDeduper()
        rid = d.dedupe("pipe-1", "key-a")
        rec1 = d.get_dedupe(rid)
        rec2 = d.get_dedupe(rid)
        assert rec1 is not rec2
        assert rec1 == rec2


class TestGetDedupes:
    """get_dedupes list tests."""

    def test_list_all(self):
        d = PipelineDataDeduper()
        d.dedupe("pipe-1", "key-a")
        d.dedupe("pipe-2", "key-b")
        results = d.get_dedupes()
        assert len(results) == 2

    def test_list_filter_by_pipeline(self):
        d = PipelineDataDeduper()
        d.dedupe("pipe-1", "key-a")
        d.dedupe("pipe-2", "key-b")
        d.dedupe("pipe-1", "key-c")
        results = d.get_dedupes(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_list_newest_first(self):
        d = PipelineDataDeduper()
        r1 = d.dedupe("pipe-1", "key-a")
        r2 = d.dedupe("pipe-1", "key-b")
        results = d.get_dedupes()
        assert results[0]["record_id"] == r2
        assert results[1]["record_id"] == r1


class TestGetDedupeCount:
    """get_dedupe_count tests."""

    def test_total_count(self):
        d = PipelineDataDeduper()
        d.dedupe("pipe-1", "key-a")
        d.dedupe("pipe-2", "key-b")
        assert d.get_dedupe_count() == 2

    def test_filtered_count(self):
        d = PipelineDataDeduper()
        d.dedupe("pipe-1", "key-a")
        d.dedupe("pipe-2", "key-b")
        d.dedupe("pipe-1", "key-c")
        assert d.get_dedupe_count("pipe-1") == 2
        assert d.get_dedupe_count("pipe-2") == 1


class TestStats:
    """get_stats tests."""

    def test_stats(self):
        d = PipelineDataDeduper()
        d.dedupe("pipe-1", "key-a")
        d.dedupe("pipe-2", "key-b")
        d.dedupe("pipe-1", "key-c")
        stats = d.get_stats()
        assert stats["total_dedupes"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_empty(self):
        d = PipelineDataDeduper()
        stats = d.get_stats()
        assert stats["total_dedupes"] == 0
        assert stats["unique_pipelines"] == 0


class TestOnChange:
    """on_change callback tests."""

    def test_on_change_called(self):
        d = PipelineDataDeduper()
        calls = []
        d.on_change = lambda action, detail: calls.append((action, detail))
        d.dedupe("pipe-1", "key-a")
        assert len(calls) == 1
        assert calls[0][0] == "dedupe"

    def test_named_callback_called(self):
        d = PipelineDataDeduper()
        calls = []
        d._state.callbacks["my_cb"] = lambda action, detail: calls.append(action)
        d.dedupe("pipe-1", "key-a")
        assert "dedupe" in calls


class TestRemoveCallback:
    """remove_callback tests."""

    def test_remove_existing_returns_true(self):
        d = PipelineDataDeduper()
        d._state.callbacks["cb1"] = lambda a, d: None
        assert d.remove_callback("cb1") is True
        assert "cb1" not in d._state.callbacks

    def test_remove_missing_returns_false(self):
        d = PipelineDataDeduper()
        assert d.remove_callback("nope") is False


class TestPrune:
    """Pruning tests with reduced MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        d = PipelineDataDeduper()
        d.MAX_ENTRIES = 5
        for i in range(6):
            d.dedupe("pipe-1", f"key-{i}")
        # 6 added, exceeds 5 -> prune removes 6//4 = 1 oldest
        assert d.get_dedupe_count() == 5


class TestReset:
    """reset tests."""

    def test_reset_clears_state(self):
        d = PipelineDataDeduper()
        d.on_change = lambda a, dt: None
        d.dedupe("pipe-1", "key-a")
        d.reset()
        assert d.get_dedupe_count() == 0
        assert d.on_change is None
        assert d.get_stats()["total_dedupes"] == 0
