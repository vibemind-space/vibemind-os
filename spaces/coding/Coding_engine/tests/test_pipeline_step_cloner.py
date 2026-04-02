"""Tests for PipelineStepCloner service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_cloner import PipelineStepCloner

class TestIdGeneration:
    def test_prefix(self):
        assert PipelineStepCloner().clone_step("p1", "s1", "s2").startswith("pscl-")
    def test_unique(self):
        s = PipelineStepCloner()
        ids = {s.clone_step("p1", f"s{i}", f"t{i}") for i in range(20)}
        assert len(ids) == 20

class TestCloneStepBasic:
    def test_returns_id(self):
        assert len(PipelineStepCloner().clone_step("p1", "s1", "s2")) > 0
    def test_stores_fields(self):
        s = PipelineStepCloner()
        rid = s.clone_step("p1", "src", "tgt")
        e = s.get_clone(rid)
        assert e["pipeline_id"] == "p1"
        assert e["source_step"] == "src"
        assert e["target_step"] == "tgt"
    def test_metadata_deepcopy(self):
        s = PipelineStepCloner()
        m = {"a": [1]}
        rid = s.clone_step("p1", "s1", "s2", metadata=m)
        m["a"].append(2)
        assert s.get_clone(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepCloner()
        before = time.time()
        assert s.get_clone(s.clone_step("p1", "s1", "s2"))["created_at"] >= before
    def test_empty_pipeline(self):
        assert PipelineStepCloner().clone_step("", "s1", "s2") == ""
    def test_empty_source(self):
        assert PipelineStepCloner().clone_step("p1", "", "s2") == ""
    def test_empty_target(self):
        assert PipelineStepCloner().clone_step("p1", "s1", "") == ""

class TestGetClone:
    def test_found(self):
        s = PipelineStepCloner()
        assert s.get_clone(s.clone_step("p1", "s1", "s2")) is not None
    def test_not_found(self):
        assert PipelineStepCloner().get_clone("xxx") is None
    def test_copy(self):
        s = PipelineStepCloner()
        rid = s.clone_step("p1", "s1", "s2")
        assert s.get_clone(rid) is not s.get_clone(rid)

class TestGetClones:
    def test_all(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.clone_step("p2", "s2", "t2")
        assert len(s.get_clones()) == 2
    def test_filter(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.clone_step("p2", "s2", "t2")
        assert len(s.get_clones(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.clone_step("p1", "s2", "t2")
        assert s.get_clones(pipeline_id="p1")[0]["source_step"] == "s2"
    def test_limit(self):
        s = PipelineStepCloner()
        for i in range(10): s.clone_step("p1", f"s{i}", f"t{i}")
        assert len(s.get_clones(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.clone_step("p2", "s2", "t2")
        assert s.get_clone_count() == 2
    def test_filtered(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.clone_step("p2", "s2", "t2")
        assert s.get_clone_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepCloner().get_clone_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineStepCloner().get_stats()["total_clones"] == 0
    def test_data(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.clone_step("p2", "s2", "t2")
        assert s.get_stats()["total_clones"] == 2
        assert s.get_stats()["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepCloner()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.clone_step("p1", "s1", "t1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = PipelineStepCloner()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepCloner().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepCloner()
        s.MAX_ENTRIES = 5
        for i in range(8): s.clone_step("p1", f"s{i}", f"t{i}")
        assert s.get_clone_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.reset()
        assert s.get_clone_count() == 0
    def test_callbacks(self):
        s = PipelineStepCloner()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineStepCloner()
        s.clone_step("p1", "s1", "t1"); s.reset()
        assert s._state._seq == 0
