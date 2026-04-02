"""Test health dashboard."""
import sys
sys.path.insert(0, ".")

from src.services.health_dashboard import (
    HealthDashboard,
    HealthStatus,
    AlertSeverity,
)


def test_register_component():
    """Register a component for monitoring."""
    dash = HealthDashboard()
    assert dash.register_component("Builder", "agent") is True
    assert dash.register_component("Builder", "agent") is False  # Duplicate

    comp = dash.get_component("Builder")
    assert comp is not None
    assert comp["name"] == "Builder"
    assert comp["component_type"] == "agent"
    assert comp["status"] == "unknown"
    print("OK: register component")


def test_unregister():
    """Unregister a component."""
    dash = HealthDashboard()
    dash.register_component("Temp", "service")
    assert dash.unregister_component("Temp") is True
    assert dash.get_component("Temp") is None
    assert dash.unregister_component("Temp") is False
    print("OK: unregister")


def test_report_health():
    """Report health status."""
    dash = HealthDashboard()
    dash.register_component("Builder", "agent")

    assert dash.report_health("Builder", "healthy",
                               metrics={"tasks": 5}, message="All good") is True

    comp = dash.get_component("Builder")
    assert comp["status"] == "healthy"
    assert comp["metrics"]["tasks"] == 5
    assert comp["history_size"] == 1

    assert dash.report_health("nonexistent", "healthy") is False
    print("OK: report health")


def test_uptime_ratio():
    """Uptime ratio tracks healthy reports."""
    dash = HealthDashboard()
    dash.register_component("Agent", "agent")

    dash.report_health("Agent", "healthy")
    dash.report_health("Agent", "healthy")
    dash.report_health("Agent", "unhealthy")
    dash.report_health("Agent", "healthy")

    comp = dash.get_component("Agent")
    assert comp["uptime_ratio"] == 0.75
    print("OK: uptime ratio")


def test_auto_alert_unhealthy():
    """Alert auto-created when component becomes unhealthy."""
    dash = HealthDashboard()
    dash.register_component("Agent", "agent")

    dash.report_health("Agent", "healthy")
    dash.report_health("Agent", "unhealthy", message="OOM")

    alerts = dash.get_alerts(active_only=True)
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert "unhealthy" in alerts[0]["message"].lower()
    print("OK: auto alert unhealthy")


def test_auto_alert_degraded():
    """Alert for degraded status."""
    dash = HealthDashboard()
    dash.register_component("Agent", "agent")

    dash.report_health("Agent", "healthy")
    dash.report_health("Agent", "degraded", message="Slow")

    alerts = dash.get_alerts()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "warning"
    print("OK: auto alert degraded")


def test_auto_resolve_alerts():
    """Alerts auto-resolve when component recovers."""
    dash = HealthDashboard()
    dash.register_component("Agent", "agent")

    dash.report_health("Agent", "healthy")
    dash.report_health("Agent", "unhealthy")
    assert len(dash.get_alerts(active_only=True)) == 1

    dash.report_health("Agent", "healthy")
    assert len(dash.get_alerts(active_only=True)) == 0
    print("OK: auto resolve alerts")


def test_manual_resolve_alert():
    """Manually resolve an alert."""
    dash = HealthDashboard()
    dash.register_component("Agent", "agent")

    dash.report_health("Agent", "healthy")
    dash.report_health("Agent", "unhealthy")

    alerts = dash.get_alerts(active_only=True)
    assert len(alerts) == 1
    alert_id = alerts[0]["alert_id"]

    assert dash.resolve_alert(alert_id) is True
    assert len(dash.get_alerts(active_only=True)) == 0
    assert dash.resolve_alert(alert_id) is False  # Already resolved
    print("OK: manual resolve alert")


def test_get_components_filtered():
    """List components with filters."""
    dash = HealthDashboard()
    dash.register_component("Builder", "agent")
    dash.register_component("Tester", "agent")
    dash.register_component("EventBus", "service")

    dash.report_health("Builder", "healthy")
    dash.report_health("Tester", "unhealthy")
    dash.report_health("EventBus", "healthy")

    agents = dash.get_components(component_type="agent")
    assert len(agents) == 2

    healthy = dash.get_components(status="healthy")
    assert len(healthy) == 2

    unhealthy_agents = dash.get_components(component_type="agent", status="unhealthy")
    assert len(unhealthy_agents) == 1
    assert unhealthy_agents[0]["name"] == "Tester"
    print("OK: get components filtered")


def test_overview_healthy():
    """Overview when all components healthy."""
    dash = HealthDashboard()
    dash.register_component("A", "agent")
    dash.register_component("B", "service")

    dash.report_health("A", "healthy")
    dash.report_health("B", "healthy")

    overview = dash.get_overview()
    assert overview["system_status"] == "healthy"
    assert overview["total_components"] == 2
    assert overview["status_counts"]["healthy"] == 2
    assert overview["uptime_avg"] == 1.0
    print("OK: overview healthy")


def test_overview_degraded():
    """Overview when any component degraded."""
    dash = HealthDashboard()
    dash.register_component("A", "agent")
    dash.register_component("B", "service")

    dash.report_health("A", "healthy")
    dash.report_health("B", "degraded")

    overview = dash.get_overview()
    assert overview["system_status"] == "degraded"
    print("OK: overview degraded")


def test_overview_unhealthy():
    """Overview when any component unhealthy."""
    dash = HealthDashboard()
    dash.register_component("A", "agent")
    dash.register_component("B", "service")

    dash.report_health("A", "unhealthy")
    dash.report_health("B", "degraded")

    overview = dash.get_overview()
    assert overview["system_status"] == "unhealthy"
    print("OK: overview unhealthy")


def test_overview_empty():
    """Overview with no components."""
    dash = HealthDashboard()
    overview = dash.get_overview()
    assert overview["system_status"] == "unknown"
    assert overview["total_components"] == 0
    print("OK: overview empty")


def test_health_history():
    """Get health history for a component."""
    dash = HealthDashboard()
    dash.register_component("Agent", "agent")

    dash.report_health("Agent", "healthy")
    dash.report_health("Agent", "degraded")
    dash.report_health("Agent", "healthy")

    history = dash.get_health_history("Agent")
    assert len(history) == 3
    assert history[0]["status"] == "healthy"
    assert history[1]["status"] == "degraded"
    assert history[2]["status"] == "healthy"

    assert dash.get_health_history("nope") == []
    print("OK: health history")


def test_health_probe():
    """Register and run health probes."""
    dash = HealthDashboard()
    dash.register_component("DB", "service")

    dash.register_probe("DB", lambda: {"status": "healthy", "metrics": {"connections": 5}})

    results = dash.run_probes()
    assert results["DB"] == "healthy"

    comp = dash.get_component("DB")
    assert comp["status"] == "healthy"
    assert comp["metrics"]["connections"] == 5
    print("OK: health probe")


def test_probe_failure():
    """Failed probes mark component unhealthy."""
    dash = HealthDashboard()
    dash.register_component("DB", "service")

    dash.register_probe("DB", lambda: 1 / 0)

    results = dash.run_probes()
    assert results["DB"] == "unhealthy"

    comp = dash.get_component("DB")
    assert comp["status"] == "unhealthy"
    print("OK: probe failure")


def test_alerts_filter_severity():
    """Filter alerts by severity."""
    dash = HealthDashboard()
    dash.register_component("A", "agent")
    dash.register_component("B", "agent")

    dash.report_health("A", "healthy")
    dash.report_health("A", "degraded")   # Warning alert
    dash.report_health("B", "healthy")
    dash.report_health("B", "unhealthy")  # Critical alert

    warnings = dash.get_alerts(severity="warning")
    assert len(warnings) == 1

    criticals = dash.get_alerts(severity="critical")
    assert len(criticals) == 1
    print("OK: alerts filter severity")


def test_stats():
    """Stats are accurate."""
    dash = HealthDashboard()
    dash.register_component("A", "agent")
    dash.report_health("A", "healthy")
    dash.report_health("A", "unhealthy")

    stats = dash.get_stats()
    assert stats["total_components"] == 1
    assert stats["total_reports"] == 2
    assert stats["total_alerts"] == 1
    assert stats["active_alerts"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    dash = HealthDashboard()
    dash.register_component("A", "agent")
    dash.report_health("A", "healthy")

    dash.reset()
    assert dash.get_components() == []
    assert dash.get_alerts() == []
    stats = dash.get_stats()
    assert stats["total_components"] == 0
    print("OK: reset")


def main():
    print("=== Health Dashboard Tests ===\n")
    test_register_component()
    test_unregister()
    test_report_health()
    test_uptime_ratio()
    test_auto_alert_unhealthy()
    test_auto_alert_degraded()
    test_auto_resolve_alerts()
    test_manual_resolve_alert()
    test_get_components_filtered()
    test_overview_healthy()
    test_overview_degraded()
    test_overview_unhealthy()
    test_overview_empty()
    test_health_history()
    test_health_probe()
    test_probe_failure()
    test_alerts_filter_severity()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
