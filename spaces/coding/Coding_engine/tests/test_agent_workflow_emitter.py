"""Tests for AgentWorkflowEmitter."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_emitter import AgentWorkflowEmitter


def test_init():
    e = AgentWorkflowEmitter()
    assert e._state is not None
    assert e._callbacks == {}
    assert e._on_change is None


def test_generate_id_prefix():
    e = AgentWorkflowEmitter()
    eid = e._generate_id("test")
    assert eid.startswith("awem-")
    assert len(eid) == 5 + 16


def test_generate_id_unique():
    e = AgentWorkflowEmitter()
    id1 = e._generate_id("test")
    id2 = e._generate_id("test")
    assert id1 != id2


def test_emit_basic():
    e = AgentWorkflowEmitter()
    eid = e.emit("agent1", "wf1", "created")
    assert eid.startswith("awem-")
    entry = e.get_event(eid)
    assert entry["agent_id"] == "agent1"
    assert entry["workflow_name"] == "wf1"
    assert entry["event_type"] == "created"


def test_emit_with_data():
    e = AgentWorkflowEmitter()
    eid = e.emit("agent1", "wf1", "failed", data={"error": "timeout"})
    entry = e.get_event(eid)
    assert entry["data"] == {"error": "timeout"}


def test_emit_default_data():
    e = AgentWorkflowEmitter()
    eid = e.emit("agent1", "wf1", "started")
    entry = e.get_event(eid)
    assert entry["data"] == {}


def test_emit_event_types():
    e = AgentWorkflowEmitter()
    for et in ["created", "started", "paused", "resumed", "completed", "failed"]:
        eid = e.emit("agent1", "wf1", et)
        entry = e.get_event(eid)
        assert entry["event_type"] == et


def test_get_event_not_found():
    e = AgentWorkflowEmitter()
    assert e.get_event("nonexistent") is None


def test_get_events_all():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent2", "wf2", "started")
    results = e.get_events()
    assert len(results) == 2


def test_get_events_by_agent():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent2", "wf2", "started")
    e.emit("agent1", "wf3", "completed")
    results = e.get_events(agent_id="agent1")
    assert len(results) == 2
    assert all(r["agent_id"] == "agent1" for r in results)


def test_get_events_by_workflow():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent2", "wf1", "started")
    e.emit("agent1", "wf2", "completed")
    results = e.get_events(workflow_name="wf1")
    assert len(results) == 2
    assert all(r["workflow_name"] == "wf1" for r in results)


def test_get_events_by_event_type():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent1", "wf2", "started")
    e.emit("agent2", "wf1", "created")
    results = e.get_events(event_type="created")
    assert len(results) == 2
    assert all(r["event_type"] == "created" for r in results)


def test_get_events_newest_first():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    time.sleep(0.01)
    e.emit("agent1", "wf1", "started")
    results = e.get_events()
    assert results[0]["event_type"] == "started"
    assert results[1]["event_type"] == "created"


def test_get_events_limit():
    e = AgentWorkflowEmitter()
    for i in range(10):
        e.emit("agent1", "wf1", f"event{i}")
    results = e.get_events(limit=3)
    assert len(results) == 3


def test_get_event_count_all():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent2", "wf2", "started")
    assert e.get_event_count() == 2


def test_get_event_count_by_agent():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent2", "wf2", "started")
    e.emit("agent1", "wf3", "completed")
    assert e.get_event_count(agent_id="agent1") == 2


def test_get_event_count_by_event_type():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent1", "wf2", "started")
    e.emit("agent2", "wf1", "created")
    assert e.get_event_count(event_type="created") == 2


def test_get_stats():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent2", "wf2", "started")
    e.emit("agent1", "wf3", "created")
    stats = e.get_stats()
    assert stats["total_events"] == 3
    assert stats["events_by_type"]["created"] == 2
    assert stats["events_by_type"]["started"] == 1
    assert stats["unique_agents"] == 2


def test_get_stats_empty():
    e = AgentWorkflowEmitter()
    stats = e.get_stats()
    assert stats["total_events"] == 0
    assert stats["events_by_type"] == {}
    assert stats["unique_agents"] == 0


def test_reset():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent2", "wf2", "started")
    e.reset()
    assert len(e._state.entries) == 0
    assert e._state._seq == 0


def test_on_change_property():
    e = AgentWorkflowEmitter()
    assert e.on_change is None
    handler = lambda action, data: None
    e.on_change = handler
    assert e.on_change is handler


def test_fire_on_change_called():
    e = AgentWorkflowEmitter()
    events = []
    e.on_change = lambda action, data: events.append((action, data))
    e.emit("agent1", "wf1", "created")
    assert len(events) == 1
    assert events[0][0] == "emit"


def test_fire_callback_called():
    e = AgentWorkflowEmitter()
    events = []
    e._callbacks["test_cb"] = lambda action, data: events.append((action, data))
    e.emit("agent1", "wf1", "created")
    assert len(events) == 1
    assert events[0][0] == "emit"


def test_fire_silent_exception():
    e = AgentWorkflowEmitter()
    e.on_change = lambda action, data: (_ for _ in ()).throw(ValueError("boom"))
    e._callbacks["bad"] = lambda action, data: (_ for _ in ()).throw(RuntimeError("fail"))
    eid = e.emit("agent1", "wf1", "created")
    assert eid.startswith("awem-")


def test_remove_callback_success():
    e = AgentWorkflowEmitter()
    e._callbacks["cb1"] = lambda a, d: None
    assert e.remove_callback("cb1") is True
    assert "cb1" not in e._callbacks


def test_remove_callback_not_found():
    e = AgentWorkflowEmitter()
    assert e.remove_callback("nonexistent") is False


def test_prune_evicts_oldest():
    e = AgentWorkflowEmitter()
    e.MAX_ENTRIES = 5
    ids = []
    for i in range(7):
        ids.append(e.emit("agent1", "wf1", f"event{i}"))
    assert len(e._state.entries) == 5
    assert e.get_event(ids[0]) is None
    assert e.get_event(ids[1]) is None
    assert e.get_event(ids[6]) is not None


def test_emit_returns_dict_via_get():
    e = AgentWorkflowEmitter()
    eid = e.emit("agent1", "wf1", "created")
    entry = e.get_event(eid)
    assert isinstance(entry, dict)
    assert "event_id" in entry
    assert "created_at" in entry


def test_get_stats_returns_dict():
    e = AgentWorkflowEmitter()
    stats = e.get_stats()
    assert isinstance(stats, dict)


def test_get_events_combined_filters():
    e = AgentWorkflowEmitter()
    e.emit("agent1", "wf1", "created")
    e.emit("agent1", "wf1", "started")
    e.emit("agent1", "wf2", "created")
    e.emit("agent2", "wf1", "created")
    results = e.get_events(agent_id="agent1", workflow_name="wf1")
    assert len(results) == 2


def test_fire_on_reset():
    e = AgentWorkflowEmitter()
    events = []
    e.on_change = lambda action, data: events.append((action, data))
    e.reset()
    assert len(events) == 1
    assert events[0][0] == "reset"


def test_fire_on_get_stats():
    e = AgentWorkflowEmitter()
    events = []
    e.on_change = lambda action, data: events.append((action, data))
    e.get_stats()
    assert len(events) == 1
    assert events[0][0] == "get_stats"
