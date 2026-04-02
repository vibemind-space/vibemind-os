import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_classifier import PipelineDataClassifier

class TestBasic:
    def test_returns_id(self):
        assert PipelineDataClassifier().classify("p1", "k1").startswith("pdcf-")
    def test_fields(self):
        s = PipelineDataClassifier(); rid = s.classify("p1", "k1", category="urgent")
        e = s.get_classification(rid)
        assert e["pipeline_id"] == "p1" and e["data_key"] == "k1" and e["category"] == "urgent"
    def test_default_category(self):
        s = PipelineDataClassifier(); rid = s.classify("p1", "k1")
        assert s.get_classification(rid)["category"] == "default"
    def test_metadata_deepcopy(self):
        s = PipelineDataClassifier(); m = {"x": [1]}
        rid = s.classify("p1", "k1", metadata=m); m["x"].append(2)
        assert s.get_classification(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineDataClassifier().classify("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataClassifier().classify("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineDataClassifier(); rid = s.classify("p1", "k1")
        assert s.get_classification(rid) is not None
    def test_not_found(self):
        assert PipelineDataClassifier().get_classification("nope") is None
    def test_copy(self):
        s = PipelineDataClassifier(); rid = s.classify("p1", "k1")
        assert s.get_classification(rid) is not s.get_classification(rid)
class TestList:
    def test_all(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.classify("p2", "k2")
        assert len(s.get_classifications()) == 2
    def test_filter(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.classify("p2", "k2")
        assert len(s.get_classifications("p1")) == 1
    def test_newest_first(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.classify("p1", "k2")
        assert s.get_classifications("p1")[0]["_seq"] > s.get_classifications("p1")[1]["_seq"]
class TestCount:
    def test_total(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.classify("p2", "k2")
        assert s.get_classification_count() == 2
    def test_filtered(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.classify("p2", "k2")
        assert s.get_classification_count("p1") == 1
class TestStats:
    def test_data(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.classify("p2", "k2")
        assert s.get_stats()["total_classifications"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataClassifier(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.classify("p1", "k1")
        assert "classified" in calls
    def test_remove_true(self):
        s = PipelineDataClassifier(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataClassifier().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineDataClassifier(); s.MAX_ENTRIES = 5
        for i in range(8): s.classify("p1", f"k{i}")
        assert s.get_classification_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.reset()
        assert s.get_classification_count() == 0
    def test_seq(self):
        s = PipelineDataClassifier(); s.classify("p1", "k1"); s.reset()
        assert s._state._seq == 0
