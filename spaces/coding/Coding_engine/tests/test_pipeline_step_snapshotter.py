"""Tests for PipelineStepSnapshotter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_snapshotter import PipelineStepSnapshotter

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineStepSnapshotter()
        assert s.snapshot("p1", "s1").startswith("pssn-")
    def test_unique(self):
        s = PipelineStepSnapshotter()
        ids = {s.snapshot("p1", f"s{i}") for i in range(20)}
        assert len(ids) == 20

class TestSnapshotBasic:
    def test_returns_id(self):
        s = PipelineStepSnapshotter()
        assert len(s.snapshot("p1", "s1")) > 0
    def test_stores_fields(self):
        s = PipelineStepSnapshotter()
        rid = s.snapshot("p1", "step-a", state_data={"x": 1})
        e = s.get_snapshot(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "step-a"
    def test_with_metadata(self):
        s = PipelineStepSnapshotter()
        rid = s.snapshot("p1", "s1", metadata={"k": "v"})
        assert s.get_snapshot(rid)["metadata"]["k"] == "v"
    def test_created_at(self):
        s = PipelineStepSnapshotter()
        before = time.time()
        rid = s.snapshot("p1", "s1")
        assert s.get_snapshot(rid)["created_at"] >= before

class TestGetSnapshot:
    def test_found(self):
        s = PipelineStepSnapshotter()
        rid = s.snapshot("p1", "s1")
        assert s.get_snapshot(rid) is not None
    def test_not_found(self):
        assert PipelineStepSnapshotter().get_snapshot("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepSnapshotter()
        rid = s.snapshot("p1", "s1")
        assert s.get_snapshot(rid) is not s.get_snapshot(rid)

class TestGetSnapshots:
    def test_all(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.snapshot("p2", "s2")
        assert len(s.get_snapshots()) == 2
    def test_filter(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.snapshot("p2", "s2")
        assert len(s.get_snapshots(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.snapshot("p1", "s2")
        assert s.get_snapshots(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepSnapshotter()
        for i in range(10): s.snapshot("p1", f"s{i}")
        assert len(s.get_snapshots(limit=3)) == 3

class TestGetSnapshotCount:
    def test_total(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.snapshot("p2", "s2")
        assert s.get_snapshot_count() == 2
    def test_filtered(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.snapshot("p2", "s2")
        assert s.get_snapshot_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepSnapshotter().get_snapshot_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepSnapshotter().get_stats()["total_snapshots"] == 0
    def test_with_data(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.snapshot("p2", "s2")
        st = s.get_stats()
        assert st["total_snapshots"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepSnapshotter()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.snapshot("p1", "s1")
        assert len(evts) >= 1
    def test_on_change_clear(self):
        s = PipelineStepSnapshotter()
        s.on_change = lambda a, d: None
        s.on_change = None
        assert s.on_change is None
    def test_remove_callback_true(self):
        s = PipelineStepSnapshotter()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepSnapshotter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepSnapshotter()
        s.MAX_ENTRIES = 5
        for i in range(8): s.snapshot("p1", f"s{i}")
        assert s.get_snapshot_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.reset()
        assert s.get_snapshot_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepSnapshotter()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepSnapshotter()
        s.snapshot("p1", "s1"); s.reset()
        assert s._state._seq == 0
