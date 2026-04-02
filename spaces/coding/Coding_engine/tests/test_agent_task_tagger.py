"""Tests for AgentTaskTagger service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_tagger import AgentTaskTagger


class TestTagBasic:
    """Basic tag and retrieval."""

    def test_tag_returns_id_with_prefix(self):
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1", tag_name="urgent")
        assert rid.startswith("attg-")

    def test_tag_returns_unique_ids(self):
        s = AgentTaskTagger()
        ids = set()
        for i in range(50):
            ids.add(s.tag(f"t{i}", "a1"))
        assert len(ids) == 50

    def test_tag_stores_all_fields(self):
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1", tag_name="urgent", metadata={"p": 1})
        entry = s.get_tag(rid)
        assert entry is not None
        assert entry["record_id"] == rid
        assert entry["task_id"] == "task-1"
        assert entry["agent_id"] == "a1"
        assert entry["tag_name"] == "urgent"
        assert entry["metadata"] == {"p": 1}

    def test_tag_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = s.get_tag(rid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_tag_has_created_at(self):
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1")
        entry = s.get_tag(rid)
        assert "created_at" in entry
        assert isinstance(entry["created_at"], float)

    def test_tag_empty_task_id_returns_empty(self):
        s = AgentTaskTagger()
        assert s.tag("", "a1") == ""

    def test_tag_empty_agent_id_returns_empty(self):
        s = AgentTaskTagger()
        assert s.tag("task-1", "") == ""

    def test_tag_both_empty_returns_empty(self):
        s = AgentTaskTagger()
        assert s.tag("", "") == ""

    def test_tag_default_tag_name_empty(self):
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1")
        entry = s.get_tag(rid)
        assert entry["tag_name"] == ""

    def test_tag_default_metadata_empty_dict(self):
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1")
        entry = s.get_tag(rid)
        assert entry["metadata"] == {}


class TestGetTag:
    """get_tag retrieval."""

    def test_get_tag_found(self):
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1")
        entry = s.get_tag(rid)
        assert entry is not None
        assert entry["record_id"] == rid

    def test_get_tag_not_found(self):
        s = AgentTaskTagger()
        assert s.get_tag("attg-nonexistent") is None

    def test_get_tag_returns_copy(self):
        s = AgentTaskTagger()
        rid = s.tag("task-1", "a1", tag_name="v1")
        entry = s.get_tag(rid)
        entry["tag_name"] = "mutated"
        original = s.get_tag(rid)
        assert original["tag_name"] == "v1"


class TestGetTags:
    """get_tags querying."""

    def test_get_tags_all(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        s.tag("t2", "a2")
        results = s.get_tags()
        assert len(results) == 2

    def test_get_tags_filter_by_agent(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        s.tag("t2", "a2")
        s.tag("t3", "a1")
        results = s.get_tags(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_tags_newest_first(self):
        s = AgentTaskTagger()
        id1 = s.tag("t1", "a1")
        id2 = s.tag("t2", "a1")
        results = s.get_tags()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_tags_newest_first_three(self):
        s = AgentTaskTagger()
        id1 = s.tag("t1", "a1")
        id2 = s.tag("t2", "a1")
        id3 = s.tag("t3", "a1")
        results = s.get_tags()
        assert results[0]["record_id"] == id3
        assert results[2]["record_id"] == id1

    def test_get_tags_respects_limit(self):
        s = AgentTaskTagger()
        for i in range(10):
            s.tag(f"t{i}", "a1")
        results = s.get_tags(limit=3)
        assert len(results) == 3

    def test_get_tags_empty_when_no_match(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        results = s.get_tags(agent_id="a_nonexistent")
        assert results == []


class TestGetTagCount:
    """Counting tags."""

    def test_count_all(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        s.tag("t2", "a2")
        assert s.get_tag_count() == 2

    def test_count_by_agent(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        s.tag("t2", "a2")
        s.tag("t3", "a1")
        assert s.get_tag_count(agent_id="a1") == 2
        assert s.get_tag_count(agent_id="a2") == 1

    def test_count_empty(self):
        s = AgentTaskTagger()
        assert s.get_tag_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        s = AgentTaskTagger()
        stats = s.get_stats()
        assert stats["total_tags"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        s.tag("t2", "a2")
        s.tag("t3", "a1")
        stats = s.get_stats()
        assert stats["total_tags"] == 3
        assert stats["unique_agents"] == 2


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_tag(self):
        events = []
        s = AgentTaskTagger()
        s.on_change = lambda action, data: events.append((action, data))
        s.tag("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "tagged"

    def test_on_change_getter(self):
        s = AgentTaskTagger()
        assert s.on_change is None
        fn = lambda a, d: None
        s.on_change = fn
        assert s.on_change is fn

    def test_named_callbacks_fire(self):
        events = []
        s = AgentTaskTagger()
        s._state.callbacks["my_cb"] = lambda action, data: events.append(action)
        s.tag("t1", "a1")
        assert "tagged" in events

    def test_on_change_fires_before_named_callbacks(self):
        order = []
        s = AgentTaskTagger()
        s.on_change = lambda a, d: order.append("on_change")
        s._state.callbacks["cb1"] = lambda a, d: order.append("cb1")
        s.tag("t1", "a1")
        assert order[0] == "on_change"
        assert order[1] == "cb1"

    def test_remove_callback_existing(self):
        s = AgentTaskTagger()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_callback_nonexistent(self):
        s = AgentTaskTagger()
        assert s.remove_callback("cb1") is False

    def test_on_change_exception_silenced(self):
        s = AgentTaskTagger()
        s.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = s.tag("t1", "a1")
        assert rid.startswith("attg-")

    def test_named_callback_exception_silenced(self):
        s = AgentTaskTagger()
        s._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError("fail"))
        rid = s.tag("t1", "a1")
        assert rid.startswith("attg-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        s = AgentTaskTagger()
        s.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(s.tag(f"t{i}", "a1"))
        # Oldest quarter (2 entries) should have been evicted
        assert s.get_tag(ids[0]) is None
        assert s.get_tag(ids[1]) is None
        assert s.get_tag_count() <= 8

    def test_prune_keeps_newest(self):
        s = AgentTaskTagger()
        s.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(s.tag(f"t{i}", "a1"))
        last_id = ids[-1]
        assert s.get_tag(last_id) is not None

    def test_prune_under_limit_no_eviction(self):
        s = AgentTaskTagger()
        s.MAX_ENTRIES = 8
        ids = []
        for i in range(7):
            ids.append(s.tag(f"t{i}", "a1"))
        # All should still exist (under limit)
        for rid in ids:
            assert s.get_tag(rid) is not None


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        s.reset()
        assert s.get_tag_count() == 0
        assert s.get_stats()["total_tags"] == 0

    def test_reset_clears_callbacks(self):
        s = AgentTaskTagger()
        s._state.callbacks["cb1"] = lambda a, d: None
        s.on_change = lambda a, d: None
        s.reset()
        assert len(s._state.callbacks) == 0
        assert s.on_change is None

    def test_reset_clears_seq(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        old_seq = s._state._seq
        assert old_seq > 0
        s.reset()
        assert s._state._seq == 0

    def test_reset_allows_new_entries(self):
        s = AgentTaskTagger()
        s.tag("t1", "a1")
        s.reset()
        rid = s.tag("t2", "a2")
        assert rid.startswith("attg-")
        assert s.get_tag_count() == 1


class TestUniqueIds:
    """IDs are unique and properly prefixed."""

    def test_ids_have_correct_prefix(self):
        s = AgentTaskTagger()
        for i in range(5):
            rid = s.tag(f"t{i}", "a1")
            assert rid.startswith("attg-")

    def test_many_ids_unique(self):
        s = AgentTaskTagger()
        ids = set()
        for i in range(100):
            ids.add(s.tag(f"t{i}", "a1"))
        assert len(ids) == 100
