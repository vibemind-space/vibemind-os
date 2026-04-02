import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_archiver import PipelineStepArchiver


class TestBasic:
    def test_returns_id(self):
        s = PipelineStepArchiver()
        rid = s.archive("p1", "step1")
        assert rid.startswith("psar-")

    def test_prefix(self):
        assert PipelineStepArchiver.PREFIX == "psar-"

    def test_fields(self):
        s = PipelineStepArchiver()
        rid = s.archive("p1", "step1", destination="s3")
        e = s.get_archive(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "step1"
        assert e["destination"] == "s3"

    def test_default_destination(self):
        s = PipelineStepArchiver()
        rid = s.archive("p1", "step1")
        assert s.get_archive(rid)["destination"] == "default"

    def test_metadata(self):
        s = PipelineStepArchiver()
        rid = s.archive("p1", "step1", metadata={"x": 1})
        assert s.get_archive(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = PipelineStepArchiver()
        m = {"x": [1]}
        rid = s.archive("p1", "step1", metadata=m)
        m["x"].append(2)
        assert s.get_archive(rid)["metadata"] == {"x": [1]}

    def test_created_at(self):
        s = PipelineStepArchiver()
        rid = s.archive("p1", "step1")
        assert s.get_archive(rid)["created_at"] <= time.time()

    def test_empty_pipeline(self):
        assert PipelineStepArchiver().archive("", "step1") == ""

    def test_empty_step(self):
        assert PipelineStepArchiver().archive("p1", "") == ""


class TestGet:
    def test_found(self):
        s = PipelineStepArchiver()
        rid = s.archive("p1", "step1")
        assert s.get_archive(rid) is not None

    def test_not_found(self):
        assert PipelineStepArchiver().get_archive("nope") is None

    def test_copy(self):
        s = PipelineStepArchiver()
        rid = s.archive("p1", "step1")
        assert s.get_archive(rid) is not s.get_archive(rid)


class TestList:
    def test_all(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.archive("p2", "s2")
        assert len(s.get_archives()) == 2

    def test_filter(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.archive("p2", "s2")
        assert len(s.get_archives("p1")) == 1

    def test_newest_first(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.archive("p1", "s2")
        recs = s.get_archives("p1")
        assert recs[0]["_seq"] > recs[1]["_seq"]

    def test_limit(self):
        s = PipelineStepArchiver()
        for i in range(5):
            s.archive("p1", f"s{i}")
        assert len(s.get_archives(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.archive("p2", "s2")
        assert s.get_archive_count() == 2

    def test_filtered(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.archive("p2", "s2")
        assert s.get_archive_count("p1") == 1

    def test_empty(self):
        assert PipelineStepArchiver().get_archive_count() == 0


class TestStats:
    def test_empty(self):
        st = PipelineStepArchiver().get_stats()
        assert st["total_archives"] == 0

    def test_data(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.archive("p2", "s2")
        st = s.get_stats()
        assert st["total_archives"] == 2
        assert st["unique_pipelines"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepArchiver()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.archive("p1", "s1")
        assert "archived" in calls

    def test_named_callback(self):
        s = PipelineStepArchiver()
        calls = []
        s._state.callbacks["cb1"] = lambda a, d: calls.append(a)
        s.archive("p1", "s1")
        assert "archived" in calls

    def test_remove_true(self):
        s = PipelineStepArchiver()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert PipelineStepArchiver().remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = PipelineStepArchiver()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.archive("p1", f"s{i}")
        assert s.get_archive_count() < 8


class TestReset:
    def test_clears(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.reset()
        assert s.get_archive_count() == 0

    def test_callbacks(self):
        s = PipelineStepArchiver()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = PipelineStepArchiver()
        s.archive("p1", "s1")
        s.reset()
        assert s._state._seq == 0
