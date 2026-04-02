"""Tests for AgentTaskNotifier service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_notifier import AgentTaskNotifier, AgentTaskNotifierState


class TestNotifyBasic:
    """Basic notification creation."""

    def test_notify_returns_id(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("task-1", "agent-1", "started")
        assert nid.startswith("atnf-")
        assert len(nid) > 5

    def test_notify_with_message(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("task-1", "agent-1", "started", message="hello")
        entry = svc.get_notification(nid)
        assert entry is not None
        assert entry["message"] == "hello"

    def test_notify_with_metadata(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("task-1", "agent-1", "started", metadata={"k": "v"})
        entry = svc.get_notification(nid)
        assert entry["metadata"] == {"k": "v"}

    def test_notify_empty_task_id_returns_empty(self):
        svc = AgentTaskNotifier()
        assert svc.notify("", "agent-1", "started") == ""

    def test_notify_empty_agent_id_returns_empty(self):
        svc = AgentTaskNotifier()
        assert svc.notify("task-1", "", "started") == ""

    def test_notify_empty_event_type_returns_empty(self):
        svc = AgentTaskNotifier()
        assert svc.notify("task-1", "agent-1", "") == ""

    def test_notify_default_message_is_empty(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("task-1", "agent-1", "started")
        entry = svc.get_notification(nid)
        assert entry["message"] == ""

    def test_notify_default_metadata_is_empty_dict(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("task-1", "agent-1", "started")
        entry = svc.get_notification(nid)
        assert entry["metadata"] == {}


class TestGetNotification:
    """Single notification retrieval."""

    def test_get_existing(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("task-1", "agent-1", "started")
        entry = svc.get_notification(nid)
        assert entry is not None
        assert entry["notification_id"] == nid
        assert entry["task_id"] == "task-1"
        assert entry["agent_id"] == "agent-1"
        assert entry["event_type"] == "started"

    def test_get_nonexistent(self):
        svc = AgentTaskNotifier()
        assert svc.get_notification("atnf-doesnotexist") is None

    def test_get_returns_copy(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("task-1", "agent-1", "started", message="orig")
        entry = svc.get_notification(nid)
        entry["message"] = "mutated"
        original = svc.get_notification(nid)
        assert original["message"] == "orig"


class TestGetNotifications:
    """Filtered listing of notifications."""

    def test_filter_by_agent(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "agent-1", "started")
        svc.notify("t2", "agent-2", "started")
        svc.notify("t3", "agent-1", "completed")
        results = svc.get_notifications(agent_id="agent-1")
        assert len(results) == 2
        assert all(r["agent_id"] == "agent-1" for r in results)

    def test_filter_by_event_type(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.notify("t2", "a2", "completed")
        svc.notify("t3", "a1", "started")
        results = svc.get_notifications(event_type="started")
        assert len(results) == 2
        assert all(r["event_type"] == "started" for r in results)

    def test_filter_by_agent_and_event_type(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.notify("t2", "a1", "completed")
        svc.notify("t3", "a2", "started")
        results = svc.get_notifications(agent_id="a1", event_type="started")
        assert len(results) == 1
        assert results[0]["agent_id"] == "a1"
        assert results[0]["event_type"] == "started"

    def test_no_filters_returns_all(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.notify("t2", "a2", "completed")
        results = svc.get_notifications()
        assert len(results) == 2

    def test_limit(self):
        svc = AgentTaskNotifier()
        for i in range(10):
            svc.notify(f"t{i}", "a1", "started")
        results = svc.get_notifications(limit=3)
        assert len(results) == 3

    def test_sorted_newest_first(self):
        svc = AgentTaskNotifier()
        n1 = svc.notify("t1", "a1", "started")
        n2 = svc.notify("t2", "a1", "completed")
        n3 = svc.notify("t3", "a1", "failed")
        results = svc.get_notifications()
        assert results[0]["notification_id"] == n3
        assert results[2]["notification_id"] == n1

    def test_returns_copies(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started", message="orig")
        results = svc.get_notifications()
        results[0]["message"] = "mutated"
        fresh = svc.get_notifications()
        assert fresh[0]["message"] == "orig"


class TestGetNotificationCount:
    """Counting notifications."""

    def test_count_all(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.notify("t2", "a2", "started")
        assert svc.get_notification_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.notify("t2", "a2", "started")
        svc.notify("t3", "a1", "completed")
        assert svc.get_notification_count(agent_id="a1") == 2
        assert svc.get_notification_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskNotifier()
        assert svc.get_notification_count() == 0

    def test_count_nonexistent_agent(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        assert svc.get_notification_count(agent_id="a99") == 0


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_deep_copied_on_store(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskNotifier()
        nid = svc.notify("t1", "a1", "started", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_notification(nid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_none_becomes_empty_dict(self):
        svc = AgentTaskNotifier()
        nid = svc.notify("t1", "a1", "started", metadata=None)
        entry = svc.get_notification(nid)
        assert entry["metadata"] == {}


class TestCallbacks:
    """Callback registration and firing."""

    def test_on_change_property_set_and_get(self):
        svc = AgentTaskNotifier()
        calls = []
        svc.on_change = ("cb1", lambda e, d: calls.append((e, d)))
        assert "cb1" in svc.on_change

    def test_on_change_method(self):
        svc = AgentTaskNotifier()
        calls = []
        svc._on_change("cb1", lambda e, d: calls.append((e, d)))
        svc.notify("t1", "a1", "started")
        assert len(calls) == 1
        assert calls[0][0] == "notification_created"

    def test_remove_callback_existing(self):
        svc = AgentTaskNotifier()
        svc._on_change("cb1", lambda e, d: None)
        assert svc.remove_callback("cb1") is True
        assert "cb1" not in svc.on_change

    def test_remove_callback_nonexistent(self):
        svc = AgentTaskNotifier()
        assert svc.remove_callback("nope") is False

    def test_callback_exception_swallowed(self):
        svc = AgentTaskNotifier()
        svc._on_change("bad", lambda e, d: 1 / 0)
        # Should not raise
        nid = svc.notify("t1", "a1", "started")
        assert nid != ""


class TestPruning:
    """Pruning when max_entries is exceeded."""

    def test_prune_removes_oldest_quarter(self):
        svc = AgentTaskNotifier(max_entries=8)
        ids = []
        for i in range(8):
            ids.append(svc.notify(f"t{i}", "a1", "started"))
        # All 8 present
        assert svc.get_notification_count() == 8
        # Adding one more triggers pruning
        svc.notify("t-extra", "a1", "started")
        # Should have pruned 2 (quarter of 8) then added 1: 8 - 2 + 1 = 7
        assert svc.get_notification_count() == 7
        # Oldest two should be gone
        assert svc.get_notification(ids[0]) is None
        assert svc.get_notification(ids[1]) is None
        # Recent ones should still exist
        assert svc.get_notification(ids[7]) is not None


class TestStats:
    """Statistics reporting."""

    def test_stats_empty(self):
        svc = AgentTaskNotifier()
        stats = svc.get_stats()
        assert stats["total_notifications"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_event_types"] == 0
        assert stats["unique_tasks"] == 0

    def test_stats_after_notifications(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.notify("t2", "a2", "completed")
        stats = svc.get_stats()
        assert stats["total_notifications"] == 2
        assert stats["unique_agents"] == 2
        assert stats["unique_event_types"] == 2
        assert stats["unique_tasks"] == 2
        assert stats["max_entries"] == 10000

    def test_stats_returns_dict(self):
        svc = AgentTaskNotifier()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.reset()
        assert svc.get_notification_count() == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskNotifier()
        svc._on_change("cb1", lambda e, d: None)
        svc.reset()
        assert svc.on_change == {}

    def test_reset_resets_seq(self):
        svc = AgentTaskNotifier()
        svc.notify("t1", "a1", "started")
        svc.reset()
        assert svc._state._seq == 0


class TestState:
    """AgentTaskNotifierState dataclass."""

    def test_default_entries(self):
        state = AgentTaskNotifierState()
        assert state.entries == {}
        assert state._seq == 0

    def test_entries_type(self):
        state = AgentTaskNotifierState()
        assert isinstance(state.entries, dict)


class TestPrefix:
    """PREFIX constant."""

    def test_prefix_value(self):
        assert AgentTaskNotifier.PREFIX == "atnf-"

    def test_max_entries_default(self):
        assert AgentTaskNotifier.MAX_ENTRIES == 10000
