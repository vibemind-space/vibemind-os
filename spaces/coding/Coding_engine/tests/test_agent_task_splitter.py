"""Tests for AgentTaskSplitter service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_splitter import AgentTaskSplitter


class TestSplitBasic:
    """Basic split and retrieval."""

    def test_split_returns_id(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1", subtask_count=3)
        assert sid.startswith("atsp-")
        assert len(sid) > 5

    def test_split_empty_task_id_returns_empty(self):
        svc = AgentTaskSplitter()
        assert svc.split("", "a1") == ""

    def test_split_empty_agent_id_returns_empty(self):
        svc = AgentTaskSplitter()
        assert svc.split("task-1", "") == ""

    def test_split_zero_subtask_count_returns_empty(self):
        svc = AgentTaskSplitter()
        assert svc.split("task-1", "a1", subtask_count=0) == ""

    def test_split_negative_subtask_count_returns_empty(self):
        svc = AgentTaskSplitter()
        assert svc.split("task-1", "a1", subtask_count=-1) == ""

    def test_get_split_existing(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1", subtask_count=3, strategy="equal")
        entry = svc.get_split(sid)
        assert entry is not None
        assert entry["task_id"] == "task-1"
        assert entry["agent_id"] == "a1"
        assert entry["subtask_count"] == 3
        assert entry["strategy"] == "equal"

    def test_get_split_nonexistent(self):
        svc = AgentTaskSplitter()
        assert svc.get_split("atsp-nonexistent") is None

    def test_default_strategy_is_equal(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1")
        entry = svc.get_split(sid)
        assert entry["strategy"] == "equal"

    def test_default_subtask_count_is_two(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1")
        entry = svc.get_split(sid)
        assert entry["subtask_count"] == 2

    def test_split_returns_copy(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1")
        entry = svc.get_split(sid)
        entry["strategy"] = "mutated"
        original = svc.get_split(sid)
        assert original["strategy"] == "equal"

    def test_subtask_ids_generated(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1", subtask_count=3)
        entry = svc.get_split(sid)
        assert len(entry["subtask_ids"]) == 3
        for sub_id in entry["subtask_ids"]:
            assert sub_id.startswith(sid)

    def test_custom_strategy(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1", strategy="weighted")
        entry = svc.get_split(sid)
        assert entry["strategy"] == "weighted"


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1", metadata={"key": "val"})
        entry = svc.get_split(sid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_split(sid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskSplitter()
        sid = svc.split("task-1", "a1")
        entry = svc.get_split(sid)
        assert entry["metadata"] == {}


class TestGetSplits:
    """Querying multiple splits."""

    def test_get_splits_all(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        svc.split("t2", "a2")
        results = svc.get_splits()
        assert len(results) == 2

    def test_get_splits_filter_by_agent(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        svc.split("t2", "a2")
        svc.split("t3", "a1")
        results = svc.get_splits(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_splits_newest_first(self):
        svc = AgentTaskSplitter()
        id1 = svc.split("t1", "a1")
        id2 = svc.split("t2", "a1")
        results = svc.get_splits()
        assert results[0]["split_id"] == id2
        assert results[1]["split_id"] == id1

    def test_get_splits_respects_limit(self):
        svc = AgentTaskSplitter()
        for i in range(10):
            svc.split(f"t{i}", "a1")
        results = svc.get_splits(limit=3)
        assert len(results) == 3

    def test_get_splits_empty_result(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        results = svc.get_splits(agent_id="a_nonexistent")
        assert results == []

    def test_get_splits_newest_first_tiebreak(self):
        svc = AgentTaskSplitter()
        id1 = svc.split("t1", "a1")
        id2 = svc.split("t2", "a1")
        id3 = svc.split("t3", "a1")
        results = svc.get_splits()
        assert results[0]["split_id"] == id3
        assert results[2]["split_id"] == id1


class TestGetSplitCount:
    """Counting splits."""

    def test_count_all(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        svc.split("t2", "a2")
        assert svc.get_split_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        svc.split("t2", "a2")
        svc.split("t3", "a1")
        assert svc.get_split_count(agent_id="a1") == 2
        assert svc.get_split_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskSplitter()
        assert svc.get_split_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskSplitter()
        stats = svc.get_stats()
        assert stats["total_splits"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["total_subtasks"] == 0
        assert stats["strategies"] == 0

    def test_stats_populated(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1", subtask_count=3)
        svc.split("t2", "a2", subtask_count=2, strategy="weighted")
        svc.split("t1", "a2", subtask_count=4)
        stats = svc.get_stats()
        assert stats["total_splits"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_tasks"] == 2
        assert stats["total_subtasks"] == 9
        assert stats["strategies"] == 2

    def test_stats_unique_tasks_across_splits(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        svc.split("t1", "a1")
        stats = svc.get_stats()
        assert stats["unique_tasks"] == 1


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        svc.reset()
        assert svc.get_split_count() == 0
        assert svc.get_stats()["total_splits"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskSplitter()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None

    def test_reset_allows_new_entries(self):
        svc = AgentTaskSplitter()
        svc.split("t1", "a1")
        svc.reset()
        sid = svc.split("t2", "a2")
        assert sid.startswith("atsp-")
        assert svc.get_split_count() == 1


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_split(self):
        events = []
        svc = AgentTaskSplitter()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.split("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "split"

    def test_on_change_getter(self):
        svc = AgentTaskSplitter()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback_existing(self):
        svc = AgentTaskSplitter()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskSplitter()
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskSplitter()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        sid = svc.split("t1", "a1")
        assert sid.startswith("atsp-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskSplitter()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.split("t1", "a1")
        assert "split" in events

    def test_on_change_fires_before_named_callbacks(self):
        order = []
        svc = AgentTaskSplitter()
        svc.on_change = lambda a, d: order.append("on_change")
        svc._callbacks["cb1"] = lambda a, d: order.append("cb1")
        svc.split("t1", "a1")
        assert order[0] == "on_change"
        assert order[1] == "cb1"

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskSplitter()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError("fail"))
        sid = svc.split("t1", "a1")
        assert sid.startswith("atsp-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentTaskSplitter()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.split(f"t{i}", "a1"))
        # Oldest quarter (2 entries) should have been evicted
        assert svc.get_split(ids[0]) is None
        assert svc.get_split(ids[1]) is None
        assert svc.get_split_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskSplitter()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.split(f"t{i}", "a1"))
        last_id = ids[-1]
        assert svc.get_split(last_id) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskSplitter()
        ids = set()
        for i in range(50):
            ids.add(svc.split(f"t{i}", "a1"))
        assert len(ids) == 50

    def test_ids_have_correct_prefix(self):
        svc = AgentTaskSplitter()
        for i in range(5):
            sid = svc.split(f"t{i}", "a1")
            assert sid.startswith("atsp-")
