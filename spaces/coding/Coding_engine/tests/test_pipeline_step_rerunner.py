import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_rerunner import PipelineStepRerunner

class TestBasic:
    def test_returns_id(self):
        assert PipelineStepRerunner().rerun("p1", "s1").startswith("psrr-")
    def test_fields(self):
        s = PipelineStepRerunner(); rid = s.rerun("p1", "s1", attempt=3)
        e = s.get_rerun(rid)
        assert e["pipeline_id"] == "p1" and e["step_name"] == "s1" and e["attempt"] == 3
    def test_default_attempt(self):
        s = PipelineStepRerunner(); rid = s.rerun("p1", "s1")
        assert s.get_rerun(rid)["attempt"] == 1
    def test_metadata(self):
        s = PipelineStepRerunner(); rid = s.rerun("p1", "s1", metadata={"x": 1})
        assert s.get_rerun(rid)["metadata"] == {"x": 1}
    def test_metadata_deepcopy(self):
        s = PipelineStepRerunner(); m = {"x": [1]}
        rid = s.rerun("p1", "s1", metadata=m); m["x"].append(2)
        assert s.get_rerun(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineStepRerunner().rerun("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepRerunner().rerun("p1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineStepRerunner(); rid = s.rerun("p1", "s1")
        assert s.get_rerun(rid) is not None
    def test_not_found(self):
        assert PipelineStepRerunner().get_rerun("nope") is None
    def test_copy(self):
        s = PipelineStepRerunner(); rid = s.rerun("p1", "s1")
        assert s.get_rerun(rid) is not s.get_rerun(rid)

class TestList:
    def test_all(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.rerun("p2", "s2")
        assert len(s.get_reruns()) == 2
    def test_filter(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.rerun("p2", "s2")
        assert len(s.get_reruns("p1")) == 1
    def test_newest_first(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.rerun("p1", "s2")
        assert s.get_reruns("p1")[0]["_seq"] > s.get_reruns("p1")[1]["_seq"]
    def test_limit(self):
        s = PipelineStepRerunner()
        for i in range(5): s.rerun("p1", f"s{i}")
        assert len(s.get_reruns(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.rerun("p2", "s2")
        assert s.get_rerun_count() == 2
    def test_filtered(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.rerun("p2", "s2")
        assert s.get_rerun_count("p1") == 1
    def test_empty(self):
        assert PipelineStepRerunner().get_rerun_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineStepRerunner().get_stats()["total_reruns"] == 0
    def test_data(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.rerun("p2", "s2")
        st = s.get_stats()
        assert st["total_reruns"] == 2 and st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepRerunner(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.rerun("p1", "s1")
        assert "rerun" in calls
    def test_remove_true(self):
        s = PipelineStepRerunner(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepRerunner().remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepRerunner(); s.MAX_ENTRIES = 5
        for i in range(8): s.rerun("p1", f"s{i}")
        assert s.get_rerun_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.reset()
        assert s.get_rerun_count() == 0
    def test_callbacks(self):
        s = PipelineStepRerunner(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineStepRerunner(); s.rerun("p1", "s1"); s.reset()
        assert s._state._seq == 0
