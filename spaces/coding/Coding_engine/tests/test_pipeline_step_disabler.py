"""Tests for PipelineStepDisabler service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_disabler import PipelineStepDisabler

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineStepDisabler()
        assert s.disable("p1", "s1").startswith("psdi-")
    def test_unique(self):
        s = PipelineStepDisabler()
        ids = {s.disable("p1", f"s{i}") for i in range(20)}
        assert len(ids) == 20

class TestDisableBasic:
    def test_returns_id(self):
        s = PipelineStepDisabler()
        assert len(s.disable("p1", "s1")) > 0
    def test_stores_fields(self):
        s = PipelineStepDisabler()
        rid = s.disable("p1", "s1", reason="maintenance")
        e = s.get_disablement(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "s1"
        assert e["reason"] == "maintenance"
    def test_with_metadata(self):
        s = PipelineStepDisabler()
        rid = s.disable("p1", "s1", metadata={"x": 1})
        assert s.get_disablement(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepDisabler()
        m = {"a": [1]}
        rid = s.disable("p1", "s1", metadata=m)
        m["a"].append(2)
        assert s.get_disablement(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepDisabler()
        before = time.time()
        rid = s.disable("p1", "s1")
        assert s.get_disablement(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineStepDisabler().disable("", "s1") == ""
    def test_empty_step_returns_empty(self):
        assert PipelineStepDisabler().disable("p1", "") == ""

class TestGetDisablement:
    def test_found(self):
        s = PipelineStepDisabler()
        rid = s.disable("p1", "s1")
        assert s.get_disablement(rid) is not None
    def test_not_found(self):
        assert PipelineStepDisabler().get_disablement("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepDisabler()
        rid = s.disable("p1", "s1")
        assert s.get_disablement(rid) is not s.get_disablement(rid)

class TestGetDisablements:
    def test_all(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.disable("p2", "s2")
        assert len(s.get_disablements()) == 2
    def test_filter(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.disable("p2", "s2")
        assert len(s.get_disablements(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.disable("p1", "s2")
        assert s.get_disablements(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepDisabler()
        for i in range(10): s.disable("p1", f"s{i}")
        assert len(s.get_disablements(limit=3)) == 3

class TestGetDisablementCount:
    def test_total(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.disable("p2", "s2")
        assert s.get_disablement_count() == 2
    def test_filtered(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.disable("p2", "s2")
        assert s.get_disablement_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepDisabler().get_disablement_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepDisabler().get_stats()["total_disablements"] == 0
    def test_with_data(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.disable("p2", "s2")
        st = s.get_stats()
        assert st["total_disablements"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepDisabler()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.disable("p1", "s1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepDisabler()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepDisabler().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepDisabler()
        s.MAX_ENTRIES = 5
        for i in range(8): s.disable("p1", f"s{i}")
        assert s.get_disablement_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.reset()
        assert s.get_disablement_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepDisabler()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepDisabler()
        s.disable("p1", "s1"); s.reset()
        assert s._state._seq == 0
