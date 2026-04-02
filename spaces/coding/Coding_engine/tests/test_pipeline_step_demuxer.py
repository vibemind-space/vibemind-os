"""Tests for pipeline_step_demuxer module."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from src.services.pipeline_step_demuxer import PipelineStepDemuxer


# ---------------------------------------------------------------------------
# TestBasic
# ---------------------------------------------------------------------------

class TestBasic:
    def test_demux_returns_id_with_prefix(self):
        dm = PipelineStepDemuxer()
        rid = dm.demux("pipe-1", "step-a")
        assert rid.startswith("psdm-")

    def test_demux_fields_correct(self):
        dm = PipelineStepDemuxer()
        rid = dm.demux("pipe-1", "step-a", channels=3, metadata={"k": "v"})
        entry = dm.get_demux(rid)
        assert entry["record_id"] == rid
        assert entry["pipeline_id"] == "pipe-1"
        assert entry["step_name"] == "step-a"
        assert entry["channels"] == 3
        assert entry["metadata"] == {"k": "v"}
        assert "created_at" in entry
        assert "updated_at" in entry

    def test_default_channels_is_one(self):
        dm = PipelineStepDemuxer()
        rid = dm.demux("pipe-1", "step-a")
        entry = dm.get_demux(rid)
        assert entry["channels"] == 1

    def test_metadata_deepcopy(self):
        dm = PipelineStepDemuxer()
        meta = {"nested": [1, 2, 3]}
        rid = dm.demux("pipe-1", "step-a", metadata=meta)
        meta["nested"].append(999)
        entry = dm.get_demux(rid)
        assert 999 not in entry["metadata"]["nested"]

    def test_empty_pipeline_id_returns_empty_string(self):
        dm = PipelineStepDemuxer()
        assert dm.demux("", "step-a") == ""

    def test_empty_step_name_returns_empty_string(self):
        dm = PipelineStepDemuxer()
        assert dm.demux("pipe-1", "") == ""

    def test_unique_ids(self):
        dm = PipelineStepDemuxer()
        ids = {dm.demux("pipe-1", f"step-{i}") for i in range(20)}
        assert len(ids) == 20


# ---------------------------------------------------------------------------
# TestGet
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_demux_found(self):
        dm = PipelineStepDemuxer()
        rid = dm.demux("pipe-1", "step-a")
        result = dm.get_demux(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_demux_not_found_returns_none(self):
        dm = PipelineStepDemuxer()
        assert dm.get_demux("nonexistent") is None

    def test_get_demux_returns_copy(self):
        dm = PipelineStepDemuxer()
        rid = dm.demux("pipe-1", "step-a")
        result = dm.get_demux(rid)
        result["pipeline_id"] = "MODIFIED"
        original = dm.get_demux(rid)
        assert original["pipeline_id"] == "pipe-1"


# ---------------------------------------------------------------------------
# TestList
# ---------------------------------------------------------------------------

class TestList:
    def test_get_demuxes_all_entries(self):
        dm = PipelineStepDemuxer()
        dm.demux("pipe-1", "step-a")
        dm.demux("pipe-2", "step-b")
        dm.demux("pipe-1", "step-c")
        results = dm.get_demuxes()
        assert len(results) == 3

    def test_get_demuxes_filter_by_pipeline_id(self):
        dm = PipelineStepDemuxer()
        dm.demux("pipe-1", "step-a")
        dm.demux("pipe-2", "step-b")
        dm.demux("pipe-1", "step-c")
        results = dm.get_demuxes(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_get_demuxes_newest_first(self):
        dm = PipelineStepDemuxer()
        r1 = dm.demux("pipe-1", "step-a")
        r2 = dm.demux("pipe-1", "step-b")
        r3 = dm.demux("pipe-1", "step-c")
        results = dm.get_demuxes()
        assert results[0]["record_id"] == r3
        assert results[1]["record_id"] == r2
        assert results[2]["record_id"] == r1


# ---------------------------------------------------------------------------
# TestCount
# ---------------------------------------------------------------------------

class TestCount:
    def test_total_count(self):
        dm = PipelineStepDemuxer()
        dm.demux("pipe-1", "step-a")
        dm.demux("pipe-2", "step-b")
        assert dm.get_demux_count() == 2

    def test_filtered_count(self):
        dm = PipelineStepDemuxer()
        dm.demux("pipe-1", "step-a")
        dm.demux("pipe-2", "step-b")
        dm.demux("pipe-1", "step-c")
        assert dm.get_demux_count(pipeline_id="pipe-1") == 2
        assert dm.get_demux_count(pipeline_id="pipe-2") == 1
        assert dm.get_demux_count(pipeline_id="pipe-999") == 0


# ---------------------------------------------------------------------------
# TestStats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_keys(self):
        dm = PipelineStepDemuxer()
        stats = dm.get_stats()
        assert "total_demuxes" in stats
        assert "unique_pipelines" in stats

    def test_stats_values(self):
        dm = PipelineStepDemuxer()
        dm.demux("pipe-1", "step-a")
        dm.demux("pipe-2", "step-b")
        dm.demux("pipe-1", "step-c")
        stats = dm.get_stats()
        assert stats["total_demuxes"] == 3
        assert stats["unique_pipelines"] == 2


# ---------------------------------------------------------------------------
# TestCallbacks
# ---------------------------------------------------------------------------

class TestCallbacks:
    def test_on_change_fires(self):
        dm = PipelineStepDemuxer()
        fired = []
        dm.on_change = lambda action, data: fired.append((action, data))
        dm.demux("pipe-1", "step-a")
        assert len(fired) == 1
        assert fired[0][0] == "demux"
        assert "record_id" in fired[0][1]

    def test_remove_callback_returns_true(self):
        dm = PipelineStepDemuxer()
        dm._state.callbacks["my_cb"] = lambda a, d: None
        assert dm.remove_callback("my_cb") is True
        assert "my_cb" not in dm._state.callbacks

    def test_remove_callback_unknown_returns_false(self):
        dm = PipelineStepDemuxer()
        assert dm.remove_callback("nonexistent") is False


# ---------------------------------------------------------------------------
# TestPrune
# ---------------------------------------------------------------------------

class TestPrune:
    def test_prune_removes_oldest(self):
        dm = PipelineStepDemuxer()
        dm.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(dm.demux("pipe-1", f"step-{i}"))
        # After adding 7 entries with MAX_ENTRIES=5, pruning should have kicked in.
        # 7 // 4 = 1 entry removed per prune cycle that triggers.
        # Prune triggers at entry 6 (len > 5), removes 1, leaving 5.
        # Prune triggers at entry 7 (len > 5 again), removes 1, leaving 5.
        assert dm.get_demux_count() <= 6
        # The oldest entries should be gone
        assert dm.get_demux(ids[0]) is None


# ---------------------------------------------------------------------------
# TestReset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_entries(self):
        dm = PipelineStepDemuxer()
        dm.demux("pipe-1", "step-a")
        dm.demux("pipe-2", "step-b")
        dm.reset()
        assert dm.get_demux_count() == 0

    def test_reset_on_change_is_none(self):
        dm = PipelineStepDemuxer()
        dm.on_change = lambda a, d: None
        dm.reset()
        assert dm.on_change is None

    def test_reset_seq_resets_to_zero(self):
        dm = PipelineStepDemuxer()
        dm.demux("pipe-1", "step-a")
        assert dm._state._seq > 0
        dm.reset()
        assert dm._state._seq == 0
