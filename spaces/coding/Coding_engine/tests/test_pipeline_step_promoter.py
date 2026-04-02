import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_promoter import PipelineStepPromoter

class TestBasic:
    def test_returns_id(self):
        assert PipelineStepPromoter().promote("p1", "s1").startswith("pspm-")
    def test_fields(self):
        s = PipelineStepPromoter(); rid = s.promote("p1", "s1", target_env="staging")
        e = s.get_promotion(rid)
        assert e["pipeline_id"] == "p1" and e["step_name"] == "s1" and e["target_env"] == "staging"
    def test_default_env(self):
        s = PipelineStepPromoter(); rid = s.promote("p1", "s1")
        assert s.get_promotion(rid)["target_env"] == "prod"
    def test_metadata_deepcopy(self):
        s = PipelineStepPromoter(); m = {"x": [1]}
        rid = s.promote("p1", "s1", metadata=m); m["x"].append(2)
        assert s.get_promotion(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineStepPromoter().promote("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepPromoter().promote("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineStepPromoter(); rid = s.promote("p1", "s1")
        assert s.get_promotion(rid) is not None
    def test_not_found(self):
        assert PipelineStepPromoter().get_promotion("nope") is None
    def test_copy(self):
        s = PipelineStepPromoter(); rid = s.promote("p1", "s1")
        assert s.get_promotion(rid) is not s.get_promotion(rid)
class TestList:
    def test_all(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.promote("p2", "s2")
        assert len(s.get_promotions()) == 2
    def test_filter(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.promote("p2", "s2")
        assert len(s.get_promotions("p1")) == 1
    def test_newest_first(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.promote("p1", "s2")
        assert s.get_promotions("p1")[0]["_seq"] > s.get_promotions("p1")[1]["_seq"]
    def test_limit(self):
        s = PipelineStepPromoter()
        for i in range(5): s.promote("p1", f"s{i}")
        assert len(s.get_promotions(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.promote("p2", "s2")
        assert s.get_promotion_count() == 2
    def test_filtered(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.promote("p2", "s2")
        assert s.get_promotion_count("p1") == 1
    def test_empty(self):
        assert PipelineStepPromoter().get_promotion_count() == 0
class TestStats:
    def test_data(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.promote("p2", "s2")
        assert s.get_stats()["total_promotions"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepPromoter(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.promote("p1", "s1")
        assert "promoted" in calls
    def test_remove_true(self):
        s = PipelineStepPromoter(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepPromoter().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineStepPromoter(); s.MAX_ENTRIES = 5
        for i in range(8): s.promote("p1", f"s{i}")
        assert s.get_promotion_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.reset()
        assert s.get_promotion_count() == 0
    def test_seq(self):
        s = PipelineStepPromoter(); s.promote("p1", "s1"); s.reset()
        assert s._state._seq == 0
