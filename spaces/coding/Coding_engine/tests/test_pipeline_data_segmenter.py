"""Tests for PipelineDataSegmenter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_segmenter import PipelineDataSegmenter

class TestIdGeneration:
    def test_prefix(self):
        assert PipelineDataSegmenter().segment("p1", "k1").startswith("pdsg-")
    def test_unique(self):
        s = PipelineDataSegmenter()
        assert len({s.segment("p1", f"k{i}") for i in range(20)}) == 20

class TestSegmentBasic:
    def test_returns_id(self):
        assert len(PipelineDataSegmenter().segment("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataSegmenter(); rid = s.segment("p1", "k1", segment_count=4)
        e = s.get_segment(rid)
        assert e["pipeline_id"] == "p1" and e["data_key"] == "k1" and e["segment_count"] == 4
    def test_default_count(self):
        s = PipelineDataSegmenter(); rid = s.segment("p1", "k1")
        assert s.get_segment(rid)["segment_count"] == 2
    def test_with_metadata(self):
        s = PipelineDataSegmenter(); rid = s.segment("p1", "k1", metadata={"x":1})
        assert s.get_segment(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataSegmenter(); m={"a":[1]}; rid=s.segment("p1","k1",metadata=m); m["a"].append(2)
        assert s.get_segment(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataSegmenter(); b=time.time(); rid=s.segment("p1","k1")
        assert s.get_segment(rid)["created_at"] >= b
    def test_empty_pipeline(self):
        assert PipelineDataSegmenter().segment("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataSegmenter().segment("p1", "") == ""

class TestGetSegment:
    def test_found(self):
        s = PipelineDataSegmenter(); rid=s.segment("p1","k1"); assert s.get_segment(rid) is not None
    def test_not_found(self):
        assert PipelineDataSegmenter().get_segment("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataSegmenter(); rid=s.segment("p1","k1")
        assert s.get_segment(rid) is not s.get_segment(rid)

class TestGetSegments:
    def test_all(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.segment("p2","k2")
        assert len(s.get_segments()) == 2
    def test_filter(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.segment("p2","k2")
        assert len(s.get_segments(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.segment("p1","k2")
        assert s.get_segments(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataSegmenter()
        for i in range(10): s.segment("p1", f"k{i}")
        assert len(s.get_segments(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.segment("p2","k2")
        assert s.get_segment_count() == 2
    def test_filtered(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.segment("p2","k2")
        assert s.get_segment_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataSegmenter().get_segment_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineDataSegmenter().get_stats()["total_segments"] == 0
    def test_data(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.segment("p2","k2")
        assert s.get_stats()["total_segments"] == 2 and s.get_stats()["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataSegmenter(); e=[]; s.on_change=lambda a,d: e.append(a); s.segment("p1","k1")
        assert len(e) >= 1
    def test_remove_true(self):
        s = PipelineDataSegmenter(); s._state.callbacks["cb1"]=lambda a,d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataSegmenter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataSegmenter(); s.MAX_ENTRIES=5
        for i in range(8): s.segment("p1", f"k{i}")
        assert s.get_segment_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.reset(); assert s.get_segment_count() == 0
    def test_callbacks(self):
        s = PipelineDataSegmenter(); s.on_change=lambda a,d: None; s.reset(); assert s.on_change is None
    def test_seq(self):
        s = PipelineDataSegmenter(); s.segment("p1","k1"); s.reset(); assert s._state._seq == 0
