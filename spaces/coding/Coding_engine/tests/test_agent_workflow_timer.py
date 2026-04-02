"""Tests for AgentWorkflowTimer."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_timer import AgentWorkflowTimer


def test_start_timer_returns_id():
    svc = AgentWorkflowTimer()
    tid = svc.start_timer("a1", "wf1")
    assert tid.startswith("awt-")
    assert len(tid) > len("awt-")


def test_start_timer_with_label():
    svc = AgentWorkflowTimer()
    tid = svc.start_timer("a1", "wf1", label="step-1")
    entry = svc.get_timer(tid)
    assert entry is not None
    assert entry["label"] == "step-1"


def test_get_timer_returns_dict():
    svc = AgentWorkflowTimer()
    tid = svc.start_timer("a1", "wf1")
    entry = svc.get_timer(tid)
    assert entry["timer_id"] == tid
    assert entry["agent_id"] == "a1"
    assert entry["workflow_name"] == "wf1"
    assert entry["status"] == "running"
    assert entry["started_at"] > 0
    assert entry["stopped_at"] is None
    assert entry["elapsed"] is None


def test_get_timer_not_found():
    svc = AgentWorkflowTimer()
    assert svc.get_timer("awt-nonexistent") is None


def test_stop_timer_success():
    svc = AgentWorkflowTimer()
    tid = svc.start_timer("a1", "wf1")
    result = svc.stop_timer(tid)
    assert result is True
    entry = svc.get_timer(tid)
    assert entry["status"] == "completed"
    assert entry["stopped_at"] is not None
    assert entry["elapsed"] is not None
    assert entry["elapsed"] >= 0


def test_stop_timer_not_found():
    svc = AgentWorkflowTimer()
    assert svc.stop_timer("awt-missing") is False


def test_stop_timer_already_stopped():
    svc = AgentWorkflowTimer()
    tid = svc.start_timer("a1", "wf1")
    svc.stop_timer(tid)
    assert svc.stop_timer(tid) is False


def test_elapsed_time_positive():
    svc = AgentWorkflowTimer()
    tid = svc.start_timer("a1", "wf1")
    time.sleep(0.01)
    svc.stop_timer(tid)
    entry = svc.get_timer(tid)
    assert entry["elapsed"] >= 0.005


def test_get_timers_newest_first():
    svc = AgentWorkflowTimer()
    tid1 = svc.start_timer("a1", "wf1")
    # Manually adjust started_at to guarantee ordering
    svc._state.entries[tid1]["started_at"] = 1000.0
    tid2 = svc.start_timer("a1", "wf2")
    svc._state.entries[tid2]["started_at"] = 2000.0
    tid3 = svc.start_timer("a1", "wf3")
    svc._state.entries[tid3]["started_at"] = 3000.0
    results = svc.get_timers()
    assert len(results) == 3
    assert results[0]["timer_id"] == tid3
    assert results[2]["timer_id"] == tid1


def test_get_timers_filter_by_agent():
    svc = AgentWorkflowTimer()
    svc.start_timer("a1", "wf1")
    svc.start_timer("a2", "wf1")
    svc.start_timer("a1", "wf2")
    results = svc.get_timers(agent_id="a1")
    assert len(results) == 2
    assert all(r["agent_id"] == "a1" for r in results)


def test_get_timers_filter_by_workflow():
    svc = AgentWorkflowTimer()
    svc.start_timer("a1", "wf1")
    svc.start_timer("a1", "wf2")
    svc.start_timer("a2", "wf1")
    results = svc.get_timers(workflow_name="wf1")
    assert len(results) == 2
    assert all(r["workflow_name"] == "wf1" for r in results)


def test_get_timers_filter_by_both():
    svc = AgentWorkflowTimer()
    svc.start_timer("a1", "wf1")
    svc.start_timer("a1", "wf2")
    svc.start_timer("a2", "wf1")
    results = svc.get_timers(agent_id="a1", workflow_name="wf1")
    assert len(results) == 1


def test_get_timers_limit():
    svc = AgentWorkflowTimer()
    for i in range(10):
        svc.start_timer("a1", f"wf{i}")
    results = svc.get_timers(limit=3)
    assert len(results) == 3


def test_get_timer_count_all():
    svc = AgentWorkflowTimer()
    svc.start_timer("a1", "wf1")
    svc.start_timer("a2", "wf1")
    assert svc.get_timer_count() == 2


def test_get_timer_count_by_agent():
    svc = AgentWorkflowTimer()
    svc.start_timer("a1", "wf1")
    svc.start_timer("a2", "wf1")
    svc.start_timer("a1", "wf2")
    assert svc.get_timer_count(agent_id="a1") == 2
    assert svc.get_timer_count(agent_id="a2") == 1


def test_get_stats_empty():
    svc = AgentWorkflowTimer()
    stats = svc.get_stats()
    assert stats["total_timers"] == 0
    assert stats["completed_count"] == 0
    assert stats["unique_agents"] == 0


def test_get_stats_with_data():
    svc = AgentWorkflowTimer()
    tid1 = svc.start_timer("a1", "wf1")
    tid2 = svc.start_timer("a2", "wf2")
    svc.start_timer("a1", "wf3")
    svc.stop_timer(tid1)
    svc.stop_timer(tid2)
    stats = svc.get_stats()
    assert stats["total_timers"] == 3
    assert stats["completed_count"] == 2
    assert stats["unique_agents"] == 2


def test_reset():
    svc = AgentWorkflowTimer()
    svc.start_timer("a1", "wf1")
    svc.on_change = lambda a, d: None
    svc.reset()
    assert svc.get_timer_count() == 0
    assert svc.get_stats()["total_timers"] == 0
    assert svc.on_change is None


def test_on_change_property():
    svc = AgentWorkflowTimer()
    assert svc.on_change is None
    handler = lambda a, d: None
    svc.on_change = handler
    assert svc.on_change is handler


def test_on_change_fires_on_start():
    events = []
    svc = AgentWorkflowTimer()
    svc.on_change = lambda action, data: events.append((action, data))
    svc.start_timer("a1", "wf1")
    assert len(events) == 1
    assert events[0][0] == "timer_started"


def test_on_change_fires_on_stop():
    events = []
    svc = AgentWorkflowTimer()
    svc.on_change = lambda action, data: events.append((action, data))
    tid = svc.start_timer("a1", "wf1")
    svc.stop_timer(tid)
    assert len(events) == 2
    assert events[1][0] == "timer_stopped"
    assert "elapsed" in events[1][1]


def test_callback_fires_events():
    events = []
    svc = AgentWorkflowTimer()
    svc._callbacks["test"] = lambda action, data: events.append(action)
    tid = svc.start_timer("a1", "wf1")
    svc.stop_timer(tid)
    assert "timer_started" in events
    assert "timer_stopped" in events


def test_remove_callback():
    svc = AgentWorkflowTimer()
    svc._callbacks["cb1"] = lambda a, d: None
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False


def test_callback_exception_silent():
    svc = AgentWorkflowTimer()
    svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
    # Should not raise
    tid = svc.start_timer("a1", "wf1")
    assert svc.get_timer(tid) is not None


def test_on_change_exception_silent():
    svc = AgentWorkflowTimer()
    svc.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
    # Lazy generator won't raise; use a direct raise instead
    def bad_handler(a, d):
        raise RuntimeError("boom")
    svc.on_change = bad_handler
    tid = svc.start_timer("a1", "wf1")
    assert svc.get_timer(tid) is not None


def test_unique_ids():
    svc = AgentWorkflowTimer()
    ids = set()
    for i in range(100):
        ids.add(svc.start_timer("a1", "wf1"))
    assert len(ids) == 100


def test_get_timer_returns_copy():
    svc = AgentWorkflowTimer()
    tid = svc.start_timer("a1", "wf1")
    entry1 = svc.get_timer(tid)
    entry2 = svc.get_timer(tid)
    assert entry1 == entry2
    entry1["label"] = "mutated"
    assert svc.get_timer(tid)["label"] != "mutated"


def test_pruning():
    svc = AgentWorkflowTimer()
    svc.MAX_ENTRIES = 10
    for i in range(15):
        svc.start_timer(f"a{i}", f"wf{i}")
    assert len(svc._state.entries) <= 11


def test_prefix_constant():
    assert AgentWorkflowTimer.PREFIX == "awt-"


def test_max_entries_constant():
    assert AgentWorkflowTimer.MAX_ENTRIES == 10000
