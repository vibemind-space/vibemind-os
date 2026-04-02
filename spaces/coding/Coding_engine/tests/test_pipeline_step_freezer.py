"""Tests for PipelineStepFreezer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_freezer import PipelineStepFreezer

class TestIdGeneration:
    def test_prefix(self):
        f = PipelineStepFreezer()
        rid = f.freeze("p1", "s1")
        assert rid.startswith("psfz-")
    def test_unique(self):
        f = PipelineStepFreezer()
        ids = {f.freeze("p1", f"s{i}") for i in range(20)}
        assert len(ids) == 20

class TestFreezeBasic:
    def test_returns_id(self):
        f = PipelineStepFreezer()
        assert len(f.freeze("p1", "s1")) > 0
    def test_stores_fields(self):
        f = PipelineStepFreezer()
        rid = f.freeze("p1", "step-a", reason="maintenance")
        e = f.get_freeze(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "step-a"
        assert e["reason"] == "maintenance"
    def test_with_metadata(self):
        f = PipelineStepFreezer()
        rid = f.freeze("p1", "s1", metadata={"k": "v"})
        assert f.get_freeze(rid)["metadata"]["k"] == "v"
    def test_created_at(self):
        f = PipelineStepFreezer()
        before = time.time()
        rid = f.freeze("p1", "s1")
        assert f.get_freeze(rid)["created_at"] >= before

class TestGetFreeze:
    def test_found(self):
        f = PipelineStepFreezer()
        rid = f.freeze("p1", "s1")
        assert f.get_freeze(rid) is not None
    def test_not_found(self):
        f = PipelineStepFreezer()
        assert f.get_freeze("xxx") is None
    def test_returns_copy(self):
        f = PipelineStepFreezer()
        rid = f.freeze("p1", "s1")
        assert f.get_freeze(rid) is not f.get_freeze(rid)

class TestGetFreezes:
    def test_all(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.freeze("p2", "s2")
        assert len(f.get_freezes()) == 2
    def test_filter(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.freeze("p2", "s2")
        assert len(f.get_freezes(pipeline_id="p1")) == 1
    def test_newest_first(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.freeze("p1", "s2")
        assert f.get_freezes(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        f = PipelineStepFreezer()
        for i in range(10): f.freeze("p1", f"s{i}")
        assert len(f.get_freezes(limit=3)) == 3

class TestGetFreezeCount:
    def test_total(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.freeze("p2", "s2")
        assert f.get_freeze_count() == 2
    def test_filtered(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.freeze("p2", "s2")
        assert f.get_freeze_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepFreezer().get_freeze_count() == 0

class TestGetStats:
    def test_empty(self):
        s = PipelineStepFreezer().get_stats()
        assert s["total_freezes"] == 0
    def test_with_data(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.freeze("p2", "s2")
        s = f.get_stats()
        assert s["total_freezes"] == 2
        assert s["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        f = PipelineStepFreezer()
        evts = []
        f.on_change = lambda a, d: evts.append(a)
        f.freeze("p1", "s1")
        assert len(evts) >= 1
    def test_on_change_clear(self):
        f = PipelineStepFreezer()
        f.on_change = lambda a, d: None
        f.on_change = None
        assert f.on_change is None
    def test_remove_callback_true(self):
        f = PipelineStepFreezer()
        f._state.callbacks["cb1"] = lambda a, d: None
        assert f.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepFreezer().remove_callback("x") is False
    def test_exception_suppressed(self):
        f = PipelineStepFreezer()
        f.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError)
        assert f.freeze("p1", "s1").startswith("psfz-")

class TestPrune:
    def test_prune(self):
        f = PipelineStepFreezer()
        f.MAX_ENTRIES = 5
        for i in range(8): f.freeze("p1", f"s{i}")
        assert f.get_freeze_count() < 8

class TestReset:
    def test_clears(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.reset()
        assert f.get_freeze_count() == 0
    def test_clears_callbacks(self):
        f = PipelineStepFreezer()
        f.on_change = lambda a, d: None
        f.reset()
        assert f.on_change is None
    def test_resets_seq(self):
        f = PipelineStepFreezer()
        f.freeze("p1", "s1"); f.reset()
        assert f._state._seq == 0
