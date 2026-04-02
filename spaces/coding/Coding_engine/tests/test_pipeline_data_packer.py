"""Tests for PipelineDataPacker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_packer import PipelineDataPacker

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineDataPacker()
        assert s.pack("p1", "k1").startswith("pdpk-")
    def test_unique(self):
        s = PipelineDataPacker()
        ids = {s.pack("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20

class TestPackBasic:
    def test_returns_id(self):
        s = PipelineDataPacker()
        assert len(s.pack("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataPacker()
        rid = s.pack("p1", "k1", format="binary")
        e = s.get_pack(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["format"] == "binary"
    def test_with_metadata(self):
        s = PipelineDataPacker()
        rid = s.pack("p1", "k1", metadata={"x": 1})
        assert s.get_pack(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataPacker()
        m = {"a": [1]}
        rid = s.pack("p1", "k1", metadata=m)
        m["a"].append(2)
        assert s.get_pack(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataPacker()
        before = time.time()
        rid = s.pack("p1", "k1")
        assert s.get_pack(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineDataPacker().pack("", "k1") == ""
    def test_empty_key_returns_empty(self):
        assert PipelineDataPacker().pack("p1", "") == ""

class TestGetPack:
    def test_found(self):
        s = PipelineDataPacker()
        rid = s.pack("p1", "k1")
        assert s.get_pack(rid) is not None
    def test_not_found(self):
        assert PipelineDataPacker().get_pack("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataPacker()
        rid = s.pack("p1", "k1")
        assert s.get_pack(rid) is not s.get_pack(rid)

class TestGetPacks:
    def test_all(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.pack("p2", "k2")
        assert len(s.get_packs()) == 2
    def test_filter(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.pack("p2", "k2")
        assert len(s.get_packs(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.pack("p1", "k2")
        assert s.get_packs(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataPacker()
        for i in range(10): s.pack("p1", f"k{i}")
        assert len(s.get_packs(limit=3)) == 3

class TestGetPackCount:
    def test_total(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.pack("p2", "k2")
        assert s.get_pack_count() == 2
    def test_filtered(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.pack("p2", "k2")
        assert s.get_pack_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataPacker().get_pack_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineDataPacker().get_stats()["total_packs"] == 0
    def test_with_data(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.pack("p2", "k2")
        st = s.get_stats()
        assert st["total_packs"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataPacker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.pack("p1", "k1")
        assert len(evts) >= 1
    def test_named_callback(self):
        s = PipelineDataPacker()
        evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.pack("p1", "k1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineDataPacker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineDataPacker().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataPacker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.pack("p1", f"k{i}")
        assert s.get_pack_count() < 8
    def test_prune_keeps_max(self):
        s = PipelineDataPacker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.pack("p1", f"k{i}")
        assert s.get_pack_count() == 5
    def test_no_prune_under_limit(self):
        s = PipelineDataPacker()
        s.MAX_ENTRIES = 5
        for i in range(4): s.pack("p1", f"k{i}")
        assert s.get_pack_count() == 4

class TestReset:
    def test_clears(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.reset()
        assert s.get_pack_count() == 0
    def test_clears_callbacks(self):
        s = PipelineDataPacker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineDataPacker()
        s.pack("p1", "k1"); s.reset()
        assert s._state._seq == 0
