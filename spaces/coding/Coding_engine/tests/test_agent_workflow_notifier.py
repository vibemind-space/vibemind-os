"""Tests for AgentWorkflowNotifier."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_notifier import AgentWorkflowNotifier


def test_init():
    n = AgentWorkflowNotifier()
    assert n._state is not None
    assert n._callbacks == {}
    assert n._on_change is None


def test_generate_id_prefix():
    n = AgentWorkflowNotifier()
    nid = n._generate_id("test")
    assert nid.startswith("awn-")
    assert len(nid) == 4 + 16


def test_generate_id_unique():
    n = AgentWorkflowNotifier()
    id1 = n._generate_id("test")
    id2 = n._generate_id("test")
    assert id1 != id2


def test_notify_basic():
    n = AgentWorkflowNotifier()
    nid = n.notify("agent1", "wf1", "started")
    assert nid.startswith("awn-")
    entry = n.get_notification(nid)
    assert entry["agent_id"] == "agent1"
    assert entry["workflow_name"] == "wf1"
    assert entry["event"] == "started"
    assert entry["read"] is False


def test_notify_with_message():
    n = AgentWorkflowNotifier()
    nid = n.notify("agent1", "wf1", "started", message="Workflow began")
    entry = n.get_notification(nid)
    assert entry["message"] == "Workflow began"


def test_notify_with_metadata():
    n = AgentWorkflowNotifier()
    nid = n.notify("agent1", "wf1", "error", metadata={"code": 500})
    entry = n.get_notification(nid)
    assert entry["metadata"] == {"code": 500}


def test_notify_default_metadata():
    n = AgentWorkflowNotifier()
    nid = n.notify("agent1", "wf1", "started")
    entry = n.get_notification(nid)
    assert entry["metadata"] == {}


def test_get_notification_not_found():
    n = AgentWorkflowNotifier()
    assert n.get_notification("nonexistent") is None


def test_get_notifications_all():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "started")
    n.notify("agent2", "wf2", "completed")
    results = n.get_notifications()
    assert len(results) == 2


def test_get_notifications_by_agent():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "started")
    n.notify("agent2", "wf2", "completed")
    n.notify("agent1", "wf3", "failed")
    results = n.get_notifications(agent_id="agent1")
    assert len(results) == 2
    assert all(r["agent_id"] == "agent1" for r in results)


def test_get_notifications_by_workflow():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "started")
    n.notify("agent2", "wf1", "completed")
    n.notify("agent1", "wf2", "failed")
    results = n.get_notifications(workflow_name="wf1")
    assert len(results) == 2
    assert all(r["workflow_name"] == "wf1" for r in results)


def test_get_notifications_newest_first():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "first")
    time.sleep(0.01)
    n.notify("agent1", "wf1", "second")
    results = n.get_notifications()
    assert results[0]["event"] == "second"
    assert results[1]["event"] == "first"


def test_get_notifications_limit():
    n = AgentWorkflowNotifier()
    for i in range(10):
        n.notify("agent1", "wf1", f"event{i}")
    results = n.get_notifications(limit=3)
    assert len(results) == 3


def test_mark_read_success():
    n = AgentWorkflowNotifier()
    nid = n.notify("agent1", "wf1", "started")
    assert n.get_notification(nid)["read"] is False
    result = n.mark_read(nid)
    assert result is True
    assert n.get_notification(nid)["read"] is True


def test_mark_read_not_found():
    n = AgentWorkflowNotifier()
    assert n.mark_read("nonexistent") is False


def test_get_notification_count_all():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "started")
    n.notify("agent2", "wf2", "completed")
    assert n.get_notification_count() == 2


def test_get_notification_count_by_agent():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "started")
    n.notify("agent2", "wf2", "completed")
    n.notify("agent1", "wf3", "failed")
    assert n.get_notification_count(agent_id="agent1") == 2


def test_get_notification_count_by_read_status():
    n = AgentWorkflowNotifier()
    nid1 = n.notify("agent1", "wf1", "started")
    n.notify("agent1", "wf2", "completed")
    n.mark_read(nid1)
    assert n.get_notification_count(read=True) == 1
    assert n.get_notification_count(read=False) == 1


def test_get_stats():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "started")
    n.notify("agent2", "wf2", "completed")
    nid3 = n.notify("agent1", "wf3", "done")
    n.mark_read(nid3)
    stats = n.get_stats()
    assert stats["total_notifications"] == 3
    assert stats["unread_count"] == 2
    assert stats["unique_agents"] == 2


def test_reset():
    n = AgentWorkflowNotifier()
    n.notify("agent1", "wf1", "started")
    n.notify("agent2", "wf2", "completed")
    n.reset()
    assert len(n._state.entries) == 0
    assert n._state._seq == 0


def test_on_change_property():
    n = AgentWorkflowNotifier()
    assert n.on_change is None
    handler = lambda action, data: None
    n.on_change = handler
    assert n.on_change is handler


def test_fire_on_change_called():
    n = AgentWorkflowNotifier()
    events = []
    n.on_change = lambda action, data: events.append((action, data))
    n.notify("agent1", "wf1", "started")
    assert len(events) == 1
    assert events[0][0] == "notify"


def test_fire_callback_called():
    n = AgentWorkflowNotifier()
    events = []
    n._callbacks["test_cb"] = lambda action, data: events.append((action, data))
    n.notify("agent1", "wf1", "started")
    assert len(events) == 1
    assert events[0][0] == "notify"


def test_fire_silent_exception():
    n = AgentWorkflowNotifier()
    n.on_change = lambda action, data: (_ for _ in ()).throw(ValueError("boom"))
    n._callbacks["bad"] = lambda action, data: (_ for _ in ()).throw(RuntimeError("fail"))
    # Should not raise
    nid = n.notify("agent1", "wf1", "started")
    assert nid.startswith("awn-")


def test_remove_callback_success():
    n = AgentWorkflowNotifier()
    n._callbacks["cb1"] = lambda a, d: None
    assert n.remove_callback("cb1") is True
    assert "cb1" not in n._callbacks


def test_remove_callback_not_found():
    n = AgentWorkflowNotifier()
    assert n.remove_callback("nonexistent") is False


def test_prune_evicts_oldest():
    n = AgentWorkflowNotifier()
    n.MAX_ENTRIES = 5
    ids = []
    for i in range(7):
        ids.append(n.notify("agent1", "wf1", f"event{i}"))
    assert len(n._state.entries) == 5
    # Oldest should be evicted
    assert n.get_notification(ids[0]) is None
    assert n.get_notification(ids[1]) is None
    assert n.get_notification(ids[6]) is not None


def test_notify_returns_dict_via_get():
    n = AgentWorkflowNotifier()
    nid = n.notify("agent1", "wf1", "started")
    entry = n.get_notification(nid)
    assert isinstance(entry, dict)
    assert "notification_id" in entry
    assert "created_at" in entry


def test_get_stats_returns_dict():
    n = AgentWorkflowNotifier()
    stats = n.get_stats()
    assert isinstance(stats, dict)
    assert stats["total_notifications"] == 0
    assert stats["unread_count"] == 0
    assert stats["unique_agents"] == 0
