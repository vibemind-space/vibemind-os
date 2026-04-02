"""Tests for PipelineStepMerger service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_merger import PipelineStepMerger

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineStepMerger()
        assert s.merge("p1", "sa", "sb", "merged").startswith("psmg-")
    def test_unique(self):
        s = PipelineStepMerger()
        ids = {s.merge("p1", f"sa{i}", f"sb{i}", f"m{i}") for i in range(20)}
        assert len(ids) == 20

class TestMergeBasic:
    def test_returns_id(self):
        s = PipelineStepMerger()
        assert len(s.merge("p1", "sa", "sb", "merged")) > 0
    def test_stores_fields(self):
        s = PipelineStepMerger()
        rid = s.merge("p1", "sa", "sb", "merged")
        e = s.get_merge(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_a"] == "sa"
        assert e["step_b"] == "sb"
        assert e["merged_name"] == "merged"
    def test_with_metadata(self):
        s = PipelineStepMerger()
        rid = s.merge("p1", "sa", "sb", "m", metadata={"x": 1})
        assert s.get_merge(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepMerger()
        m = {"a": [1]}
        rid = s.merge("p1", "sa", "sb", "m", metadata=m)
        m["a"].append(2)
        assert s.get_merge(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepMerger()
        before = time.time()
        rid = s.merge("p1", "sa", "sb", "m")
        assert s.get_merge(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineStepMerger().merge("", "sa", "sb", "m") == ""
    def test_empty_step_a_returns_empty(self):
        assert PipelineStepMerger().merge("p1", "", "sb", "m") == ""
    def test_empty_step_b_returns_empty(self):
        assert PipelineStepMerger().merge("p1", "sa", "", "m") == ""
    def test_empty_merged_name_returns_empty(self):
        assert PipelineStepMerger().merge("p1", "sa", "sb", "") == ""

class TestGetMerge:
    def test_found(self):
        s = PipelineStepMerger()
        rid = s.merge("p1", "sa", "sb", "m")
        assert s.get_merge(rid) is not None
    def test_not_found(self):
        assert PipelineStepMerger().get_merge("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepMerger()
        rid = s.merge("p1", "sa", "sb", "m")
        assert s.get_merge(rid) is not s.get_merge(rid)

class TestGetMerges:
    def test_all(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m1"); s.merge("p2", "sc", "sd", "m2")
        assert len(s.get_merges()) == 2
    def test_filter(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m1"); s.merge("p2", "sc", "sd", "m2")
        assert len(s.get_merges(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m1"); s.merge("p1", "sc", "sd", "m2")
        assert s.get_merges(pipeline_id="p1")[0]["merged_name"] == "m2"
    def test_limit(self):
        s = PipelineStepMerger()
        for i in range(10): s.merge("p1", f"sa{i}", f"sb{i}", f"m{i}")
        assert len(s.get_merges(limit=3)) == 3

class TestGetMergeCount:
    def test_total(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m1"); s.merge("p2", "sc", "sd", "m2")
        assert s.get_merge_count() == 2
    def test_filtered(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m1"); s.merge("p2", "sc", "sd", "m2")
        assert s.get_merge_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepMerger().get_merge_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepMerger().get_stats()["total_merges"] == 0
    def test_with_data(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m1"); s.merge("p2", "sc", "sd", "m2")
        st = s.get_stats()
        assert st["total_merges"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepMerger()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.merge("p1", "sa", "sb", "m")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepMerger()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepMerger().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepMerger()
        s.MAX_ENTRIES = 5
        for i in range(8): s.merge("p1", f"sa{i}", f"sb{i}", f"m{i}")
        assert s.get_merge_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m"); s.reset()
        assert s.get_merge_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepMerger()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepMerger()
        s.merge("p1", "sa", "sb", "m"); s.reset()
        assert s._state._seq == 0
