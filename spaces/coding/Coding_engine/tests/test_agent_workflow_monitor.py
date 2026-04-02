"""Tests for AgentWorkflowMonitor."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_monitor import (
    AgentWorkflowMonitor,
    AgentWorkflowMonitorState,
)


def test_init():
    m = AgentWorkflowMonitor()
    assert m._state is not None
    assert m._callbacks == {}
    assert m._on_change is None
    assert isinstance(m._state, AgentWorkflowMonitorState)


def test_generate_id_prefix():
    m = AgentWorkflowMonitor()
    mid = m._generate_id("test")
    assert mid.startswith("awmo-")
    assert len(mid) == 5 + 16


def test_generate_id_unique():
    m = AgentWorkflowMonitor()
    id1 = m._generate_id("test")
    id2 = m._generate_id("test")
    assert id1 != id2


def test_start_monitoring_basic():
    m = AgentWorkflowMonitor()
    mid = m.start_monitoring("agent1", "wf1")
    assert mid.startswith("awmo-")
    entry = m.get_monitor(mid)
    assert entry["agent_id"] == "agent1"
    assert entry["workflow_name"] == "wf1"
    assert entry["status"] == "active"
    assert entry["timeout_seconds"] == 300


def test_start_monitoring_custom_timeout():
    m = AgentWorkflowMonitor()
    mid = m.start_monitoring("agent1", "wf1", timeout_seconds=60)
    entry = m.get_monitor(mid)
    assert entry["timeout_seconds"] == 60


def test_heartbeat_success():
    m = AgentWorkflowMonitor()
    mid = m.start_monitoring("agent1", "wf1")
    old_hb = m.get_monitor(mid)["heartbeat_at"]
    time.sleep(0.01)
    result = m.heartbeat(mid)
    assert result is True
    new_hb = m.get_monitor(mid)["heartbeat_at"]
    assert new_hb >= old_hb


def test_heartbeat_not_found():
    m = AgentWorkflowMonitor()
    result = m.heartbeat("nonexistent")
    assert result is False


def test_complete_monitoring_success():
    m = AgentWorkflowMonitor()
    mid = m.start_monitoring("agent1", "wf1")
    result = m.complete_monitoring(mid)
    assert result is True
    entry = m.get_monitor(mid)
    assert entry["status"] == "success"


def test_complete_monitoring_custom_status():
    m = AgentWorkflowMonitor()
    mid = m.start_monitoring("agent1", "wf1")
    result = m.complete_monitoring(mid, status="failed")
    assert result is True
    assert m.get_monitor(mid)["status"] == "failed"


def test_complete_monitoring_not_found():
    m = AgentWorkflowMonitor()
    result = m.complete_monitoring("nonexistent")
    assert result is False


def test_get_monitor_not_found():
    m = AgentWorkflowMonitor()
    entry = m.get_monitor("nonexistent")
    assert entry == {}


def test_get_monitors_all():
    m = AgentWorkflowMonitor()
    m.start_monitoring("agent1", "wf1")
    m.start_monitoring("agent2", "wf2")
    monitors = m.get_monitors()
    assert len(monitors) == 2


def test_get_monitors_by_agent():
    m = AgentWorkflowMonitor()
    m.start_monitoring("agent1", "wf1")
    m.start_monitoring("agent2", "wf2")
    m.start_monitoring("agent1", "wf3")
    monitors = m.get_monitors(agent_id="agent1")
    assert len(monitors) == 2


def test_get_monitors_by_status():
    m = AgentWorkflowMonitor()
    mid1 = m.start_monitoring("agent1", "wf1")
    m.start_monitoring("agent1", "wf2")
    m.complete_monitoring(mid1)
    monitors = m.get_monitors(status="active")
    assert len(monitors) == 1
    monitors = m.get_monitors(status="success")
    assert len(monitors) == 1


def test_get_stalled():
    m = AgentWorkflowMonitor()
    mid = m.start_monitoring("agent1", "wf1", timeout_seconds=0.01)
    time.sleep(0.02)
    stalled = m.get_stalled()
    assert len(stalled) == 1
    assert stalled[0]["monitor_id"] == mid


def test_get_stalled_with_override():
    m = AgentWorkflowMonitor()
    m.start_monitoring("agent1", "wf1", timeout_seconds=9999)
    time.sleep(0.02)
    stalled = m.get_stalled(timeout_override=0.01)
    assert len(stalled) == 1


def test_get_active_count():
    m = AgentWorkflowMonitor()
    m.start_monitoring("agent1", "wf1")
    m.start_monitoring("agent1", "wf2")
    mid3 = m.start_monitoring("agent2", "wf3")
    m.complete_monitoring(mid3)
    assert m.get_active_count() == 2
    assert m.get_active_count(agent_id="agent1") == 2
    assert m.get_active_count(agent_id="agent2") == 0


def test_get_monitor_count():
    m = AgentWorkflowMonitor()
    m.start_monitoring("agent1", "wf1")
    m.start_monitoring("agent2", "wf2")
    m.start_monitoring("agent1", "wf3")
    assert m.get_monitor_count() == 3
    assert m.get_monitor_count(agent_id="agent1") == 2
    assert m.get_monitor_count(agent_id="agent2") == 1


def test_get_stats():
    m = AgentWorkflowMonitor()
    m.start_monitoring("agent1", "wf1", timeout_seconds=0.01)
    mid2 = m.start_monitoring("agent1", "wf2")
    m.complete_monitoring(mid2)
    time.sleep(0.02)
    stats = m.get_stats()
    assert stats["total_monitors"] == 2
    assert stats["active"] == 1
    assert stats["completed"] == 1
    assert stats["stalled_count"] == 1


def test_reset():
    m = AgentWorkflowMonitor()
    m.start_monitoring("agent1", "wf1")
    m.reset()
    assert m.get_monitor_count() == 0
    assert m._callbacks == {}
    assert m._on_change is None


def test_on_change_callback():
    events = []
    m = AgentWorkflowMonitor()
    m.on_change = lambda evt, data: events.append(evt)
    m.start_monitoring("agent1", "wf1")
    assert "start_monitoring" in events


def test_remove_callback():
    m = AgentWorkflowMonitor()
    m._callbacks["cb1"] = lambda e, d: None
    assert m.remove_callback("cb1") is True
    assert m.remove_callback("cb1") is False


def test_prune():
    m = AgentWorkflowMonitor()
    m.MAX_ENTRIES = 5
    for i in range(8):
        m.start_monitoring(f"agent{i}", f"wf{i}")
    assert len(m._state.entries) <= 5


if __name__ == "__main__":
    tests = [
        test_init,
        test_generate_id_prefix,
        test_generate_id_unique,
        test_start_monitoring_basic,
        test_start_monitoring_custom_timeout,
        test_heartbeat_success,
        test_heartbeat_not_found,
        test_complete_monitoring_success,
        test_complete_monitoring_custom_status,
        test_complete_monitoring_not_found,
        test_get_monitor_not_found,
        test_get_monitors_all,
        test_get_monitors_by_agent,
        test_get_monitors_by_status,
        test_get_stalled,
        test_get_stalled_with_override,
        test_get_active_count,
        test_get_monitor_count,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_prune,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{passed + failed} tests passed")
