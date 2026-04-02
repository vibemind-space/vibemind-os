"""Tests for PipelineDataPrefetcher service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_prefetcher import PipelineDataPrefetcher

class TestIdGeneration:
    def test_prefix(self):
        assert PipelineDataPrefetcher().prefetch("p1", "k1").startswith("pdpf-")
    def test_unique(self):
        s = PipelineDataPrefetcher()
        ids = {s.prefetch("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20
    def test_non_empty(self):
        assert len(PipelineDataPrefetcher().prefetch("p1", "k1")) > 5

class TestPrefetchBasic:
    def test_returns_id(self):
        assert len(PipelineDataPrefetcher().prefetch("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataPrefetcher()
        rid = s.prefetch("p1", "k1", priority=5)
        e = s.get_prefetch(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["priority"] == 5
    def test_default_priority(self):
        s = PipelineDataPrefetcher()
        rid = s.prefetch("p1", "k1")
        assert s.get_prefetch(rid)["priority"] == 0
    def test_metadata_deepcopy(self):
        s = PipelineDataPrefetcher()
        m = {"a": [1]}
        rid = s.prefetch("p1", "k1", metadata=m)
        m["a"].append(2)
        assert s.get_prefetch(rid)["metadata"]["a"] == [1]
    def test_metadata_default(self):
        s = PipelineDataPrefetcher()
        rid = s.prefetch("p1", "k1")
        assert s.get_prefetch(rid)["metadata"] == {}
    def test_created_at(self):
        s = PipelineDataPrefetcher()
        before = time.time()
        assert s.get_prefetch(s.prefetch("p1", "k1"))["created_at"] >= before
    def test_empty_pipeline(self):
        assert PipelineDataPrefetcher().prefetch("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataPrefetcher().prefetch("p1", "") == ""
    def test_both_empty(self):
        assert PipelineDataPrefetcher().prefetch("", "") == ""
    def test_record_id_in_entry(self):
        s = PipelineDataPrefetcher()
        rid = s.prefetch("p1", "k1")
        assert s.get_prefetch(rid)["record_id"] == rid

class TestGetPrefetch:
    def test_found(self):
        s = PipelineDataPrefetcher()
        assert s.get_prefetch(s.prefetch("p1", "k1")) is not None
    def test_not_found(self):
        assert PipelineDataPrefetcher().get_prefetch("xxx") is None
    def test_copy(self):
        s = PipelineDataPrefetcher()
        rid = s.prefetch("p1", "k1")
        assert s.get_prefetch(rid) is not s.get_prefetch(rid)

class TestGetPrefetches:
    def test_all(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.prefetch("p2", "k2")
        assert len(s.get_prefetches()) == 2
    def test_filter(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.prefetch("p2", "k2")
        assert len(s.get_prefetches(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.prefetch("p1", "k2")
        assert s.get_prefetches(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataPrefetcher()
        for i in range(10): s.prefetch("p1", f"k{i}")
        assert len(s.get_prefetches(limit=3)) == 3
    def test_empty(self):
        assert len(PipelineDataPrefetcher().get_prefetches()) == 0
    def test_filter_no_match(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1")
        assert len(s.get_prefetches(pipeline_id="p999")) == 0

class TestCount:
    def test_total(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.prefetch("p2", "k2")
        assert s.get_prefetch_count() == 2
    def test_filtered(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.prefetch("p2", "k2")
        assert s.get_prefetch_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataPrefetcher().get_prefetch_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineDataPrefetcher().get_stats()["total_prefetches"] == 0
    def test_data(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.prefetch("p2", "k2")
        assert s.get_stats()["total_prefetches"] == 2
        assert s.get_stats()["unique_pipelines"] == 2
    def test_same_pipeline(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.prefetch("p1", "k2")
        assert s.get_stats()["unique_pipelines"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataPrefetcher()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.prefetch("p1", "k1")
        assert len(evts) >= 1
    def test_on_change_action(self):
        s = PipelineDataPrefetcher()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.prefetch("p1", "k1")
        assert "prefetched" in evts
    def test_named_callback(self):
        s = PipelineDataPrefetcher()
        evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.prefetch("p1", "k1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = PipelineDataPrefetcher()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataPrefetcher().remove_callback("x") is False
    def test_on_change_property(self):
        s = PipelineDataPrefetcher()
        assert s.on_change is None
        cb = lambda a, d: None
        s.on_change = cb
        assert s.on_change is cb
    def test_callback_error_no_crash(self):
        s = PipelineDataPrefetcher()
        s.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        s.prefetch("p1", "k1")  # should not raise

class TestPrune:
    def test_prune(self):
        s = PipelineDataPrefetcher()
        s.MAX_ENTRIES = 5
        for i in range(8): s.prefetch("p1", f"k{i}")
        assert s.get_prefetch_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.reset()
        assert s.get_prefetch_count() == 0
    def test_callbacks(self):
        s = PipelineDataPrefetcher()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.reset()
        assert s._state._seq == 0
    def test_stats_after_reset(self):
        s = PipelineDataPrefetcher()
        s.prefetch("p1", "k1"); s.reset()
        assert s.get_stats()["total_prefetches"] == 0
