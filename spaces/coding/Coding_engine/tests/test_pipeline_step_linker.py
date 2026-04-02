"""Tests for PipelineStepLinker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_linker import PipelineStepLinker

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineStepLinker()
        assert s.link("p1", "sa", "sb").startswith("pslk-")
    def test_unique(self):
        s = PipelineStepLinker()
        ids = {s.link("p1", f"sa{i}", f"sb{i}") for i in range(20)}
        assert len(ids) == 20

class TestLinkBasic:
    def test_returns_id(self):
        s = PipelineStepLinker()
        assert len(s.link("p1", "sa", "sb")) > 0
    def test_stores_fields(self):
        s = PipelineStepLinker()
        rid = s.link("p1", "sa", "sb", link_type="parallel")
        e = s.get_link(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_a"] == "sa"
        assert e["step_b"] == "sb"
        assert e["link_type"] == "parallel"
    def test_default_link_type(self):
        s = PipelineStepLinker()
        rid = s.link("p1", "sa", "sb")
        assert s.get_link(rid)["link_type"] == "sequential"
    def test_with_metadata(self):
        s = PipelineStepLinker()
        rid = s.link("p1", "sa", "sb", metadata={"x": 1})
        assert s.get_link(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepLinker()
        m = {"a": [1]}
        rid = s.link("p1", "sa", "sb", metadata=m)
        m["a"].append(2)
        assert s.get_link(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepLinker()
        before = time.time()
        rid = s.link("p1", "sa", "sb")
        assert s.get_link(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineStepLinker().link("", "sa", "sb") == ""
    def test_empty_step_a_returns_empty(self):
        assert PipelineStepLinker().link("p1", "", "sb") == ""
    def test_empty_step_b_returns_empty(self):
        assert PipelineStepLinker().link("p1", "sa", "") == ""

class TestGetLink:
    def test_found(self):
        s = PipelineStepLinker()
        rid = s.link("p1", "sa", "sb")
        assert s.get_link(rid) is not None
    def test_not_found(self):
        assert PipelineStepLinker().get_link("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepLinker()
        rid = s.link("p1", "sa", "sb")
        assert s.get_link(rid) is not s.get_link(rid)

class TestGetLinks:
    def test_all(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.link("p2", "sc", "sd")
        assert len(s.get_links()) == 2
    def test_filter(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.link("p2", "sc", "sd")
        assert len(s.get_links(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.link("p1", "sc", "sd")
        assert s.get_links(pipeline_id="p1")[0]["step_a"] == "sc"
    def test_limit(self):
        s = PipelineStepLinker()
        for i in range(10): s.link("p1", f"sa{i}", f"sb{i}")
        assert len(s.get_links(limit=3)) == 3

class TestGetLinkCount:
    def test_total(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.link("p2", "sc", "sd")
        assert s.get_link_count() == 2
    def test_filtered(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.link("p2", "sc", "sd")
        assert s.get_link_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepLinker().get_link_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepLinker().get_stats()["total_links"] == 0
    def test_with_data(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.link("p2", "sc", "sd")
        st = s.get_stats()
        assert st["total_links"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepLinker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.link("p1", "sa", "sb")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepLinker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepLinker().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepLinker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.link("p1", f"sa{i}", f"sb{i}")
        assert s.get_link_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.reset()
        assert s.get_link_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepLinker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepLinker()
        s.link("p1", "sa", "sb"); s.reset()
        assert s._state._seq == 0
