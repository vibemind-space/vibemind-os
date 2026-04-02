"""Test agent alert dispatcher -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_alert_dispatcher import AgentAlertDispatcher


def test_send_alert():
    ad = AgentAlertDispatcher()
    aid = ad.send_alert("agent-1", "critical", "CPU over 90%", alert_type="resource")
    assert len(aid) > 0
    assert aid.startswith("aad-")
    print("OK: send alert")


def test_get_alerts():
    ad = AgentAlertDispatcher()
    ad.send_alert("agent-1", "info", "started")
    ad.send_alert("agent-1", "warning", "high load")
    ad.send_alert("agent-1", "critical", "failure")
    alerts = ad.get_alerts("agent-1")
    assert len(alerts) == 3
    print("OK: get alerts")


def test_get_alerts_filtered():
    ad = AgentAlertDispatcher()
    ad.send_alert("agent-1", "info", "started")
    ad.send_alert("agent-1", "critical", "failure")
    alerts = ad.get_alerts("agent-1", severity="critical")
    assert len(alerts) == 1
    print("OK: get alerts filtered")


def test_get_latest_alert():
    ad = AgentAlertDispatcher()
    ad.send_alert("agent-1", "info", "first")
    ad.send_alert("agent-1", "warning", "second")
    latest = ad.get_latest_alert("agent-1")
    assert latest is not None
    assert latest["message"] == "second"
    print("OK: get latest alert")


def test_acknowledge_alert():
    ad = AgentAlertDispatcher()
    aid = ad.send_alert("agent-1", "critical", "failure")
    assert ad.acknowledge_alert(aid) is True
    assert ad.acknowledge_alert("nonexistent") is False
    print("OK: acknowledge alert")


def test_get_unacknowledged_count():
    ad = AgentAlertDispatcher()
    ad.send_alert("agent-1", "info", "msg1")
    aid2 = ad.send_alert("agent-1", "warning", "msg2")
    ad.acknowledge_alert(aid2)
    assert ad.get_unacknowledged_count("agent-1") == 1
    print("OK: get unacknowledged count")


def test_list_agents():
    ad = AgentAlertDispatcher()
    ad.send_alert("agent-1", "info", "msg")
    ad.send_alert("agent-2", "info", "msg")
    agents = ad.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ad = AgentAlertDispatcher()
    fired = []
    ad.on_change("mon", lambda a, d: fired.append(a))
    ad.send_alert("agent-1", "info", "msg")
    assert len(fired) >= 1
    assert ad.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ad = AgentAlertDispatcher()
    ad.send_alert("agent-1", "info", "msg")
    stats = ad.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ad = AgentAlertDispatcher()
    ad.send_alert("agent-1", "info", "msg")
    ad.reset()
    assert ad.get_alert_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Alert Dispatcher Tests ===\n")
    test_send_alert()
    test_get_alerts()
    test_get_alerts_filtered()
    test_get_latest_alert()
    test_acknowledge_alert()
    test_get_unacknowledged_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
