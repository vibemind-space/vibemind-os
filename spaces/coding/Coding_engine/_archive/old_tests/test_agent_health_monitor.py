"""Test agent health monitor."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_health_monitor import AgentHealthMonitor


def test_register():
    """Register and unregister agents."""
    m = AgentHealthMonitor()
    assert m.register("Builder") is True
    assert m.register("Builder") is False

    agent = m.get_agent("Builder")
    assert agent is not None
    assert agent["status"] == "healthy"

    assert m.unregister("Builder") is True
    assert m.unregister("Builder") is False
    assert m.get_agent("Builder") is None
    print("OK: register")


def test_heartbeat():
    """Heartbeats keep agent healthy."""
    m = AgentHealthMonitor()
    m.register("Builder")

    assert m.heartbeat("Builder") is True
    assert m.heartbeat("Builder", metadata={"load": 0.5}) is True

    agent = m.get_agent("Builder")
    assert agent["heartbeat_count"] == 2
    assert agent["metadata"]["load"] == 0.5

    assert m.heartbeat("fake") is False
    print("OK: heartbeat")


def test_degraded_detection():
    """Detect degraded status after threshold."""
    m = AgentHealthMonitor(default_degraded_threshold=0.02)
    m.register("Builder")

    time.sleep(0.03)
    changes = m.evaluate()
    assert len(changes) == 1
    assert changes[0]["new_status"] == "degraded"
    assert m.get_status("Builder") == "degraded"
    print("OK: degraded detection")


def test_unhealthy_detection():
    """Detect unhealthy after threshold."""
    m = AgentHealthMonitor(
        default_degraded_threshold=0.01,
        default_unhealthy_threshold=0.02,
    )
    m.register("Builder")

    time.sleep(0.03)
    m.evaluate()
    assert m.get_status("Builder") == "unhealthy"
    print("OK: unhealthy detection")


def test_dead_detection():
    """Detect dead after threshold."""
    m = AgentHealthMonitor(
        default_degraded_threshold=0.01,
        default_unhealthy_threshold=0.02,
        default_dead_threshold=0.03,
    )
    m.register("Builder")

    time.sleep(0.04)
    m.evaluate()
    assert m.get_status("Builder") == "dead"
    print("OK: dead detection")


def test_heartbeat_recovery():
    """Heartbeat recovers agent to healthy."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("Builder")

    time.sleep(0.02)
    m.evaluate()
    assert m.get_status("Builder") == "degraded"

    m.heartbeat("Builder")
    assert m.get_status("Builder") == "healthy"
    print("OK: heartbeat recovery")


def test_custom_checks():
    """Custom checks can degrade status."""
    m = AgentHealthMonitor()
    m.register("Builder")

    m.report_check("Builder", "memory", True)
    m.report_check("Builder", "disk", False)

    m.evaluate()
    assert m.get_status("Builder") == "degraded"

    agent = m.get_agent("Builder")
    assert agent["failed_checks"] == 1

    # Fix the check
    m.report_check("Builder", "disk", True)
    m.evaluate()
    assert m.get_status("Builder") == "healthy"

    # Clear check
    assert m.clear_check("Builder", "disk") is True
    assert m.clear_check("Builder", "nonexistent") is False
    assert m.clear_check("fake", "disk") is False
    print("OK: custom checks")


def test_callbacks():
    """Callbacks fire on status change."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("Builder")

    fired = []
    assert m.on_status_change("monitor", lambda a, o, n: fired.append((a, o, n))) is True
    assert m.on_status_change("monitor", lambda a, o, n: None) is False  # Duplicate

    time.sleep(0.02)
    m.evaluate()

    assert len(fired) == 1
    assert fired[0] == ("Builder", "healthy", "degraded")

    assert m.remove_callback("monitor") is True
    assert m.remove_callback("monitor") is False
    print("OK: callbacks")


def test_list_agents():
    """List agents with status filter."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("A")
    m.register("B")

    all_agents = m.list_agents()
    assert len(all_agents) == 2

    healthy = m.list_agents(status="healthy")
    assert len(healthy) == 2

    # Make one degraded
    time.sleep(0.02)
    m.heartbeat("A")  # Keep A healthy
    m.evaluate()

    degraded = m.list_agents(status="degraded")
    assert len(degraded) == 1
    assert degraded[0]["agent_name"] == "B"
    print("OK: list agents")


def test_get_unhealthy():
    """Get all non-healthy agents."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("A")
    m.register("B")

    time.sleep(0.02)
    m.heartbeat("A")
    m.evaluate()

    unhealthy = m.get_unhealthy()
    assert len(unhealthy) == 1
    assert unhealthy[0]["agent_name"] == "B"
    print("OK: get unhealthy")


def test_history():
    """Status change history."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("Builder")

    time.sleep(0.02)
    m.evaluate()  # healthy -> degraded
    m.heartbeat("Builder")  # degraded -> healthy

    history = m.get_history("Builder")
    assert len(history) >= 3  # initial healthy + degraded + healthy
    assert history[-1]["status"] == "healthy"
    print("OK: history")


def test_alerts():
    """Health alerts are recorded."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("Builder")

    time.sleep(0.02)
    m.evaluate()

    alerts = m.get_alerts()
    assert len(alerts) >= 1
    assert alerts[-1]["agent_name"] == "Builder"
    assert alerts[-1]["new_status"] == "degraded"

    by_agent = m.get_alerts(agent_name="Builder")
    assert len(by_agent) >= 1

    assert m.get_alerts(agent_name="fake") == []
    print("OK: alerts")


def test_set_thresholds():
    """Update thresholds."""
    m = AgentHealthMonitor()
    m.register("Builder")

    assert m.set_thresholds("Builder", degraded=5.0, unhealthy=10.0) is True
    agent = m.get_agent("Builder")
    assert agent["degraded_threshold"] == 5.0
    assert agent["unhealthy_threshold"] == 10.0

    assert m.set_thresholds("fake") is False
    print("OK: set thresholds")


def test_summary():
    """Health summary counts."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("A")
    m.register("B")
    m.register("C")

    time.sleep(0.02)
    m.heartbeat("A")
    m.evaluate()

    summary = m.get_summary()
    assert summary.get("healthy", 0) >= 1
    assert summary.get("degraded", 0) >= 1
    print("OK: summary")


def test_evaluate_single():
    """Evaluate single agent."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("A")
    m.register("B")

    time.sleep(0.02)
    changes = m.evaluate("A")
    assert len(changes) == 1
    assert changes[0]["agent_name"] == "A"

    # B not evaluated yet
    assert m.get_status("B") == "healthy"
    print("OK: evaluate single")


def test_stats():
    """Stats are accurate."""
    m = AgentHealthMonitor(default_degraded_threshold=0.01)
    m.register("A")
    m.heartbeat("A")

    time.sleep(0.02)
    m.evaluate()

    stats = m.get_stats()
    assert stats["total_registered"] == 1
    assert stats["total_heartbeats"] == 1
    assert stats["total_agents"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    m = AgentHealthMonitor()
    m.register("A")

    m.reset()
    assert m.list_agents() == []
    stats = m.get_stats()
    assert stats["total_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Health Monitor Tests ===\n")
    test_register()
    test_heartbeat()
    test_degraded_detection()
    test_unhealthy_detection()
    test_dead_detection()
    test_heartbeat_recovery()
    test_custom_checks()
    test_callbacks()
    test_list_agents()
    test_get_unhealthy()
    test_history()
    test_alerts()
    test_set_thresholds()
    test_summary()
    test_evaluate_single()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
