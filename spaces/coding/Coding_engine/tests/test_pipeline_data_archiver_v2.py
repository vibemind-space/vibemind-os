import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_data_archiver_v2 import PipelineDataArchiverV2

class TestBasic:
    def test_returns_id(self):
        s = PipelineDataArchiverV2()
        rid = s.archive_v2("v1", "v2")
        assert rid.startswith("pdav-")
    def test_fields(self):
        s = PipelineDataArchiverV2()
        rid = s.archive_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_archive(rid)
        assert e["pipeline_id"] == "v1"
        assert e["data_key"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = PipelineDataArchiverV2()
        rid = s.archive_v2("v1", "v2")
        assert s.get_archive(rid)["retention"] == "30d"
    def test_metadata_deepcopy(self):
        s = PipelineDataArchiverV2()
        m = {"x": [1]}
        rid = s.archive_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_archive(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = PipelineDataArchiverV2()
        assert s.archive_v2("", "v2") == ""
    def test_empty_p2(self):
        s = PipelineDataArchiverV2()
        assert s.archive_v2("v1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineDataArchiverV2()
        rid = s.archive_v2("v1", "v2")
        assert s.get_archive(rid) is not None
    def test_not_found(self):
        s = PipelineDataArchiverV2()
        assert s.get_archive("nope") is None
    def test_copy(self):
        s = PipelineDataArchiverV2()
        rid = s.archive_v2("v1", "v2")
        assert s.get_archive(rid) is not s.get_archive(rid)
class TestList:
    def test_all(self):
        s = PipelineDataArchiverV2()
        s.archive_v2("v1", "v2")
        s.archive_v2("v3", "v4")
        assert len(s.get_archives()) == 2
    def test_filter(self):
        s = PipelineDataArchiverV2()
        s.archive_v2("v1", "v2")
        s.archive_v2("v3", "v4")
        assert len(s.get_archives(pipeline_id="v1")) == 1
    def test_newest_first(self):
        s = PipelineDataArchiverV2()
        s.archive_v2("v1", "w1")
        s.archive_v2("v1", "w2")
        items = s.get_archives(pipeline_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = PipelineDataArchiverV2()
        s.archive_v2("v1", "v2")
        s.archive_v2("v3", "v4")
        assert s.get_archive_count() == 2
    def test_filtered(self):
        s = PipelineDataArchiverV2()
        s.archive_v2("v1", "v2")
        s.archive_v2("v3", "v4")
        assert s.get_archive_count("v1") == 1
class TestStats:
    def test_data(self):
        s = PipelineDataArchiverV2()
        s.archive_v2("v1", "v2")
        assert s.get_stats()["total_archives"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataArchiverV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.archive_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = PipelineDataArchiverV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = PipelineDataArchiverV2()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineDataArchiverV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.archive_v2(f"p{i}", f"v{i}")
        assert s.get_archive_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = PipelineDataArchiverV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.archive_v2("t1", "a1")
        assert captured[0]["action"] == "archive_v2"
        assert captured[0]["record_id"].startswith("pdav-")
class TestReset:
    def test_clears(self):
        s = PipelineDataArchiverV2()
        s.on_change = lambda a, d: None
        s.archive_v2("v1", "v2")
        s.reset()
        assert s.get_archive_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataArchiverV2()
        s.archive_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
