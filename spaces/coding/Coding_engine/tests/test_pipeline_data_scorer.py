import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_scorer import PipelineDataScorer

class TestBasic:
    def test_returns_id(self):
        assert PipelineDataScorer().score("p1", "k1").startswith("pdsc-")
    def test_fields(self):
        s = PipelineDataScorer(); rid = s.score("p1", "k1", score_value=9.5)
        e = s.get_score(rid)
        assert e["pipeline_id"] == "p1" and e["data_key"] == "k1" and e["score_value"] == 9.5
    def test_default_score(self):
        s = PipelineDataScorer(); rid = s.score("p1", "k1")
        assert s.get_score(rid)["score_value"] == 0.0
    def test_metadata_deepcopy(self):
        s = PipelineDataScorer(); m = {"x": [1]}
        rid = s.score("p1", "k1", metadata=m); m["x"].append(2)
        assert s.get_score(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineDataScorer().score("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataScorer().score("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineDataScorer(); rid = s.score("p1", "k1")
        assert s.get_score(rid) is not None
    def test_not_found(self):
        assert PipelineDataScorer().get_score("nope") is None
    def test_copy(self):
        s = PipelineDataScorer(); rid = s.score("p1", "k1")
        assert s.get_score(rid) is not s.get_score(rid)
class TestList:
    def test_all(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.score("p2", "k2")
        assert len(s.get_scores()) == 2
    def test_filter(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.score("p2", "k2")
        assert len(s.get_scores("p1")) == 1
    def test_newest_first(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.score("p1", "k2")
        assert s.get_scores("p1")[0]["_seq"] > s.get_scores("p1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.score("p2", "k2")
        assert s.get_score_count() == 2
    def test_filtered(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.score("p2", "k2")
        assert s.get_score_count("p1") == 1
class TestStats:
    def test_data(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.score("p2", "k2")
        assert s.get_stats()["total_scores"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataScorer(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.score("p1", "k1")
        assert "scored" in calls
    def test_remove_true(self):
        s = PipelineDataScorer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataScorer().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineDataScorer(); s.MAX_ENTRIES = 5
        for i in range(8): s.score("p1", f"k{i}")
        assert s.get_score_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.reset()
        assert s.get_score_count() == 0
    def test_seq(self):
        s = PipelineDataScorer(); s.score("p1", "k1"); s.reset()
        assert s._state._seq == 0
