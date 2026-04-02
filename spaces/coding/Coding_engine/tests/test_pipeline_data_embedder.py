"""Tests for PipelineDataEmbedder service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_embedder import PipelineDataEmbedder

class TestIdGeneration:
    def test_prefix(self):
        assert PipelineDataEmbedder().embed("p1", "k1").startswith("pdem-")
    def test_unique(self):
        s = PipelineDataEmbedder()
        ids = {s.embed("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20

class TestEmbedBasic:
    def test_returns_id(self):
        assert len(PipelineDataEmbedder().embed("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataEmbedder()
        rid = s.embed("p1", "k1", dimensions=256)
        e = s.get_embedding(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["dimensions"] == 256
    def test_metadata_deepcopy(self):
        s = PipelineDataEmbedder()
        m = {"a": [1]}
        rid = s.embed("p1", "k1", metadata=m)
        m["a"].append(2)
        assert s.get_embedding(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataEmbedder()
        before = time.time()
        assert s.get_embedding(s.embed("p1", "k1"))["created_at"] >= before
    def test_empty_pipeline(self):
        assert PipelineDataEmbedder().embed("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataEmbedder().embed("p1", "") == ""

class TestGetEmbedding:
    def test_found(self):
        s = PipelineDataEmbedder()
        assert s.get_embedding(s.embed("p1", "k1")) is not None
    def test_not_found(self):
        assert PipelineDataEmbedder().get_embedding("xxx") is None
    def test_copy(self):
        s = PipelineDataEmbedder()
        rid = s.embed("p1", "k1")
        assert s.get_embedding(rid) is not s.get_embedding(rid)

class TestGetEmbeddings:
    def test_all(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.embed("p2", "k2")
        assert len(s.get_embeddings()) == 2
    def test_filter(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.embed("p2", "k2")
        assert len(s.get_embeddings(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.embed("p1", "k2")
        assert s.get_embeddings(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataEmbedder()
        for i in range(10): s.embed("p1", f"k{i}")
        assert len(s.get_embeddings(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.embed("p2", "k2")
        assert s.get_embedding_count() == 2
    def test_filtered(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.embed("p2", "k2")
        assert s.get_embedding_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataEmbedder().get_embedding_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineDataEmbedder().get_stats()["total_embeddings"] == 0
    def test_data(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.embed("p2", "k2")
        assert s.get_stats()["total_embeddings"] == 2
        assert s.get_stats()["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataEmbedder()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.embed("p1", "k1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = PipelineDataEmbedder()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataEmbedder().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataEmbedder()
        s.MAX_ENTRIES = 5
        for i in range(8): s.embed("p1", f"k{i}")
        assert s.get_embedding_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.reset()
        assert s.get_embedding_count() == 0
    def test_callbacks(self):
        s = PipelineDataEmbedder()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataEmbedder()
        s.embed("p1", "k1"); s.reset()
        assert s._state._seq == 0
