import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_reorchestrator import PipelineStepReorchestrator

class TestBasic:
    def test_returns_id(self):
        assert PipelineStepReorchestrator().reorchestrate("p1", "s1").startswith("psro-")
    def test_fields(self):
        s = PipelineStepReorchestrator(); rid = s.reorchestrate("p1", "s1", strategy="parallel")
        e = s.get_reorchestration(rid)
        assert e["pipeline_id"] == "p1" and e["step_name"] == "s1" and e["strategy"] == "parallel"
    def test_default_strategy(self):
        s = PipelineStepReorchestrator(); rid = s.reorchestrate("p1", "s1")
        assert s.get_reorchestration(rid)["strategy"] == "default"
    def test_metadata_deepcopy(self):
        s = PipelineStepReorchestrator(); m = {"x": [1]}
        rid = s.reorchestrate("p1", "s1", metadata=m); m["x"].append(2)
        assert s.get_reorchestration(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineStepReorchestrator().reorchestrate("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepReorchestrator().reorchestrate("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineStepReorchestrator(); rid = s.reorchestrate("p1", "s1")
        assert s.get_reorchestration(rid) is not None
    def test_not_found(self):
        assert PipelineStepReorchestrator().get_reorchestration("nope") is None
    def test_copy(self):
        s = PipelineStepReorchestrator(); rid = s.reorchestrate("p1", "s1")
        assert s.get_reorchestration(rid) is not s.get_reorchestration(rid)
class TestList:
    def test_all(self):
        s = PipelineStepReorchestrator(); s.reorchestrate("p1", "s1"); s.reorchestrate("p2", "s2")
        assert len(s.get_reorchestrations()) == 2
    def test_filter(self):
        s = PipelineStepReorchestrator(); s.reorchestrate("p1", "s1"); s.reorchestrate("p2", "s2")
        assert len(s.get_reorchestrations("p1")) == 1
    def test_newest_first(self):
        s = PipelineStepReorchestrator(); s.reorchestrate("p1", "s1"); s.reorchestrate("p1", "s2")
        assert s.get_reorchestrations("p1")[0]["_seq"] > s.get_reorchestrations("p1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = PipelineStepReorchestrator(); s.reorchestrate("p1", "s1"); s.reorchestrate("p2", "s2")
        assert s.get_reorchestration_count() == 2
class TestStats:
    def test_data(self):
        s = PipelineStepReorchestrator(); s.reorchestrate("p1", "s1"); s.reorchestrate("p2", "s2")
        assert s.get_stats()["total_reorchestrations"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepReorchestrator(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.reorchestrate("p1", "s1")
        assert "reorchestrated" in calls
    def test_remove_true(self):
        s = PipelineStepReorchestrator(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepReorchestrator().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineStepReorchestrator(); s.MAX_ENTRIES = 5
        for i in range(8): s.reorchestrate("p1", f"s{i}")
        assert s.get_reorchestration_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineStepReorchestrator(); s.reorchestrate("p1", "s1"); s.reset()
        assert s.get_reorchestration_count() == 0
    def test_seq(self):
        s = PipelineStepReorchestrator(); s.reorchestrate("p1", "s1"); s.reset()
        assert s._state._seq == 0
