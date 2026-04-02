"""Tests for AgentTaskBatcher service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_batcher import AgentTaskBatcher


class TestBatchBasic:
    """Basic batch and retrieval."""

    def test_batch_returns_id(self):
        svc = AgentTaskBatcher()
        bid = svc.batch(["t1", "t2"], "a1", batch_size=5)
        assert bid.startswith("atbt-")
        assert len(bid) > 5

    def test_batch_empty_task_ids_returns_empty(self):
        svc = AgentTaskBatcher()
        assert svc.batch([], "a1") == ""

    def test_batch_empty_agent_id_returns_empty(self):
        svc = AgentTaskBatcher()
        assert svc.batch(["t1"], "") == ""

    def test_get_batch_existing(self):
        svc = AgentTaskBatcher()
        bid = svc.batch(["t1", "t2"], "a1", batch_size=5)
        entry = svc.get_batch(bid)
        assert entry is not None
        assert entry["task_ids"] == ["t1", "t2"]
        assert entry["agent_id"] == "a1"
        assert entry["batch_size"] == 5

    def test_get_batch_nonexistent(self):
        svc = AgentTaskBatcher()
        assert svc.get_batch("atbt-nonexistent") is None

    def test_default_batch_size(self):
        svc = AgentTaskBatcher()
        bid = svc.batch(["t1"], "a1")
        entry = svc.get_batch(bid)
        assert entry["batch_size"] == 10

    def test_batch_returns_copy(self):
        svc = AgentTaskBatcher()
        bid = svc.batch(["t1"], "a1", batch_size=5)
        entry = svc.get_batch(bid)
        entry["batch_size"] = 999
        original = svc.get_batch(bid)
        assert original["batch_size"] == 5

    def test_task_ids_are_copied(self):
        svc = AgentTaskBatcher()
        ids = ["t1", "t2"]
        bid = svc.batch(ids, "a1")
        ids.append("t3")
        entry = svc.get_batch(bid)
        assert entry["task_ids"] == ["t1", "t2"]


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskBatcher()
        bid = svc.batch(["t1"], "a1", metadata={"key": "val"})
        entry = svc.get_batch(bid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskBatcher()
        bid = svc.batch(["t1"], "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_batch(bid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskBatcher()
        bid = svc.batch(["t1"], "a1")
        entry = svc.get_batch(bid)
        assert entry["metadata"] == {}


class TestGetBatches:
    """Querying multiple batches."""

    def test_get_batches_all(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1"], "a1")
        svc.batch(["t2"], "a2")
        results = svc.get_batches()
        assert len(results) == 2

    def test_get_batches_filter_by_agent(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1"], "a1")
        svc.batch(["t2"], "a2")
        svc.batch(["t3"], "a1")
        results = svc.get_batches(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_batches_newest_first(self):
        svc = AgentTaskBatcher()
        id1 = svc.batch(["t1"], "a1")
        id2 = svc.batch(["t2"], "a1")
        results = svc.get_batches()
        assert results[0]["batch_id"] == id2
        assert results[1]["batch_id"] == id1

    def test_get_batches_respects_limit(self):
        svc = AgentTaskBatcher()
        for i in range(10):
            svc.batch([f"t{i}"], "a1")
        results = svc.get_batches(limit=3)
        assert len(results) == 3

    def test_get_batches_empty_result(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1"], "a1")
        results = svc.get_batches(agent_id="a_nonexistent")
        assert results == []

    def test_get_batches_newest_first_tiebreak(self):
        svc = AgentTaskBatcher()
        id1 = svc.batch(["t1"], "a1")
        id2 = svc.batch(["t2"], "a1")
        id3 = svc.batch(["t3"], "a1")
        results = svc.get_batches()
        assert results[0]["batch_id"] == id3
        assert results[2]["batch_id"] == id1


class TestGetBatchCount:
    """Counting batches."""

    def test_count_all(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1"], "a1")
        svc.batch(["t2"], "a2")
        assert svc.get_batch_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1"], "a1")
        svc.batch(["t2"], "a2")
        svc.batch(["t3"], "a1")
        assert svc.get_batch_count(agent_id="a1") == 2
        assert svc.get_batch_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskBatcher()
        assert svc.get_batch_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskBatcher()
        stats = svc.get_stats()
        assert stats["total_batches"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["total_batch_size"] == 0

    def test_stats_populated(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1", "t2"], "a1", batch_size=5)
        svc.batch(["t2", "t3"], "a2", batch_size=10)
        svc.batch(["t1"], "a2", batch_size=3)
        stats = svc.get_stats()
        assert stats["total_batches"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_tasks"] == 3
        assert stats["total_batch_size"] == 18

    def test_stats_unique_tasks_across_batches(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1", "t2"], "a1")
        svc.batch(["t1", "t2"], "a1")
        stats = svc.get_stats()
        assert stats["unique_tasks"] == 2

    def test_stats_batch_size_accumulates(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1"], "a1", batch_size=7)
        svc.batch(["t2"], "a1", batch_size=3)
        stats = svc.get_stats()
        assert stats["total_batch_size"] == 10


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskBatcher()
        svc.batch(["t1"], "a1")
        svc.reset()
        assert svc.get_batch_count() == 0
        assert svc.get_stats()["total_batches"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskBatcher()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_batch(self):
        events = []
        svc = AgentTaskBatcher()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.batch(["t1"], "a1")
        assert len(events) == 1
        assert events[0][0] == "batched"

    def test_on_change_getter(self):
        svc = AgentTaskBatcher()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback_existing(self):
        svc = AgentTaskBatcher()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskBatcher()
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskBatcher()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        bid = svc.batch(["t1"], "a1")
        assert bid.startswith("atbt-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskBatcher()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.batch(["t1"], "a1")
        assert "batched" in events

    def test_on_change_fires_before_named_callbacks(self):
        order = []
        svc = AgentTaskBatcher()
        svc.on_change = lambda a, d: order.append("on_change")
        svc._callbacks["cb1"] = lambda a, d: order.append("cb1")
        svc.batch(["t1"], "a1")
        assert order[0] == "on_change"
        assert order[1] == "cb1"

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskBatcher()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError("fail"))
        bid = svc.batch(["t1"], "a1")
        assert bid.startswith("atbt-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentTaskBatcher()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.batch([f"t{i}"], "a1"))
        assert svc.get_batch(ids[0]) is None
        assert svc.get_batch(ids[1]) is None
        assert svc.get_batch_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskBatcher()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.batch([f"t{i}"], "a1"))
        last_id = ids[-1]
        assert svc.get_batch(last_id) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskBatcher()
        ids = set()
        for i in range(50):
            ids.add(svc.batch([f"t{i}"], "a1"))
        assert len(ids) == 50

    def test_ids_have_correct_prefix(self):
        svc = AgentTaskBatcher()
        for i in range(5):
            bid = svc.batch([f"t{i}"], "a1")
            assert bid.startswith("atbt-")
