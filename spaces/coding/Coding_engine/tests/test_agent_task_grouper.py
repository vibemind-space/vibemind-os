"""Tests for AgentTaskGrouper service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_grouper import AgentTaskGrouper


class TestGroupBasic:
    """Basic group and retrieval."""

    def test_group_returns_id(self):
        svc = AgentTaskGrouper()
        gid = svc.group(["t1", "t2"], "a1", group_name="grp")
        assert gid.startswith("atgr-")
        assert len(gid) > 5

    def test_group_empty_task_ids_returns_empty(self):
        svc = AgentTaskGrouper()
        assert svc.group([], "a1", group_name="grp") == ""

    def test_group_empty_agent_id_returns_empty(self):
        svc = AgentTaskGrouper()
        assert svc.group(["t1"], "", group_name="grp") == ""

    def test_get_group_existing(self):
        svc = AgentTaskGrouper()
        gid = svc.group(["t1", "t2"], "a1", group_name="batch")
        entry = svc.get_group(gid)
        assert entry is not None
        assert entry["task_ids"] == ["t1", "t2"]
        assert entry["agent_id"] == "a1"
        assert entry["group_name"] == "batch"

    def test_get_group_nonexistent(self):
        svc = AgentTaskGrouper()
        assert svc.get_group("atgr-nonexistent") is None

    def test_default_group_name_is_empty(self):
        svc = AgentTaskGrouper()
        gid = svc.group(["t1"], "a1")
        entry = svc.get_group(gid)
        assert entry["group_name"] == ""

    def test_group_returns_copy(self):
        svc = AgentTaskGrouper()
        gid = svc.group(["t1"], "a1", group_name="grp")
        entry = svc.get_group(gid)
        entry["group_name"] = "mutated"
        original = svc.get_group(gid)
        assert original["group_name"] == "grp"

    def test_task_ids_are_copied(self):
        svc = AgentTaskGrouper()
        ids = ["t1", "t2"]
        gid = svc.group(ids, "a1")
        ids.append("t3")
        entry = svc.get_group(gid)
        assert entry["task_ids"] == ["t1", "t2"]


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskGrouper()
        gid = svc.group(["t1"], "a1", metadata={"key": "val"})
        entry = svc.get_group(gid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskGrouper()
        gid = svc.group(["t1"], "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_group(gid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskGrouper()
        gid = svc.group(["t1"], "a1")
        entry = svc.get_group(gid)
        assert entry["metadata"] == {}


class TestGetGroups:
    """Querying multiple groups."""

    def test_get_groups_all(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1")
        svc.group(["t2"], "a2")
        results = svc.get_groups()
        assert len(results) == 2

    def test_get_groups_filter_by_agent(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1")
        svc.group(["t2"], "a2")
        svc.group(["t3"], "a1")
        results = svc.get_groups(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_groups_filter_by_group_name(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1", group_name="alpha")
        svc.group(["t2"], "a1", group_name="beta")
        svc.group(["t3"], "a2", group_name="alpha")
        results = svc.get_groups(group_name="alpha")
        assert len(results) == 2
        assert all(r["group_name"] == "alpha" for r in results)

    def test_get_groups_filter_by_agent_and_group_name(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1", group_name="alpha")
        svc.group(["t2"], "a1", group_name="beta")
        svc.group(["t3"], "a2", group_name="alpha")
        results = svc.get_groups(agent_id="a1", group_name="alpha")
        assert len(results) == 1
        assert results[0]["agent_id"] == "a1"
        assert results[0]["group_name"] == "alpha"

    def test_get_groups_newest_first(self):
        svc = AgentTaskGrouper()
        id1 = svc.group(["t1"], "a1")
        id2 = svc.group(["t2"], "a1")
        results = svc.get_groups()
        assert results[0]["group_id"] == id2
        assert results[1]["group_id"] == id1

    def test_get_groups_respects_limit(self):
        svc = AgentTaskGrouper()
        for i in range(10):
            svc.group([f"t{i}"], "a1")
        results = svc.get_groups(limit=3)
        assert len(results) == 3

    def test_get_groups_empty_result(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1")
        results = svc.get_groups(agent_id="a_nonexistent")
        assert results == []

    def test_get_groups_newest_first_tiebreak(self):
        svc = AgentTaskGrouper()
        id1 = svc.group(["t1"], "a1")
        id2 = svc.group(["t2"], "a1")
        id3 = svc.group(["t3"], "a1")
        results = svc.get_groups()
        assert results[0]["group_id"] == id3
        assert results[2]["group_id"] == id1


class TestGetGroupCount:
    """Counting groups."""

    def test_count_all(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1")
        svc.group(["t2"], "a2")
        assert svc.get_group_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1")
        svc.group(["t2"], "a2")
        svc.group(["t3"], "a1")
        assert svc.get_group_count(agent_id="a1") == 2
        assert svc.get_group_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskGrouper()
        assert svc.get_group_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskGrouper()
        stats = svc.get_stats()
        assert stats["total_groups"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_tasks"] == 0
        assert stats["unique_group_names"] == 0

    def test_stats_populated(self):
        svc = AgentTaskGrouper()
        svc.group(["t1", "t2"], "a1", group_name="alpha")
        svc.group(["t2", "t3"], "a2", group_name="beta")
        svc.group(["t1"], "a2", group_name="alpha")
        stats = svc.get_stats()
        assert stats["total_groups"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_tasks"] == 3
        assert stats["unique_group_names"] == 2

    def test_stats_unique_tasks_across_groups(self):
        svc = AgentTaskGrouper()
        svc.group(["t1", "t2"], "a1")
        svc.group(["t1", "t2"], "a1")
        stats = svc.get_stats()
        assert stats["unique_tasks"] == 2

    def test_stats_empty_group_name_not_counted(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1")
        svc.group(["t2"], "a1", group_name="alpha")
        stats = svc.get_stats()
        assert stats["unique_group_names"] == 1


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskGrouper()
        svc.group(["t1"], "a1")
        svc.reset()
        assert svc.get_group_count() == 0
        assert svc.get_stats()["total_groups"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskGrouper()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_group(self):
        events = []
        svc = AgentTaskGrouper()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.group(["t1"], "a1")
        assert len(events) == 1
        assert events[0][0] == "grouped"

    def test_on_change_getter(self):
        svc = AgentTaskGrouper()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback_existing(self):
        svc = AgentTaskGrouper()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskGrouper()
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskGrouper()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        gid = svc.group(["t1"], "a1")
        assert gid.startswith("atgr-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskGrouper()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.group(["t1"], "a1")
        assert "grouped" in events

    def test_on_change_fires_before_named_callbacks(self):
        order = []
        svc = AgentTaskGrouper()
        svc.on_change = lambda a, d: order.append("on_change")
        svc._callbacks["cb1"] = lambda a, d: order.append("cb1")
        svc.group(["t1"], "a1")
        assert order[0] == "on_change"
        assert order[1] == "cb1"

    def test_named_callback_exception_silenced(self):
        svc = AgentTaskGrouper()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError("fail"))
        gid = svc.group(["t1"], "a1")
        assert gid.startswith("atgr-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentTaskGrouper()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.group([f"t{i}"], "a1"))
        # Oldest quarter (2 entries) should have been evicted
        assert svc.get_group(ids[0]) is None
        assert svc.get_group(ids[1]) is None
        assert svc.get_group_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentTaskGrouper()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.group([f"t{i}"], "a1"))
        last_id = ids[-1]
        assert svc.get_group(last_id) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskGrouper()
        ids = set()
        for i in range(50):
            ids.add(svc.group([f"t{i}"], "a1"))
        assert len(ids) == 50

    def test_ids_have_correct_prefix(self):
        svc = AgentTaskGrouper()
        for i in range(5):
            gid = svc.group([f"t{i}"], "a1")
            assert gid.startswith("atgr-")
