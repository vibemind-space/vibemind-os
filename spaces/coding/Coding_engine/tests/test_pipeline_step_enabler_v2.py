import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_enabler_v2 import PipelineStepEnablerV2

class TestBasic:
    def test_returns_id(self):
        assert PipelineStepEnablerV2().enable_v2("p1", "s1").startswith("psev-")
    def test_fields(self):
        s = PipelineStepEnablerV2(); rid = s.enable_v2("p1", "s1", force=True)
        e = s.get_enablement(rid)
        assert e["pipeline_id"] == "p1" and e["step_name"] == "s1" and e["force"] is True
    def test_default_force(self):
        s = PipelineStepEnablerV2(); rid = s.enable_v2("p1", "s1")
        assert s.get_enablement(rid)["force"] is False
    def test_metadata_deepcopy(self):
        s = PipelineStepEnablerV2(); m = {"x": [1]}
        rid = s.enable_v2("p1", "s1", metadata=m); m["x"].append(2)
        assert s.get_enablement(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineStepEnablerV2().enable_v2("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepEnablerV2().enable_v2("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineStepEnablerV2(); rid = s.enable_v2("p1", "s1")
        assert s.get_enablement(rid) is not None
    def test_not_found(self):
        assert PipelineStepEnablerV2().get_enablement("nope") is None
    def test_copy(self):
        s = PipelineStepEnablerV2(); rid = s.enable_v2("p1", "s1")
        assert s.get_enablement(rid) is not s.get_enablement(rid)
class TestList:
    def test_all(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.enable_v2("p2", "s2")
        assert len(s.get_enablements()) == 2
    def test_filter(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.enable_v2("p2", "s2")
        assert len(s.get_enablements("p1")) == 1
    def test_newest_first(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.enable_v2("p1", "s2")
        assert s.get_enablements("p1")[0]["_seq"] > s.get_enablements("p1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.enable_v2("p2", "s2")
        assert s.get_enablement_count() == 2
    def test_filtered(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.enable_v2("p2", "s2")
        assert s.get_enablement_count("p1") == 1
class TestStats:
    def test_data(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.enable_v2("p2", "s2")
        assert s.get_stats()["total_enablements"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepEnablerV2(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.enable_v2("p1", "s1")
        assert "enabled" in calls
    def test_remove_true(self):
        s = PipelineStepEnablerV2(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepEnablerV2().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineStepEnablerV2(); s.MAX_ENTRIES = 5
        for i in range(8): s.enable_v2("p1", f"s{i}")
        assert s.get_enablement_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.reset()
        assert s.get_enablement_count() == 0
    def test_seq(self):
        s = PipelineStepEnablerV2(); s.enable_v2("p1", "s1"); s.reset()
        assert s._state._seq == 0
