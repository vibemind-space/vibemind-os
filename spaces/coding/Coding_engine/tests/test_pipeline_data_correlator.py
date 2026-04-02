import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_correlator import PipelineDataCorrelator


class TestBasic:
    def test_returns_id(self):
        s = PipelineDataCorrelator()
        rid = s.correlate("p1", "ka", "kb")
        assert rid.startswith("pdcr-")

    def test_prefix(self):
        assert PipelineDataCorrelator.PREFIX == "pdcr-"

    def test_fields(self):
        s = PipelineDataCorrelator()
        rid = s.correlate("p1", "ka", "kb", method="spearman")
        e = s.get_correlation(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key_a"] == "ka"
        assert e["data_key_b"] == "kb"
        assert e["method"] == "spearman"

    def test_default_method(self):
        s = PipelineDataCorrelator()
        rid = s.correlate("p1", "ka", "kb")
        assert s.get_correlation(rid)["method"] == "pearson"

    def test_metadata(self):
        s = PipelineDataCorrelator()
        m = {"x": 1}
        rid = s.correlate("p1", "ka", "kb", metadata=m)
        assert s.get_correlation(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = PipelineDataCorrelator()
        m = {"x": [1]}
        rid = s.correlate("p1", "ka", "kb", metadata=m)
        m["x"].append(2)
        assert s.get_correlation(rid)["metadata"] == {"x": [1]}

    def test_created_at(self):
        s = PipelineDataCorrelator()
        rid = s.correlate("p1", "ka", "kb")
        assert s.get_correlation(rid)["created_at"] <= time.time()

    def test_empty_pipeline(self):
        s = PipelineDataCorrelator()
        assert s.correlate("", "ka", "kb") == ""

    def test_empty_key_a(self):
        s = PipelineDataCorrelator()
        assert s.correlate("p1", "", "kb") == ""

    def test_empty_key_b(self):
        s = PipelineDataCorrelator()
        assert s.correlate("p1", "ka", "") == ""


class TestGet:
    def test_found(self):
        s = PipelineDataCorrelator()
        rid = s.correlate("p1", "ka", "kb")
        assert s.get_correlation(rid) is not None

    def test_not_found(self):
        s = PipelineDataCorrelator()
        assert s.get_correlation("nope") is None

    def test_copy(self):
        s = PipelineDataCorrelator()
        rid = s.correlate("p1", "ka", "kb")
        a = s.get_correlation(rid)
        b = s.get_correlation(rid)
        assert a is not b


class TestList:
    def test_all(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.correlate("p2", "kc", "kd")
        assert len(s.get_correlations()) == 2

    def test_filter(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.correlate("p2", "kc", "kd")
        assert len(s.get_correlations("p1")) == 1

    def test_newest_first(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.correlate("p1", "kc", "kd")
        recs = s.get_correlations("p1")
        assert recs[0]["_seq"] > recs[1]["_seq"]

    def test_limit(self):
        s = PipelineDataCorrelator()
        for i in range(5):
            s.correlate("p1", f"a{i}", f"b{i}")
        assert len(s.get_correlations(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.correlate("p2", "kc", "kd")
        assert s.get_correlation_count() == 2

    def test_filtered(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.correlate("p2", "kc", "kd")
        assert s.get_correlation_count("p1") == 1

    def test_empty(self):
        assert PipelineDataCorrelator().get_correlation_count() == 0


class TestStats:
    def test_empty(self):
        s = PipelineDataCorrelator()
        st = s.get_stats()
        assert st["total_correlations"] == 0

    def test_data(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.correlate("p2", "kc", "kd")
        st = s.get_stats()
        assert st["total_correlations"] == 2
        assert st["unique_pipelines"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataCorrelator()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.correlate("p1", "ka", "kb")
        assert "correlated" in calls

    def test_named_callback(self):
        s = PipelineDataCorrelator()
        calls = []
        s._state.callbacks["cb1"] = lambda a, d: calls.append(a)
        s.correlate("p1", "ka", "kb")
        assert "correlated" in calls

    def test_remove_true(self):
        s = PipelineDataCorrelator()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = PipelineDataCorrelator()
        assert s.remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = PipelineDataCorrelator()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.correlate("p1", f"a{i}", f"b{i}")
        assert s.get_correlation_count() < 8


class TestReset:
    def test_clears(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.reset()
        assert s.get_correlation_count() == 0

    def test_callbacks(self):
        s = PipelineDataCorrelator()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = PipelineDataCorrelator()
        s.correlate("p1", "ka", "kb")
        s.reset()
        assert s._state._seq == 0
