"""Tests for PipelineStepSwapper service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_swapper import PipelineStepSwapper

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineStepSwapper()
        assert s.swap("p1", "sa", "sb").startswith("pssw-")
    def test_unique(self):
        s = PipelineStepSwapper()
        ids = {s.swap("p1", f"sa{i}", f"sb{i}") for i in range(20)}
        assert len(ids) == 20

class TestSwapBasic:
    def test_returns_id(self):
        s = PipelineStepSwapper()
        assert len(s.swap("p1", "sa", "sb")) > 0
    def test_stores_fields(self):
        s = PipelineStepSwapper()
        rid = s.swap("p1", "sa", "sb")
        e = s.get_swap(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_a"] == "sa"
        assert e["step_b"] == "sb"
    def test_with_metadata(self):
        s = PipelineStepSwapper()
        rid = s.swap("p1", "sa", "sb", metadata={"x": 1})
        assert s.get_swap(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepSwapper()
        m = {"a": [1]}
        rid = s.swap("p1", "sa", "sb", metadata=m)
        m["a"].append(2)
        assert s.get_swap(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepSwapper()
        before = time.time()
        rid = s.swap("p1", "sa", "sb")
        assert s.get_swap(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineStepSwapper().swap("", "sa", "sb") == ""
    def test_empty_step_a_returns_empty(self):
        assert PipelineStepSwapper().swap("p1", "", "sb") == ""
    def test_empty_step_b_returns_empty(self):
        assert PipelineStepSwapper().swap("p1", "sa", "") == ""

class TestGetSwap:
    def test_found(self):
        s = PipelineStepSwapper()
        rid = s.swap("p1", "sa", "sb")
        assert s.get_swap(rid) is not None
    def test_not_found(self):
        assert PipelineStepSwapper().get_swap("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepSwapper()
        rid = s.swap("p1", "sa", "sb")
        assert s.get_swap(rid) is not s.get_swap(rid)

class TestGetSwaps:
    def test_all(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.swap("p2", "sc", "sd")
        assert len(s.get_swaps()) == 2
    def test_filter(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.swap("p2", "sc", "sd")
        assert len(s.get_swaps(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.swap("p1", "sc", "sd")
        assert s.get_swaps(pipeline_id="p1")[0]["step_a"] == "sc"
    def test_limit(self):
        s = PipelineStepSwapper()
        for i in range(10): s.swap("p1", f"sa{i}", f"sb{i}")
        assert len(s.get_swaps(limit=3)) == 3

class TestGetSwapCount:
    def test_total(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.swap("p2", "sc", "sd")
        assert s.get_swap_count() == 2
    def test_filtered(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.swap("p2", "sc", "sd")
        assert s.get_swap_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepSwapper().get_swap_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepSwapper().get_stats()["total_swaps"] == 0
    def test_with_data(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.swap("p2", "sc", "sd")
        st = s.get_stats()
        assert st["total_swaps"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepSwapper()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.swap("p1", "sa", "sb")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepSwapper()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepSwapper().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepSwapper()
        s.MAX_ENTRIES = 5
        for i in range(8): s.swap("p1", f"sa{i}", f"sb{i}")
        assert s.get_swap_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.reset()
        assert s.get_swap_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepSwapper()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepSwapper()
        s.swap("p1", "sa", "sb"); s.reset()
        assert s._state._seq == 0
