"""Tests for PipelineDataFingerprinter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_fingerprinter import PipelineDataFingerprinter

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineDataFingerprinter()
        assert s.fingerprint("p1", "k1").startswith("pdfp-")
    def test_unique(self):
        s = PipelineDataFingerprinter()
        ids = {s.fingerprint("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20

class TestFingerprintBasic:
    def test_returns_id(self):
        s = PipelineDataFingerprinter()
        assert len(s.fingerprint("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataFingerprinter()
        rid = s.fingerprint("p1", "k1", algorithm="md5")
        e = s.get_fingerprint(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["algorithm"] == "md5"
    def test_default_algorithm(self):
        s = PipelineDataFingerprinter()
        rid = s.fingerprint("p1", "k1")
        assert s.get_fingerprint(rid)["algorithm"] == "sha256"
    def test_with_metadata(self):
        s = PipelineDataFingerprinter()
        rid = s.fingerprint("p1", "k1", metadata={"x": 1})
        assert s.get_fingerprint(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataFingerprinter()
        m = {"a": [1]}
        rid = s.fingerprint("p1", "k1", metadata=m)
        m["a"].append(2)
        assert s.get_fingerprint(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataFingerprinter()
        before = time.time()
        rid = s.fingerprint("p1", "k1")
        assert s.get_fingerprint(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineDataFingerprinter().fingerprint("", "k1") == ""
    def test_empty_key_returns_empty(self):
        assert PipelineDataFingerprinter().fingerprint("p1", "") == ""

class TestGetFingerprint:
    def test_found(self):
        s = PipelineDataFingerprinter()
        rid = s.fingerprint("p1", "k1")
        assert s.get_fingerprint(rid) is not None
    def test_not_found(self):
        assert PipelineDataFingerprinter().get_fingerprint("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataFingerprinter()
        rid = s.fingerprint("p1", "k1")
        assert s.get_fingerprint(rid) is not s.get_fingerprint(rid)

class TestGetFingerprints:
    def test_all(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.fingerprint("p2", "k2")
        assert len(s.get_fingerprints()) == 2
    def test_filter(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.fingerprint("p2", "k2")
        assert len(s.get_fingerprints(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.fingerprint("p1", "k2")
        assert s.get_fingerprints(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataFingerprinter()
        for i in range(10): s.fingerprint("p1", f"k{i}")
        assert len(s.get_fingerprints(limit=3)) == 3

class TestGetFingerprintCount:
    def test_total(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.fingerprint("p2", "k2")
        assert s.get_fingerprint_count() == 2
    def test_filtered(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.fingerprint("p2", "k2")
        assert s.get_fingerprint_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataFingerprinter().get_fingerprint_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineDataFingerprinter().get_stats()["total_fingerprints"] == 0
    def test_with_data(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.fingerprint("p2", "k2")
        st = s.get_stats()
        assert st["total_fingerprints"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataFingerprinter()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.fingerprint("p1", "k1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineDataFingerprinter()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineDataFingerprinter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataFingerprinter()
        s.MAX_ENTRIES = 5
        for i in range(8): s.fingerprint("p1", f"k{i}")
        assert s.get_fingerprint_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.reset()
        assert s.get_fingerprint_count() == 0
    def test_clears_callbacks(self):
        s = PipelineDataFingerprinter()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineDataFingerprinter()
        s.fingerprint("p1", "k1"); s.reset()
        assert s._state._seq == 0
