import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_unfreezer import PipelineStepUnfreezer

class TestBasic:
    def test_returns_id(self):
        assert PipelineStepUnfreezer().unfreeze("p1", "s1").startswith("psuf-")
    def test_fields(self):
        s = PipelineStepUnfreezer(); rid = s.unfreeze("p1", "s1", reason="ready")
        e = s.get_unfreeze(rid)
        assert e["pipeline_id"] == "p1" and e["step_name"] == "s1" and e["reason"] == "ready"
    def test_default_reason(self):
        s = PipelineStepUnfreezer(); rid = s.unfreeze("p1", "s1")
        assert s.get_unfreeze(rid)["reason"] == ""
    def test_metadata_deepcopy(self):
        s = PipelineStepUnfreezer(); m = {"x": [1]}
        rid = s.unfreeze("p1", "s1", metadata=m); m["x"].append(2)
        assert s.get_unfreeze(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineStepUnfreezer().unfreeze("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepUnfreezer().unfreeze("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineStepUnfreezer(); rid = s.unfreeze("p1", "s1")
        assert s.get_unfreeze(rid) is not None
    def test_not_found(self):
        assert PipelineStepUnfreezer().get_unfreeze("nope") is None
    def test_copy(self):
        s = PipelineStepUnfreezer(); rid = s.unfreeze("p1", "s1")
        assert s.get_unfreeze(rid) is not s.get_unfreeze(rid)
class TestList:
    def test_all(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.unfreeze("p2", "s2")
        assert len(s.get_unfreezes()) == 2
    def test_filter(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.unfreeze("p2", "s2")
        assert len(s.get_unfreezes("p1")) == 1
    def test_newest_first(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.unfreeze("p1", "s2")
        assert s.get_unfreezes("p1")[0]["_seq"] > s.get_unfreezes("p1")[1]["_seq"]
    def test_limit(self):
        s = PipelineStepUnfreezer()
        for i in range(5): s.unfreeze("p1", f"s{i}")
        assert len(s.get_unfreezes(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.unfreeze("p2", "s2")
        assert s.get_unfreeze_count() == 2
    def test_filtered(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.unfreeze("p2", "s2")
        assert s.get_unfreeze_count("p1") == 1
    def test_empty(self):
        assert PipelineStepUnfreezer().get_unfreeze_count() == 0
class TestStats:
    def test_empty(self):
        assert PipelineStepUnfreezer().get_stats()["total_unfreezes"] == 0
    def test_data(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.unfreeze("p2", "s2")
        assert s.get_stats()["total_unfreezes"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepUnfreezer(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.unfreeze("p1", "s1")
        assert "unfrozen" in calls
    def test_remove_true(self):
        s = PipelineStepUnfreezer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepUnfreezer().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineStepUnfreezer(); s.MAX_ENTRIES = 5
        for i in range(8): s.unfreeze("p1", f"s{i}")
        assert s.get_unfreeze_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.reset()
        assert s.get_unfreeze_count() == 0
    def test_callbacks(self):
        s = PipelineStepUnfreezer(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineStepUnfreezer(); s.unfreeze("p1", "s1"); s.reset()
        assert s._state._seq == 0
