"""Tests for AgentTaskForker service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_forker import AgentTaskForker


class TestForkBasic:
    """Basic fork and retrieval."""

    def test_fork_returns_id(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1", fork_count=3)
        assert fid.startswith("atfk-")
        assert len(fid) > 5

    def test_fork_empty_task_id_returns_empty(self):
        svc = AgentTaskForker()
        assert svc.fork("", "a1") == ""

    def test_fork_empty_agent_id_returns_empty(self):
        svc = AgentTaskForker()
        assert svc.fork("task-1", "") == ""

    def test_fork_zero_fork_count_returns_empty(self):
        svc = AgentTaskForker()
        assert svc.fork("task-1", "a1", fork_count=0) == ""

    def test_fork_negative_fork_count_returns_empty(self):
        svc = AgentTaskForker()
        assert svc.fork("task-1", "a1", fork_count=-1) == ""

    def test_get_fork_existing(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1", fork_count=3, strategy="clone")
        entry = svc.get_fork(fid)
        assert entry is not None
        assert entry["task_id"] == "task-1"
        assert entry["agent_id"] == "a1"
        assert entry["fork_count"] == 3
        assert entry["strategy"] == "clone"

    def test_get_fork_nonexistent(self):
        svc = AgentTaskForker()
        assert svc.get_fork("atfk-nonexistent") is None

    def test_default_strategy_is_clone(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1")
        entry = svc.get_fork(fid)
        assert entry["strategy"] == "clone"

    def test_default_fork_count_is_two(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1")
        entry = svc.get_fork(fid)
        assert entry["fork_count"] == 2

    def test_fork_returns_copy(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1")
        entry = svc.get_fork(fid)
        entry["strategy"] = "mutated"
        original = svc.get_fork(fid)
        assert original["strategy"] == "clone"

    def test_subtask_ids_generated(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1", fork_count=3)
        entry = svc.get_fork(fid)
        assert len(entry["subtask_ids"]) == 3
        for sub_id in entry["subtask_ids"]:
            assert sub_id.startswith(fid)

    def test_custom_strategy(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1", strategy="round_robin")
        entry = svc.get_fork(fid)
        assert entry["strategy"] == "round_robin"


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1", metadata={"key": "val"})
        entry = svc.get_fork(fid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_fork(fid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskForker()
        fid = svc.fork("task-1", "a1")
        entry = svc.get_fork(fid)
        assert entry["metadata"] == {}


class TestGetForks:
    """Querying multiple forks."""

    def test_get_forks_all(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        svc.fork("t2", "a2")
        results = svc.get_forks()
        assert len(results) == 2

    def test_get_forks_filter_by_agent(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        svc.fork("t2", "a2")
        svc.fork("t3", "a1")
        results = svc.get_forks(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_forks_newest_first(self):
        svc = AgentTaskForker()
        id1 = svc.fork("t1", "a1")
        id2 = svc.fork("t2", "a1")
        results = svc.get_forks()
        assert results[0]["fork_id"] == id2
        assert results[1]["fork_id"] == id1

    def test_get_forks_respects_limit(self):
        svc = AgentTaskForker()
        for i in range(10):
            svc.fork(f"t{i}", "a1")
        results = svc.get_forks(limit=3)
        assert len(results) == 3

    def test_get_forks_empty_result(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        results = svc.get_forks(agent_id="a_nonexistent")
        assert results == []

    def test_get_forks_newest_first_tiebreak(self):
        svc = AgentTaskForker()
        id1 = svc.fork("t1", "a1")
        id2 = svc.fork("t2", "a1")
        id3 = svc.fork("t3", "a1")
        results = svc.get_forks()
        assert results[0]["fork_id"] == id3
        assert results[2]["fork_id"] == id1


class TestGetForkCount:
    """Counting forks."""

    def test_count_all(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        svc.fork("t2", "a2")
        assert svc.get_fork_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        svc.fork("t2", "a2")
        svc.fork("t3", "a1")
        assert svc.get_fork_count(agent_id="a1") == 2
        assert svc.get_fork_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskForker()
        assert svc.get_fork_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskForker()
        stats = svc.get_stats()
        assert stats["total_forks"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["total_subtasks"] == 0
        assert stats["strategies"] == 0

    def test_stats_populated(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1", fork_count=3)
        svc.fork("t2", "a2", fork_count=2, strategy="round_robin")
        svc.fork("t1", "a2", fork_count=4)
        stats = svc.get_stats()
        assert stats["total_forks"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_tasks"] == 2
        assert stats["total_subtasks"] == 9
        assert stats["strategies"] == 2

    def test_stats_unique_tasks_across_forks(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        svc.fork("t1", "a1")
        stats = svc.get_stats()
        assert stats["unique_tasks"] == 1


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        svc.reset()
        assert svc.get_fork_count() == 0
        assert svc.get_stats()["total_forks"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskForker()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None

    def test_reset_allows_new_entries(self):
        svc = AgentTaskForker()
        svc.fork("t1", "a1")
        svc.reset()
        fid = svc.fork("t2", "a2")
        assert fid.startswith("atfk-")
        assert svc.get_fork_count() == 1


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_fork(self):
        events = []
        svc = AgentTaskForker()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.fork("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "fork"

    def test_on_change_getter(self):
        svc = AgentTaskForker()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback_existing(self):
        svc = AgentTaskForker()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskForker()
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskForker()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        fid = svc.fork("t1", "a1")
        assert fid.startswith("atfk-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskForker()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.fork("t1", "a1")
        assert "fork" in events

    def test_on_change_fires_before_named_callbacks(self):
        order = []
        svc = AgentTaskForker()
        svc.on_change = lambda a, d: order.append("on_change")
        svc._callbacks["cb1"] = lambda a, d: order.append("cb1")
        svc.fork("t1", "a1")
        assert order[0] == "on_change"
        assert order[1] == "cb1"

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskForker()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError("fail"))
        fid = svc.fork("t1", "a1")
        assert fid.startswith("atfk-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentTaskForker()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.fork(f"t{i}", "a1"))
        # Oldest quarter (2 entries) should have been evicted
        assert svc.get_fork(ids[0]) is None
        assert svc.get_fork(ids[1]) is None
        assert svc.get_fork_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskForker()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.fork(f"t{i}", "a1"))
        last_id = ids[-1]
        assert svc.get_fork(last_id) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskForker()
        ids = set()
        for i in range(50):
            ids.add(svc.fork(f"t{i}", "a1"))
        assert len(ids) == 50

    def test_ids_have_correct_prefix(self):
        svc = AgentTaskForker()
        for i in range(5):
            fid = svc.fork(f"t{i}", "a1")
            assert fid.startswith("atfk-")
