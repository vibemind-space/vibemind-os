"""Tests for PipelineDataUnpacker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_unpacker import PipelineDataUnpacker

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineDataUnpacker()
        assert s.unpack("p1", "k1").startswith("pdun-")
    def test_unique(self):
        s = PipelineDataUnpacker()
        ids = {s.unpack("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20

class TestUnpackBasic:
    def test_returns_id(self):
        s = PipelineDataUnpacker()
        assert len(s.unpack("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataUnpacker()
        rid = s.unpack("p1", "k1", format="json")
        e = s.get_unpack(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["format"] == "json"
    def test_with_metadata(self):
        s = PipelineDataUnpacker()
        rid = s.unpack("p1", "k1", metadata={"x": 1})
        assert s.get_unpack(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataUnpacker()
        m = {"a": [1]}
        rid = s.unpack("p1", "k1", metadata=m)
        m["a"].append(2)
        assert s.get_unpack(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataUnpacker()
        before = time.time()
        rid = s.unpack("p1", "k1")
        assert s.get_unpack(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineDataUnpacker().unpack("", "k1") == ""
    def test_empty_key_returns_empty(self):
        assert PipelineDataUnpacker().unpack("p1", "") == ""

class TestGetUnpack:
    def test_found(self):
        s = PipelineDataUnpacker()
        rid = s.unpack("p1", "k1")
        assert s.get_unpack(rid) is not None
    def test_not_found(self):
        assert PipelineDataUnpacker().get_unpack("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataUnpacker()
        rid = s.unpack("p1", "k1")
        assert s.get_unpack(rid) is not s.get_unpack(rid)

class TestGetUnpacks:
    def test_all(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.unpack("p2", "k2")
        assert len(s.get_unpacks()) == 2
    def test_filter(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.unpack("p2", "k2")
        assert len(s.get_unpacks(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.unpack("p1", "k2")
        assert s.get_unpacks(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataUnpacker()
        for i in range(10): s.unpack("p1", f"k{i}")
        assert len(s.get_unpacks(limit=3)) == 3

class TestGetUnpackCount:
    def test_total(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.unpack("p2", "k2")
        assert s.get_unpack_count() == 2
    def test_filtered(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.unpack("p2", "k2")
        assert s.get_unpack_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataUnpacker().get_unpack_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineDataUnpacker().get_stats()["total_unpacks"] == 0
    def test_with_data(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.unpack("p2", "k2")
        st = s.get_stats()
        assert st["total_unpacks"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataUnpacker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.unpack("p1", "k1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineDataUnpacker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineDataUnpacker().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataUnpacker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.unpack("p1", f"k{i}")
        assert s.get_unpack_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.reset()
        assert s.get_unpack_count() == 0
    def test_clears_callbacks(self):
        s = PipelineDataUnpacker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineDataUnpacker()
        s.unpack("p1", "k1"); s.reset()
        assert s._state._seq == 0
