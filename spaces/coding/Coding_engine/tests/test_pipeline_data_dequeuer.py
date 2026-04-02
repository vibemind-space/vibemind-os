import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_dequeuer import PipelineDataDequeuer

class TestBasic:
    def test_returns_id(self):
        assert PipelineDataDequeuer().dequeue("p1", "k1").startswith("pddq-")
    def test_fields(self):
        s = PipelineDataDequeuer(); rid = s.dequeue("p1", "k1", queue_name="high")
        e = s.get_dequeue(rid)
        assert e["pipeline_id"] == "p1" and e["data_key"] == "k1" and e["queue_name"] == "high"
    def test_default_queue(self):
        s = PipelineDataDequeuer(); rid = s.dequeue("p1", "k1")
        assert s.get_dequeue(rid)["queue_name"] == "default"
    def test_metadata_deepcopy(self):
        s = PipelineDataDequeuer(); m = {"x": [1]}
        rid = s.dequeue("p1", "k1", metadata=m); m["x"].append(2)
        assert s.get_dequeue(rid)["metadata"] == {"x": [1]}
    def test_empty_pipeline(self):
        assert PipelineDataDequeuer().dequeue("", "k1") == ""
    def test_empty_key(self):
        assert PipelineDataDequeuer().dequeue("p1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineDataDequeuer(); rid = s.dequeue("p1", "k1")
        assert s.get_dequeue(rid) is not None
    def test_not_found(self):
        assert PipelineDataDequeuer().get_dequeue("nope") is None
    def test_copy(self):
        s = PipelineDataDequeuer(); rid = s.dequeue("p1", "k1")
        assert s.get_dequeue(rid) is not s.get_dequeue(rid)
class TestList:
    def test_all(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.dequeue("p2", "k2")
        assert len(s.get_dequeues()) == 2
    def test_filter(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.dequeue("p2", "k2")
        assert len(s.get_dequeues("p1")) == 1
    def test_newest_first(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.dequeue("p1", "k2")
        assert s.get_dequeues("p1")[0]["_seq"] > s.get_dequeues("p1")[1]["_seq"]
    def test_limit(self):
        s = PipelineDataDequeuer()
        for i in range(5): s.dequeue("p1", f"k{i}")
        assert len(s.get_dequeues(limit=3)) == 3
class TestCount:
    def test_total(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.dequeue("p2", "k2")
        assert s.get_dequeue_count() == 2
    def test_filtered(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.dequeue("p2", "k2")
        assert s.get_dequeue_count("p1") == 1
    def test_empty(self):
        assert PipelineDataDequeuer().get_dequeue_count() == 0
class TestStats:
    def test_empty(self):
        assert PipelineDataDequeuer().get_stats()["total_dequeues"] == 0
    def test_data(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.dequeue("p2", "k2")
        assert s.get_stats()["total_dequeues"] == 2 and s.get_stats()["unique_pipelines"] == 2
class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataDequeuer(); calls = []
        s.on_change = lambda a, d: calls.append(a); s.dequeue("p1", "k1")
        assert "dequeued" in calls
    def test_remove_true(self):
        s = PipelineDataDequeuer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineDataDequeuer().remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineDataDequeuer(); s.MAX_ENTRIES = 5
        for i in range(8): s.dequeue("p1", f"k{i}")
        assert s.get_dequeue_count() < 8
class TestReset:
    def test_clears(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.reset()
        assert s.get_dequeue_count() == 0
    def test_callbacks(self):
        s = PipelineDataDequeuer(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataDequeuer(); s.dequeue("p1", "k1"); s.reset()
        assert s._state._seq == 0
