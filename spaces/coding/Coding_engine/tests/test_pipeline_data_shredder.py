"""Tests for PipelineDataShredder service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_shredder import PipelineDataShredder

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineDataShredder()
        assert s.shred("p1", "k1").startswith("pdsh-")
    def test_unique(self):
        s = PipelineDataShredder()
        ids = {s.shred("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20

class TestShredBasic:
    def test_returns_id(self):
        s = PipelineDataShredder()
        assert len(s.shred("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataShredder()
        rid = s.shred("p1", "k1", passes=5)
        e = s.get_shred(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["passes"] == 5
    def test_default_passes(self):
        s = PipelineDataShredder()
        rid = s.shred("p1", "k1")
        assert s.get_shred(rid)["passes"] == 3
    def test_with_metadata(self):
        s = PipelineDataShredder()
        rid = s.shred("p1", "k1", metadata={"x": 1})
        assert s.get_shred(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataShredder()
        m = {"a": [1]}
        rid = s.shred("p1", "k1", metadata=m)
        m["a"].append(2)
        assert s.get_shred(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataShredder()
        before = time.time()
        rid = s.shred("p1", "k1")
        assert s.get_shred(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineDataShredder().shred("", "k1") == ""
    def test_empty_key_returns_empty(self):
        assert PipelineDataShredder().shred("p1", "") == ""

class TestGetShred:
    def test_found(self):
        s = PipelineDataShredder()
        rid = s.shred("p1", "k1")
        assert s.get_shred(rid) is not None
    def test_not_found(self):
        assert PipelineDataShredder().get_shred("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataShredder()
        rid = s.shred("p1", "k1")
        assert s.get_shred(rid) is not s.get_shred(rid)

class TestGetShreds:
    def test_all(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.shred("p2", "k2")
        assert len(s.get_shreds()) == 2
    def test_filter(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.shred("p2", "k2")
        assert len(s.get_shreds(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.shred("p1", "k2")
        assert s.get_shreds(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataShredder()
        for i in range(10): s.shred("p1", f"k{i}")
        assert len(s.get_shreds(limit=3)) == 3

class TestGetShredCount:
    def test_total(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.shred("p2", "k2")
        assert s.get_shred_count() == 2
    def test_filtered(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.shred("p2", "k2")
        assert s.get_shred_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataShredder().get_shred_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineDataShredder().get_stats()["total_shreds"] == 0
    def test_with_data(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.shred("p2", "k2")
        st = s.get_stats()
        assert st["total_shreds"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataShredder()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.shred("p1", "k1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineDataShredder()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineDataShredder().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataShredder()
        s.MAX_ENTRIES = 5
        for i in range(8): s.shred("p1", f"k{i}")
        assert s.get_shred_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.reset()
        assert s.get_shred_count() == 0
    def test_clears_callbacks(self):
        s = PipelineDataShredder()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineDataShredder()
        s.shred("p1", "k1"); s.reset()
        assert s._state._seq == 0
