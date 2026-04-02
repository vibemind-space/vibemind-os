"""Test agent alert manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_alert_manager import AgentAlertManager


def test_raise_alert():
    mgr = AgentAlertManager()
    aid = mgr.raise_alert("agent-1", "cpu_high", "CPU over 90%", severity="critical")
    assert len(aid) > 0
    assert aid.startswith("aam-")
    print("OK: raise alert")


def test_acknowledge_alert():
    mgr = AgentAlertManager()
    aid = mgr.raise_alert("agent-1", "cpu_high", "CPU over 90%", severity="critical")
    assert mgr.acknowledge_alert(aid) is True
    alert = mgr.get_alert(aid)
    assert alert["acknowledged"] is True
    assert mgr.acknowledge_alert("nonexistent") is False
    print("OK: acknowledge alert")


def test_get_alert():
    mgr = AgentAlertManager()
    aid = mgr.raise_alert("agent-1", "mem_low", "Memory below 10%", severity="warning")
    alert = mgr.get_alert(aid)
    assert alert is not None
    assert alert["agent_id"] == "agent-1"
    assert alert["alert_type"] == "mem_low"
    assert alert["message"] == "Memory below 10%"
    assert alert["severity"] == "warning"
    assert alert["acknowledged"] is False
    assert mgr.get_alert("nonexistent") is None
    print("OK: get alert")


def test_get_alerts_filtered():
    mgr = AgentAlertManager()
    mgr.raise_alert("agent-1", "cpu", "high cpu", severity="warning")
    mgr.raise_alert("agent-1", "mem", "low mem", severity="critical")
    aid3 = mgr.raise_alert("agent-1", "disk", "disk ok", severity="info")
    mgr.acknowledge_alert(aid3)

    # filter by severity
    warnings = mgr.get_alerts("agent-1", severity="warning")
    assert len(warnings) == 1
    assert warnings[0]["alert_type"] == "cpu"

    # filter by acknowledged
    acked = mgr.get_alerts("agent-1", acknowledged=True)
    assert len(acked) == 1
    assert acked[0]["alert_type"] == "disk"

    unacked = mgr.get_alerts("agent-1", acknowledged=False)
    assert len(unacked) == 2

    # filter by both
    combo = mgr.get_alerts("agent-1", severity="info", acknowledged=True)
    assert len(combo) == 1
    print("OK: get alerts filtered")


def test_get_active_alerts():
    mgr = AgentAlertManager()
    aid1 = mgr.raise_alert("agent-1", "cpu", "high", severity="warning")
    mgr.raise_alert("agent-1", "mem", "low", severity="critical")
    mgr.raise_alert("agent-2", "disk", "full", severity="error")
    mgr.acknowledge_alert(aid1)

    # all active
    active = mgr.get_active_alerts()
    assert len(active) == 2

    # active for agent-1 only
    active_a1 = mgr.get_active_alerts(agent_id="agent-1")
    assert len(active_a1) == 1
    assert active_a1[0]["alert_type"] == "mem"

    # active for agent-2
    active_a2 = mgr.get_active_alerts(agent_id="agent-2")
    assert len(active_a2) == 1
    print("OK: get active alerts")


def test_dismiss_alert():
    mgr = AgentAlertManager()
    aid = mgr.raise_alert("agent-1", "cpu", "high", severity="warning")
    assert mgr.dismiss_alert(aid) is True
    assert mgr.get_alert(aid) is None
    assert mgr.dismiss_alert("nonexistent") is False
    print("OK: dismiss alert")


def test_get_alert_count():
    mgr = AgentAlertManager()
    mgr.raise_alert("agent-1", "cpu", "high", severity="warning")
    mgr.raise_alert("agent-1", "mem", "low", severity="critical")
    mgr.raise_alert("agent-2", "disk", "full", severity="error")

    assert mgr.get_alert_count() == 3
    assert mgr.get_alert_count(agent_id="agent-1") == 2
    assert mgr.get_alert_count(agent_id="agent-2") == 1
    assert mgr.get_alert_count(agent_id="agent-3") == 0
    print("OK: get alert count")


def test_list_agents():
    mgr = AgentAlertManager()
    mgr.raise_alert("agent-1", "cpu", "high", severity="warning")
    mgr.raise_alert("agent-2", "mem", "low", severity="critical")
    mgr.raise_alert("agent-3", "disk", "full", severity="error")
    agents = mgr.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    assert "agent-3" in agents
    assert len(agents) == 3
    print("OK: list agents")


def test_callbacks():
    mgr = AgentAlertManager()
    fired = []
    mgr.on_change("mon", lambda a, d: fired.append((a, d)))
    mgr.raise_alert("agent-1", "cpu", "high", severity="warning")
    assert len(fired) >= 1
    assert fired[0][0] == "alert_raised"
    assert "alert_id" in fired[0][1]
    assert mgr.remove_callback("mon") is True
    assert mgr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    mgr = AgentAlertManager()
    mgr.raise_alert("agent-1", "cpu", "high", severity="warning")
    aid2 = mgr.raise_alert("agent-2", "mem", "low", severity="critical")
    mgr.acknowledge_alert(aid2)
    stats = mgr.get_stats()
    assert stats["total_alerts"] == 2
    assert stats["acknowledged_count"] == 1
    assert stats["unacknowledged_count"] == 1
    assert stats["unique_agents"] == 2
    print("OK: stats")


def test_reset():
    mgr = AgentAlertManager()
    mgr.raise_alert("agent-1", "cpu", "high", severity="warning")
    mgr.raise_alert("agent-2", "mem", "low", severity="critical")
    mgr.reset()
    assert mgr.get_alert_count() == 0
    assert mgr.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Alert Manager Tests ===\n")
    test_raise_alert()
    test_acknowledge_alert()
    test_get_alert()
    test_get_alerts_filtered()
    test_get_active_alerts()
    test_dismiss_alert()
    test_get_alert_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
