"""Tests for PipelineStepNamer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_namer import PipelineStepNamer

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineStepNamer()
        assert s.name_step("p1", "s1").startswith("psnm-")
    def test_unique(self):
        s = PipelineStepNamer()
        ids = {s.name_step("p1", f"s{i}") for i in range(20)}
        assert len(ids) == 20

class TestNameStepBasic:
    def test_returns_id(self):
        s = PipelineStepNamer()
        assert len(s.name_step("p1", "s1")) > 0
    def test_stores_fields(self):
        s = PipelineStepNamer()
        rid = s.name_step("p1", "s1", new_name="renamed")
        e = s.get_naming(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "s1"
        assert e["new_name"] == "renamed"
    def test_with_metadata(self):
        s = PipelineStepNamer()
        rid = s.name_step("p1", "s1", metadata={"x": 1})
        assert s.get_naming(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepNamer()
        m = {"a": [1]}
        rid = s.name_step("p1", "s1", metadata=m)
        m["a"].append(2)
        assert s.get_naming(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepNamer()
        before = time.time()
        rid = s.name_step("p1", "s1")
        assert s.get_naming(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineStepNamer().name_step("", "s1") == ""
    def test_empty_step_returns_empty(self):
        assert PipelineStepNamer().name_step("p1", "") == ""

class TestGetNaming:
    def test_found(self):
        s = PipelineStepNamer()
        rid = s.name_step("p1", "s1")
        assert s.get_naming(rid) is not None
    def test_not_found(self):
        assert PipelineStepNamer().get_naming("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepNamer()
        rid = s.name_step("p1", "s1")
        assert s.get_naming(rid) is not s.get_naming(rid)

class TestGetNamings:
    def test_all(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.name_step("p2", "s2")
        assert len(s.get_namings()) == 2
    def test_filter(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.name_step("p2", "s2")
        assert len(s.get_namings(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.name_step("p1", "s2")
        assert s.get_namings(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepNamer()
        for i in range(10): s.name_step("p1", f"s{i}")
        assert len(s.get_namings(limit=3)) == 3

class TestGetNamingCount:
    def test_total(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.name_step("p2", "s2")
        assert s.get_naming_count() == 2
    def test_filtered(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.name_step("p2", "s2")
        assert s.get_naming_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepNamer().get_naming_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepNamer().get_stats()["total_namings"] == 0
    def test_with_data(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.name_step("p2", "s2")
        st = s.get_stats()
        assert st["total_namings"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepNamer()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.name_step("p1", "s1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepNamer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepNamer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepNamer()
        s.MAX_ENTRIES = 5
        for i in range(8): s.name_step("p1", f"s{i}")
        assert s.get_naming_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.reset()
        assert s.get_naming_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepNamer()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepNamer()
        s.name_step("p1", "s1"); s.reset()
        assert s._state._seq == 0
