"""Tests for AgentTaskMerger service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_merger import AgentTaskMerger


class TestMergeBasic:
    """Basic merge and retrieval."""

    def test_merge_returns_id(self):
        svc = AgentTaskMerger()
        mid = svc.merge(["t1", "t2"], "a1")
        assert mid.startswith("atmg-")
        assert len(mid) > 5

    def test_merge_empty_task_ids_returns_empty(self):
        svc = AgentTaskMerger()
        assert svc.merge([], "a1") == ""

    def test_merge_empty_agent_id_returns_empty(self):
        svc = AgentTaskMerger()
        assert svc.merge(["t1"], "") == ""

    def test_get_merge_existing(self):
        svc = AgentTaskMerger()
        mid = svc.merge(["t1", "t2"], "a1", label="combo")
        entry = svc.get_merge(mid)
        assert entry is not None
        assert entry["task_ids"] == ["t1", "t2"]
        assert entry["agent_id"] == "a1"
        assert entry["label"] == "combo"

    def test_get_merge_nonexistent(self):
        svc = AgentTaskMerger()
        assert svc.get_merge("atmg-nonexistent") is None

    def test_default_label_is_empty(self):
        svc = AgentTaskMerger()
        mid = svc.merge(["t1"], "a1")
        entry = svc.get_merge(mid)
        assert entry["label"] == ""

    def test_merge_returns_copy(self):
        svc = AgentTaskMerger()
        mid = svc.merge(["t1"], "a1")
        entry = svc.get_merge(mid)
        entry["label"] = "mutated"
        original = svc.get_merge(mid)
        assert original["label"] == ""

    def test_task_ids_are_copied(self):
        svc = AgentTaskMerger()
        ids = ["t1", "t2"]
        mid = svc.merge(ids, "a1")
        ids.append("t3")
        entry = svc.get_merge(mid)
        assert entry["task_ids"] == ["t1", "t2"]


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskMerger()
        mid = svc.merge(["t1"], "a1", metadata={"key": "val"})
        entry = svc.get_merge(mid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskMerger()
        mid = svc.merge(["t1"], "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_merge(mid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskMerger()
        mid = svc.merge(["t1"], "a1")
        entry = svc.get_merge(mid)
        assert entry["metadata"] == {}


class TestGetMerges:
    """Querying multiple merges."""

    def test_get_merges_all(self):
        svc = AgentTaskMerger()
        svc.merge(["t1"], "a1")
        svc.merge(["t2"], "a2")
        results = svc.get_merges()
        assert len(results) == 2

    def test_get_merges_filter_by_agent(self):
        svc = AgentTaskMerger()
        svc.merge(["t1"], "a1")
        svc.merge(["t2"], "a2")
        svc.merge(["t3"], "a1")
        results = svc.get_merges(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_merges_newest_first(self):
        svc = AgentTaskMerger()
        id1 = svc.merge(["t1"], "a1")
        id2 = svc.merge(["t2"], "a1")
        results = svc.get_merges()
        assert results[0]["merge_id"] == id2
        assert results[1]["merge_id"] == id1

    def test_get_merges_respects_limit(self):
        svc = AgentTaskMerger()
        for i in range(10):
            svc.merge([f"t{i}"], "a1")
        results = svc.get_merges(limit=3)
        assert len(results) == 3

    def test_get_merges_empty_result(self):
        svc = AgentTaskMerger()
        svc.merge(["t1"], "a1")
        results = svc.get_merges(agent_id="a_nonexistent")
        assert results == []

    def test_get_merges_newest_first_tiebreak(self):
        svc = AgentTaskMerger()
        id1 = svc.merge(["t1"], "a1")
        id2 = svc.merge(["t2"], "a1")
        id3 = svc.merge(["t3"], "a1")
        results = svc.get_merges()
        assert results[0]["merge_id"] == id3
        assert results[2]["merge_id"] == id1


class TestGetMergeCount:
    """Counting merges."""

    def test_count_all(self):
        svc = AgentTaskMerger()
        svc.merge(["t1"], "a1")
        svc.merge(["t2"], "a2")
        assert svc.get_merge_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskMerger()
        svc.merge(["t1"], "a1")
        svc.merge(["t2"], "a2")
        svc.merge(["t3"], "a1")
        assert svc.get_merge_count(agent_id="a1") == 2
        assert svc.get_merge_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskMerger()
        assert svc.get_merge_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskMerger()
        stats = svc.get_stats()
        assert stats["total_merges"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_tasks"] == 0

    def test_stats_populated(self):
        svc = AgentTaskMerger()
        svc.merge(["t1", "t2"], "a1")
        svc.merge(["t2", "t3"], "a2")
        svc.merge(["t1"], "a2")
        stats = svc.get_stats()
        assert stats["total_merges"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_tasks"] == 3

    def test_stats_unique_tasks_across_merges(self):
        svc = AgentTaskMerger()
        svc.merge(["t1", "t2"], "a1")
        svc.merge(["t1", "t2"], "a1")
        stats = svc.get_stats()
        assert stats["unique_tasks"] == 2


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskMerger()
        svc.merge(["t1"], "a1")
        svc.reset()
        assert svc.get_merge_count() == 0
        assert svc.get_stats()["total_merges"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskMerger()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_merge(self):
        events = []
        svc = AgentTaskMerger()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.merge(["t1"], "a1")
        assert len(events) == 1
        assert events[0][0] == "merged"

    def test_on_change_getter(self):
        svc = AgentTaskMerger()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback_existing(self):
        svc = AgentTaskMerger()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskMerger()
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskMerger()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        mid = svc.merge(["t1"], "a1")
        assert mid.startswith("atmg-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskMerger()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.merge(["t1"], "a1")
        assert "merged" in events

    def test_on_change_fires_before_named_callbacks(self):
        order = []
        svc = AgentTaskMerger()
        svc.on_change = lambda a, d: order.append("on_change")
        svc._callbacks["cb1"] = lambda a, d: order.append("cb1")
        svc.merge(["t1"], "a1")
        assert order[0] == "on_change"
        assert order[1] == "cb1"

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskMerger()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError("fail"))
        mid = svc.merge(["t1"], "a1")
        assert mid.startswith("atmg-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentTaskMerger()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.merge([f"t{i}"], "a1"))
        # Oldest quarter (2 entries) should have been evicted
        assert svc.get_merge(ids[0]) is None
        assert svc.get_merge(ids[1]) is None
        assert svc.get_merge_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskMerger()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.merge([f"t{i}"], "a1"))
        last_id = ids[-1]
        assert svc.get_merge(last_id) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskMerger()
        ids = set()
        for i in range(50):
            ids.add(svc.merge([f"t{i}"], "a1"))
        assert len(ids) == 50

    def test_ids_have_correct_prefix(self):
        svc = AgentTaskMerger()
        for i in range(5):
            mid = svc.merge([f"t{i}"], "a1")
            assert mid.startswith("atmg-")
