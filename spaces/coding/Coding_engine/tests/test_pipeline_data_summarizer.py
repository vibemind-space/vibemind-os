import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_summarizer import PipelineDataSummarizer


class TestBasic:
    def test_returns_id(self):
        s = PipelineDataSummarizer()
        assert s.summarize("p1", "k1").startswith("pdsu-")

    def test_fields(self):
        s = PipelineDataSummarizer()
        rid = s.summarize("p1", "k1", summary_type="detailed")
        e = s.get_summary(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["summary_type"] == "detailed"

    def test_default_type(self):
        s = PipelineDataSummarizer()
        rid = s.summarize("p1", "k1")
        assert s.get_summary(rid)["summary_type"] == "brief"

    def test_metadata(self):
        s = PipelineDataSummarizer()
        rid = s.summarize("p1", "k1", metadata={"x": 1})
        assert s.get_summary(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = PipelineDataSummarizer()
        m = {"x": [1]}
        rid = s.summarize("p1", "k1", metadata=m)
        m["x"].append(2)
        assert s.get_summary(rid)["metadata"] == {"x": [1]}

    def test_empty_pipeline(self):
        assert PipelineDataSummarizer().summarize("", "k1") == ""

    def test_empty_key(self):
        assert PipelineDataSummarizer().summarize("p1", "") == ""


class TestGet:
    def test_found(self):
        s = PipelineDataSummarizer()
        rid = s.summarize("p1", "k1")
        assert s.get_summary(rid) is not None

    def test_not_found(self):
        assert PipelineDataSummarizer().get_summary("nope") is None

    def test_copy(self):
        s = PipelineDataSummarizer()
        rid = s.summarize("p1", "k1")
        assert s.get_summary(rid) is not s.get_summary(rid)


class TestList:
    def test_all(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.summarize("p2", "k2")
        assert len(s.get_summaries()) == 2

    def test_filter(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.summarize("p2", "k2")
        assert len(s.get_summaries("p1")) == 1

    def test_newest_first(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.summarize("p1", "k2")
        assert s.get_summaries("p1")[0]["_seq"] > s.get_summaries("p1")[1]["_seq"]

    def test_limit(self):
        s = PipelineDataSummarizer()
        for i in range(5): s.summarize("p1", f"k{i}")
        assert len(s.get_summaries(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.summarize("p2", "k2")
        assert s.get_summary_count() == 2

    def test_filtered(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.summarize("p2", "k2")
        assert s.get_summary_count("p1") == 1

    def test_empty(self):
        assert PipelineDataSummarizer().get_summary_count() == 0


class TestStats:
    def test_empty(self):
        assert PipelineDataSummarizer().get_stats()["total_summaries"] == 0

    def test_data(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.summarize("p2", "k2")
        st = s.get_stats()
        assert st["total_summaries"] == 2
        assert st["unique_pipelines"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataSummarizer()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.summarize("p1", "k1")
        assert "summarized" in calls

    def test_remove_true(self):
        s = PipelineDataSummarizer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert PipelineDataSummarizer().remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = PipelineDataSummarizer(); s.MAX_ENTRIES = 5
        for i in range(8): s.summarize("p1", f"k{i}")
        assert s.get_summary_count() < 8


class TestReset:
    def test_clears(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.reset()
        assert s.get_summary_count() == 0

    def test_callbacks(self):
        s = PipelineDataSummarizer()
        s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = PipelineDataSummarizer()
        s.summarize("p1", "k1"); s.reset()
        assert s._state._seq == 0
