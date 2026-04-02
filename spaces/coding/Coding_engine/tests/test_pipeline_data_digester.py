"""Tests for PipelineDataDigester service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_digester import PipelineDataDigester

class TestIdGeneration:
    def test_prefix(self):
        assert PipelineDataDigester().digest("p1", "k1").startswith("pddi-")
    def test_unique(self):
        s = PipelineDataDigester()
        ids = {s.digest("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20

class TestDigestBasic:
    def test_returns_id(self):
        assert len(PipelineDataDigester().digest("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataDigester()
        rid = s.digest("p1", "k1", digest_type="full")
        e = s.get_digest(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["digest_type"] == "full"
    def test_default_type(self):
        s = PipelineDataDigester()
        rid = s.digest("p1", "k1")
        assert s.get_digest(rid)["digest_type"] == "summary"
    def test_with_metadata(self):
        s = PipelineDataDigester()
        rid = s.digest("p1", "k1", metadata={"x": 1})
        assert s.get_digest(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataDigester(); m = {"a": [1]}
        rid = s.digest("p1", "k1", metadata=m); m["a"].append(2)
        assert s.get_digest(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataDigester(); before = time.time()
        rid = s.digest("p1", "k1")
        assert s.get_digest(rid)["created_at"] >= before
    def test_empty_pipeline(self):
        assert PipelineDataDigester().digest("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataDigester().digest("p1", "") == ""

class TestGetDigest:
    def test_found(self):
        s = PipelineDataDigester(); rid = s.digest("p1", "k1")
        assert s.get_digest(rid) is not None
    def test_not_found(self):
        assert PipelineDataDigester().get_digest("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataDigester(); rid = s.digest("p1", "k1")
        assert s.get_digest(rid) is not s.get_digest(rid)

class TestGetDigests:
    def test_all(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.digest("p2","k2")
        assert len(s.get_digests()) == 2
    def test_filter(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.digest("p2","k2")
        assert len(s.get_digests(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.digest("p1","k2")
        assert s.get_digests(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataDigester()
        for i in range(10): s.digest("p1", f"k{i}")
        assert len(s.get_digests(limit=3)) == 3

class TestGetDigestCount:
    def test_total(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.digest("p2","k2")
        assert s.get_digest_count() == 2
    def test_filtered(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.digest("p2","k2")
        assert s.get_digest_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataDigester().get_digest_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineDataDigester().get_stats()["total_digests"] == 0
    def test_with_data(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.digest("p2","k2")
        st = s.get_stats()
        assert st["total_digests"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataDigester(); evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.digest("p1", "k1"); assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineDataDigester(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineDataDigester().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataDigester(); s.MAX_ENTRIES = 5
        for i in range(8): s.digest("p1", f"k{i}")
        assert s.get_digest_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.reset()
        assert s.get_digest_count() == 0
    def test_clears_callbacks(self):
        s = PipelineDataDigester(); s.on_change = lambda a,d: None; s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineDataDigester(); s.digest("p1","k1"); s.reset()
        assert s._state._seq == 0
