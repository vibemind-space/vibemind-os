import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_comparer import PipelineDataComparer

class TestBasic:
    def test_returns_id(self):
        s = PipelineDataComparer()
        assert s.compare("p1", "ka", "kb").startswith("pdcp-")
    def test_fields(self):
        s = PipelineDataComparer()
        rid = s.compare("p1", "ka", "kb", mode="strict")
        e = s.get_comparison(rid)
        assert e["pipeline_id"] == "p1" and e["data_key_a"] == "ka" and e["mode"] == "strict"
    def test_default_mode(self):
        s = PipelineDataComparer()
        rid = s.compare("p1", "ka", "kb")
        assert s.get_comparison(rid)["mode"] == "diff"
    def test_metadata(self):
        s = PipelineDataComparer()
        rid = s.compare("p1", "ka", "kb", metadata={"x": 1})
        assert s.get_comparison(rid)["metadata"] == {"x": 1}
    def test_metadata_deepcopy(self):
        s = PipelineDataComparer(); m = {"x": [1]}
        rid = s.compare("p1", "ka", "kb", metadata=m); m["x"].append(2)
        assert s.get_comparison(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineDataComparer().compare("", "ka", "kb") == ""
    def test_empty_key_a(self):
        assert PipelineDataComparer().compare("p1", "", "kb") == ""
    def test_empty_key_b(self):
        assert PipelineDataComparer().compare("p1", "ka", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineDataComparer(); rid = s.compare("p1", "ka", "kb")
        assert s.get_comparison(rid) is not None
    def test_not_found(self):
        assert PipelineDataComparer().get_comparison("nope") is None
    def test_copy(self):
        s = PipelineDataComparer(); rid = s.compare("p1", "ka", "kb")
        assert s.get_comparison(rid) is not s.get_comparison(rid)

class TestList:
    def test_all(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.compare("p2", "kc", "kd")
        assert len(s.get_comparisons()) == 2
    def test_filter(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.compare("p2", "kc", "kd")
        assert len(s.get_comparisons("p1")) == 1
    def test_newest_first(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.compare("p1", "kc", "kd")
        assert s.get_comparisons("p1")[0]["_seq"] > s.get_comparisons("p1")[1]["_seq"]
    def test_limit(self):
        s = PipelineDataComparer()
        for i in range(5): s.compare("p1", f"a{i}", f"b{i}")
        assert len(s.get_comparisons(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.compare("p2", "kc", "kd")
        assert s.get_comparison_count() == 2
    def test_filtered(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.compare("p2", "kc", "kd")
        assert s.get_comparison_count("p1") == 1
    def test_empty(self):
        assert PipelineDataComparer().get_comparison_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineDataComparer().get_stats()["total_comparisons"] == 0
    def test_data(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.compare("p2", "kc", "kd")
        st = s.get_stats()
        assert st["total_comparisons"] == 2 and st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataComparer(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.compare("p1", "ka", "kb")
        assert "compared" in calls
    def test_remove_true(self):
        s = PipelineDataComparer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataComparer().remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataComparer(); s.MAX_ENTRIES = 5
        for i in range(8): s.compare("p1", f"a{i}", f"b{i}")
        assert s.get_comparison_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.reset()
        assert s.get_comparison_count() == 0
    def test_callbacks(self):
        s = PipelineDataComparer(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataComparer(); s.compare("p1", "ka", "kb"); s.reset()
        assert s._state._seq == 0
