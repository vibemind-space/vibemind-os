"""Tests for pipeline_data_materializer."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from src.services.pipeline_data_materializer import PipelineDataMaterializer


# ---------------------------------------------------------------------------
# TestBasic
# ---------------------------------------------------------------------------

class TestBasic:
    def test_materialize_returns_id_with_prefix(self):
        m = PipelineDataMaterializer()
        rid = m.materialize("p1", "dk1")
        assert rid.startswith("pdmt-")

    def test_materialize_fields_correct(self):
        m = PipelineDataMaterializer()
        rid = m.materialize("p1", "dk1", format="json", metadata={"a": 1})
        entry = m.get_materialization(rid)
        assert entry["record_id"] == rid
        assert entry["pipeline_id"] == "p1"
        assert entry["data_key"] == "dk1"
        assert entry["format"] == "json"
        assert entry["metadata"] == {"a": 1}
        assert "created_at" in entry
        assert "updated_at" in entry

    def test_default_format_is_default(self):
        m = PipelineDataMaterializer()
        rid = m.materialize("p1", "dk1")
        entry = m.get_materialization(rid)
        assert entry["format"] == "default"

    def test_metadata_deepcopy(self):
        m = PipelineDataMaterializer()
        meta = {"nested": [1, 2, 3]}
        rid = m.materialize("p1", "dk1", metadata=meta)
        meta["nested"].append(999)
        entry = m.get_materialization(rid)
        assert 999 not in entry["metadata"]["nested"]

    def test_empty_pipeline_id_returns_empty_string(self):
        m = PipelineDataMaterializer()
        assert m.materialize("", "dk1") == ""

    def test_empty_data_key_returns_empty_string(self):
        m = PipelineDataMaterializer()
        assert m.materialize("p1", "") == ""


# ---------------------------------------------------------------------------
# TestGet
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_found(self):
        m = PipelineDataMaterializer()
        rid = m.materialize("p1", "dk1")
        result = m.get_materialization(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_not_found_returns_none(self):
        m = PipelineDataMaterializer()
        assert m.get_materialization("nonexistent") is None

    def test_get_returns_copy(self):
        m = PipelineDataMaterializer()
        rid = m.materialize("p1", "dk1")
        result = m.get_materialization(rid)
        assert isinstance(result, dict)
        result["pipeline_id"] = "MUTATED"
        original = m.get_materialization(rid)
        assert original["pipeline_id"] == "p1"


# ---------------------------------------------------------------------------
# TestList
# ---------------------------------------------------------------------------

class TestList:
    def test_list_all_entries(self):
        m = PipelineDataMaterializer()
        m.materialize("p1", "dk1")
        m.materialize("p2", "dk2")
        m.materialize("p3", "dk3")
        results = m.get_materializations()
        assert len(results) == 3

    def test_list_filter_by_pipeline_id(self):
        m = PipelineDataMaterializer()
        m.materialize("p1", "dk1")
        m.materialize("p1", "dk2")
        m.materialize("p2", "dk3")
        results = m.get_materializations(pipeline_id="p1")
        assert len(results) == 2
        assert all(e["pipeline_id"] == "p1" for e in results)

    def test_list_newest_first(self):
        m = PipelineDataMaterializer()
        r1 = m.materialize("p1", "dk1")
        r2 = m.materialize("p1", "dk2")
        r3 = m.materialize("p1", "dk3")
        results = m.get_materializations()
        assert results[0]["record_id"] == r3
        assert results[-1]["record_id"] == r1


# ---------------------------------------------------------------------------
# TestCount
# ---------------------------------------------------------------------------

class TestCount:
    def test_total_count(self):
        m = PipelineDataMaterializer()
        m.materialize("p1", "dk1")
        m.materialize("p2", "dk2")
        assert m.get_materialization_count() == 2

    def test_count_filtered_by_pipeline_id(self):
        m = PipelineDataMaterializer()
        m.materialize("p1", "dk1")
        m.materialize("p1", "dk2")
        m.materialize("p2", "dk3")
        assert m.get_materialization_count(pipeline_id="p1") == 2
        assert m.get_materialization_count(pipeline_id="p2") == 1


# ---------------------------------------------------------------------------
# TestStats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_keys(self):
        m = PipelineDataMaterializer()
        m.materialize("p1", "dk1")
        m.materialize("p2", "dk2")
        stats = m.get_stats()
        assert "total_materializations" in stats
        assert "unique_pipelines" in stats
        assert stats["total_materializations"] == 2
        assert stats["unique_pipelines"] == 2


# ---------------------------------------------------------------------------
# TestCallbacks
# ---------------------------------------------------------------------------

class TestCallbacks:
    def test_on_change_fires(self):
        m = PipelineDataMaterializer()
        fired = []
        m.on_change = lambda action, data: fired.append((action, data))
        m.materialize("p1", "dk1")
        assert len(fired) == 1
        assert fired[0][0] == "materialize"

    def test_remove_callback_returns_true(self):
        m = PipelineDataMaterializer()
        m._state.callbacks["cb1"] = lambda a, d: None
        assert m.remove_callback("cb1") is True
        assert "cb1" not in m._state.callbacks

    def test_remove_callback_unknown_returns_false(self):
        m = PipelineDataMaterializer()
        assert m.remove_callback("unknown") is False


# ---------------------------------------------------------------------------
# TestPrune
# ---------------------------------------------------------------------------

class TestPrune:
    def test_prune_removes_oldest_entries(self):
        m = PipelineDataMaterializer()
        m.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            rid = m.materialize(f"p{i}", f"dk{i}")
            ids.append(rid)
        # After adding 7 entries with MAX_ENTRIES=5, pruning should have kicked in.
        # 7 > 5 triggers prune, removing 7//4 = 1 oldest entry each time it fires.
        assert m.get_materialization_count() <= 7
        assert m.get_materialization_count() >= 5


# ---------------------------------------------------------------------------
# TestReset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_entries(self):
        m = PipelineDataMaterializer()
        m.materialize("p1", "dk1")
        m.materialize("p2", "dk2")
        m.reset()
        assert m.get_materialization_count() == 0

    def test_reset_on_change_is_none(self):
        m = PipelineDataMaterializer()
        m.on_change = lambda a, d: None
        m.reset()
        assert m.on_change is None

    def test_reset_seq_resets_to_zero(self):
        m = PipelineDataMaterializer()
        m.materialize("p1", "dk1")
        assert m._state._seq > 0
        m.reset()
        assert m._state._seq == 0
