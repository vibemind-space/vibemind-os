"""Tests for AgentWorkflowDispatcher."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_dispatcher import AgentWorkflowDispatcher


def test_dispatch_returns_id():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "agent1", "build")
    assert did.startswith("awdi-")
    assert len(did) == 5 + 16


def test_dispatch_default_priority():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "agent1", "build")
    entry = d.get_dispatch(did)
    assert entry["priority"] == "normal"


def test_dispatch_custom_priority():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "agent1", "build", priority="critical")
    entry = d.get_dispatch(did)
    assert entry["priority"] == "critical"


def test_dispatch_invalid_priority_defaults_to_normal():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "agent1", "build", priority="urgent")
    entry = d.get_dispatch(did)
    assert entry["priority"] == "normal"


def test_dispatch_with_metadata():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "agent1", "build", metadata={"env": "prod"})
    entry = d.get_dispatch(did)
    assert entry["metadata"] == {"env": "prod"}


def test_dispatch_status_is_pending():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "agent1", "build")
    entry = d.get_dispatch(did)
    assert entry["status"] == "pending"


def test_get_dispatch_not_found():
    d = AgentWorkflowDispatcher()
    assert d.get_dispatch("awdi-nonexistent") is None


def test_get_dispatches_all():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.dispatch("wf2", "a2", "t2")
    results = d.get_dispatches()
    assert len(results) == 2


def test_get_dispatches_by_workflow():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.dispatch("wf2", "a2", "t2")
    d.dispatch("wf1", "a3", "t3")
    results = d.get_dispatches(workflow_id="wf1")
    assert len(results) == 2
    assert all(r["workflow_id"] == "wf1" for r in results)


def test_get_dispatches_by_agent():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.dispatch("wf2", "a1", "t2")
    d.dispatch("wf1", "a2", "t3")
    results = d.get_dispatches(agent_id="a1")
    assert len(results) == 2


def test_get_dispatches_newest_first():
    d = AgentWorkflowDispatcher()
    id1 = d.dispatch("wf1", "a1", "first")
    id2 = d.dispatch("wf1", "a1", "second")
    # Ensure distinct timestamps for ordering
    d.get_dispatch(id1)["created_at"] = 1000.0
    d.get_dispatch(id2)["created_at"] = 2000.0
    results = d.get_dispatches()
    assert results[0]["task"] == "second"
    assert results[1]["task"] == "first"


def test_get_dispatches_limit():
    d = AgentWorkflowDispatcher()
    for i in range(10):
        d.dispatch("wf1", "a1", f"task{i}")
    results = d.get_dispatches(limit=3)
    assert len(results) == 3


def test_complete_dispatch():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "a1", "build")
    assert d.complete_dispatch(did, result="success") is True
    entry = d.get_dispatch(did)
    assert entry["status"] == "completed"
    assert entry["result"] == "success"
    assert entry["completed_at"] is not None


def test_complete_dispatch_not_found():
    d = AgentWorkflowDispatcher()
    assert d.complete_dispatch("awdi-nope") is False


def test_get_dispatch_count_all():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.dispatch("wf2", "a2", "t2")
    assert d.get_dispatch_count() == 2


def test_get_dispatch_count_by_workflow():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.dispatch("wf2", "a2", "t2")
    d.dispatch("wf1", "a3", "t3")
    assert d.get_dispatch_count(workflow_id="wf1") == 2


def test_get_dispatch_count_by_agent():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.dispatch("wf2", "a1", "t2")
    d.dispatch("wf1", "a2", "t3")
    assert d.get_dispatch_count(agent_id="a1") == 2


def test_get_stats():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1", priority="high")
    d.dispatch("wf1", "a1", "t2", priority="low")
    did = d.dispatch("wf1", "a1", "t3", priority="high")
    d.complete_dispatch(did)
    stats = d.get_stats()
    assert stats["total_dispatches"] == 3
    assert stats["completed_count"] == 1
    assert stats["by_priority"]["high"] == 2
    assert stats["by_priority"]["low"] == 1
    assert "seq" in stats
    assert "uptime" in stats


def test_reset():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.reset()
    assert d.get_dispatch_count() == 0
    assert d.get_dispatches() == []


def test_unique_ids():
    d = AgentWorkflowDispatcher()
    ids = set()
    for i in range(20):
        ids.add(d.dispatch("wf1", "a1", f"task{i}"))
    assert len(ids) == 20


def test_on_change_property():
    d = AgentWorkflowDispatcher()
    assert d.on_change is None
    events = []
    d.on_change = lambda action, data: events.append(action)
    d.dispatch("wf1", "a1", "t1")
    assert "dispatch" in events


def test_on_change_setter_none():
    d = AgentWorkflowDispatcher()
    d.on_change = lambda a, b: None
    d.on_change = None
    assert d.on_change is None


def test_callbacks_fire_on_dispatch():
    d = AgentWorkflowDispatcher()
    events = []
    d._callbacks["test"] = lambda action, data: events.append(action)
    d.dispatch("wf1", "a1", "build")
    assert "dispatch" in events


def test_callbacks_fire_on_complete():
    d = AgentWorkflowDispatcher()
    events = []
    d._callbacks["test"] = lambda action, data: events.append(action)
    did = d.dispatch("wf1", "a1", "build")
    d.complete_dispatch(did)
    assert "complete_dispatch" in events


def test_callback_exception_silenced():
    d = AgentWorkflowDispatcher()
    d._callbacks["bad"] = lambda a, b: (_ for _ in ()).throw(RuntimeError("boom"))
    # Should not raise
    d.dispatch("wf1", "a1", "build")


def test_remove_callback():
    d = AgentWorkflowDispatcher()
    d._callbacks["x"] = lambda a, b: None
    assert d.remove_callback("x") is True
    assert d.remove_callback("x") is False


def test_dispatch_metadata_defaults_to_empty_dict():
    d = AgentWorkflowDispatcher()
    did = d.dispatch("wf1", "a1", "t1")
    assert d.get_dispatch(did)["metadata"] == {}


def test_get_dispatches_combined_filters():
    d = AgentWorkflowDispatcher()
    d.dispatch("wf1", "a1", "t1")
    d.dispatch("wf1", "a2", "t2")
    d.dispatch("wf2", "a1", "t3")
    results = d.get_dispatches(workflow_id="wf1", agent_id="a1")
    assert len(results) == 1
    assert results[0]["task"] == "t1"
