import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_enqueuer import PipelineDataEnqueuer

class TestBasic:
    def test_returns_id(self):
        assert PipelineDataEnqueuer().enqueue("p1", "k1").startswith("pden-")
    def test_fields(self):
        s = PipelineDataEnqueuer(); rid = s.enqueue("p1", "k1", queue_name="high")
        e = s.get_enqueue(rid)
        assert e["pipeline_id"] == "p1" and e["data_key"] == "k1" and e["queue_name"] == "high"
    def test_default_queue(self):
        s = PipelineDataEnqueuer(); rid = s.enqueue("p1", "k1")
        assert s.get_enqueue(rid)["queue_name"] == "default"
    def test_metadata_deepcopy(self):
        s = PipelineDataEnqueuer(); m = {"x": [1]}
        rid = s.enqueue("p1", "k1", metadata=m); m["x"].append(2)
        assert s.get_enqueue(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineDataEnqueuer().enqueue("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataEnqueuer().enqueue("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineDataEnqueuer(); rid = s.enqueue("p1", "k1")
        assert s.get_enqueue(rid) is not None
    def test_not_found(self):
        assert PipelineDataEnqueuer().get_enqueue("nope") is None
    def test_copy(self):
        s = PipelineDataEnqueuer(); rid = s.enqueue("p1", "k1")
        assert s.get_enqueue(rid) is not s.get_enqueue(rid)
class TestList:
    def test_all(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.enqueue("p2", "k2")
        assert len(s.get_enqueues()) == 2
    def test_filter(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.enqueue("p2", "k2")
        assert len(s.get_enqueues("p1")) == 1
    def test_newest_first(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.enqueue("p1", "k2")
        assert s.get_enqueues("p1")[0]["_seq"] > s.get_enqueues("p1")[1]["_seq"]
    def test_limit(self):
        s = PipelineDataEnqueuer()
        for i in range(5): s.enqueue("p1", f"k{i}")
        assert len(s.get_enqueues(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.enqueue("p2", "k2")
        assert s.get_enqueue_count() == 2
    def test_filtered(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.enqueue("p2", "k2")
        assert s.get_enqueue_count("p1") == 1
    def test_empty(self):
        assert PipelineDataEnqueuer().get_enqueue_count() == 0
class TestStats:
    def test_data(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.enqueue("p2", "k2")
        assert s.get_stats()["total_enqueues"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataEnqueuer(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.enqueue("p1", "k1")
        assert "enqueued" in calls
    def test_remove_true(self):
        s = PipelineDataEnqueuer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataEnqueuer().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineDataEnqueuer(); s.MAX_ENTRIES = 5
        for i in range(8): s.enqueue("p1", f"k{i}")
        assert s.get_enqueue_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.reset()
        assert s.get_enqueue_count() == 0
    def test_seq(self):
        s = PipelineDataEnqueuer(); s.enqueue("p1", "k1"); s.reset()
        assert s._state._seq == 0
