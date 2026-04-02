"""Tests for PipelineStepCacher service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_cacher import PipelineStepCacher

class TestIdGeneration:
    def test_prefix(self):
        assert PipelineStepCacher().cache("p1","s1").startswith("psch-")
    def test_unique(self):
        s = PipelineStepCacher()
        assert len({s.cache("p1", f"s{i}") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(PipelineStepCacher().cache("p1","s1")) > 0
    def test_stores_fields(self):
        s = PipelineStepCacher(); rid=s.cache("p1","s1",ttl_seconds=7200)
        e = s.get_cache_entry(rid)
        assert e["pipeline_id"]=="p1" and e["step_name"]=="s1" and e["ttl_seconds"]==7200
    def test_default_ttl(self):
        s = PipelineStepCacher(); rid=s.cache("p1","s1")
        assert s.get_cache_entry(rid)["ttl_seconds"] == 3600
    def test_metadata(self):
        s = PipelineStepCacher(); rid=s.cache("p1","s1",metadata={"x":1})
        assert s.get_cache_entry(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepCacher(); m={"a":[1]}; rid=s.cache("p1","s1",metadata=m); m["a"].append(2)
        assert s.get_cache_entry(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepCacher(); b=time.time(); rid=s.cache("p1","s1")
        assert s.get_cache_entry(rid)["created_at"] >= b
    def test_empty_pipeline(self):
        assert PipelineStepCacher().cache("","s1") == ""
    def test_empty_step(self):
        assert PipelineStepCacher().cache("p1","") == ""

class TestGet:
    def test_found(self):
        s = PipelineStepCacher(); rid=s.cache("p1","s1"); assert s.get_cache_entry(rid) is not None
    def test_not_found(self):
        assert PipelineStepCacher().get_cache_entry("xxx") is None
    def test_copy(self):
        s = PipelineStepCacher(); rid=s.cache("p1","s1")
        assert s.get_cache_entry(rid) is not s.get_cache_entry(rid)

class TestList:
    def test_all(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.cache("p2","s2")
        assert len(s.get_cache_entries()) == 2
    def test_filter(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.cache("p2","s2")
        assert len(s.get_cache_entries(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.cache("p1","s2")
        assert s.get_cache_entries(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepCacher()
        for i in range(10): s.cache("p1", f"s{i}")
        assert len(s.get_cache_entries(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.cache("p2","s2")
        assert s.get_cache_count() == 2
    def test_filtered(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.cache("p2","s2")
        assert s.get_cache_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepCacher().get_cache_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineStepCacher().get_stats()["total_caches"] == 0
    def test_data(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.cache("p2","s2")
        assert s.get_stats()["total_caches"] == 2 and s.get_stats()["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepCacher(); e=[]; s.on_change=lambda a,d: e.append(a); s.cache("p1","s1")
        assert len(e) >= 1
    def test_remove_true(self):
        s = PipelineStepCacher(); s._state.callbacks["cb1"]=lambda a,d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepCacher().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepCacher(); s.MAX_ENTRIES=5
        for i in range(8): s.cache("p1", f"s{i}")
        assert s.get_cache_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.reset(); assert s.get_cache_count() == 0
    def test_callbacks(self):
        s = PipelineStepCacher(); s.on_change=lambda a,d: None; s.reset(); assert s.on_change is None
    def test_seq(self):
        s = PipelineStepCacher(); s.cache("p1","s1"); s.reset(); assert s._state._seq == 0
