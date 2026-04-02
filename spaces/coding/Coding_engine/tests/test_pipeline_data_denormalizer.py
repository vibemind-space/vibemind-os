"""Tests for PipelineDataDenormalizer."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_denormalizer import PipelineDataDenormalizer

class TestBasic:
    def test_returns_id(self):
        s = PipelineDataDenormalizer()
        assert s.denormalize("pipe-1", "k1").startswith("pddn-")
    def test_fields(self):
        s = PipelineDataDenormalizer()
        rid = s.denormalize("pipe-1", "k1", strategy="expand")
        rec = s.get_denormalization(rid)
        assert rec["pipeline_id"] == "pipe-1"
        assert rec["data_key"] == "k1"
        assert rec["strategy"] == "expand"
    def test_default_strategy(self):
        s = PipelineDataDenormalizer()
        rid = s.denormalize("pipe-1", "k1")
        assert s.get_denormalization(rid)["strategy"] == "flatten"
    def test_metadata_deepcopy(self):
        s = PipelineDataDenormalizer()
        m = {"k": [1]}
        rid = s.denormalize("pipe-1", "k1", metadata=m)
        m["k"].append(2)
        assert s.get_denormalization(rid)["metadata"]["k"] == [1]
    def test_empty_pipeline(self):
        assert PipelineDataDenormalizer().denormalize("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataDenormalizer().denormalize("pipe-1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineDataDenormalizer()
        rid = s.denormalize("pipe-1", "k1")
        assert s.get_denormalization(rid) is not None
    def test_not_found(self):
        assert PipelineDataDenormalizer().get_denormalization("nope") is None
    def test_copy(self):
        s = PipelineDataDenormalizer()
        rid = s.denormalize("pipe-1", "k1")
        assert s.get_denormalization(rid) is not s.get_denormalization(rid)

class TestList:
    def test_all(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1"); s.denormalize("pipe-2", "k2")
        assert len(s.get_denormalizations()) == 2
    def test_filter(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1"); s.denormalize("pipe-2", "k2")
        assert len(s.get_denormalizations(pipeline_id="pipe-1")) == 1
    def test_newest_first(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1"); time.sleep(0.01); s.denormalize("pipe-1", "k2")
        assert s.get_denormalizations(pipeline_id="pipe-1")[0]["data_key"] == "k2"

class TestCount:
    def test_total(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1"); s.denormalize("pipe-2", "k2")
        assert s.get_denormalization_count() == 2
    def test_filtered(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1"); s.denormalize("pipe-2", "k2")
        assert s.get_denormalization_count("pipe-1") == 1

class TestStats:
    def test_data(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1"); s.denormalize("pipe-2", "k2")
        st = s.get_stats()
        assert st["total_denormalizations"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataDenormalizer()
        called = []
        s.on_change = lambda a, d: called.append(a)
        s.denormalize("pipe-1", "k1")
        assert len(called) == 1
    def test_remove_true(self):
        s = PipelineDataDenormalizer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataDenormalizer().remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataDenormalizer()
        s.MAX_ENTRIES = 5
        for i in range(8): s.denormalize(f"pipe-{i}", f"k{i}")
        assert len(s._state.entries) < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1")
        s.on_change = lambda a, d: None
        s.reset()
        assert s.get_denormalization_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataDenormalizer()
        s.denormalize("pipe-1", "k1")
        s.reset()
        assert s._state._seq == 0
