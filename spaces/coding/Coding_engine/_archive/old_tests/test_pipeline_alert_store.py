"""Test pipeline alert store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_alert_store import PipelineAlertStore


def test_create_alert():
    als = PipelineAlertStore()
    aid = als.create_alert("deploy", "threshold", "critical", "CPU > 90%", tags=["ops"])
    assert len(aid) > 0
    a = als.get_alert(aid)
    assert a is not None
    assert a["status"] == "open"
    assert a["severity"] == "critical"
    print("OK: create alert")


def test_acknowledge_alert():
    als = PipelineAlertStore()
    aid = als.create_alert("deploy", "threshold", "warning", "Memory high")
    assert als.acknowledge_alert(aid, "ops-team") is True
    a = als.get_alert(aid)
    assert a["acknowledged_by"] == "ops-team"
    print("OK: acknowledge alert")


def test_resolve_alert():
    als = PipelineAlertStore()
    aid = als.create_alert("deploy", "error", "critical", "Deployment failed")
    assert als.resolve_alert(aid) is True
    a = als.get_alert(aid)
    assert a["status"] == "resolved"
    print("OK: resolve alert")


def test_get_open_alerts():
    als = PipelineAlertStore()
    aid1 = als.create_alert("deploy", "threshold", "critical", "Alert 1")
    aid2 = als.create_alert("deploy", "error", "warning", "Alert 2")
    als.create_alert("test", "threshold", "info", "Alert 3")
    als.resolve_alert(aid2)
    open_alerts = als.get_open_alerts(pipeline_name="deploy")
    assert len(open_alerts) == 1
    all_open = als.get_open_alerts()
    assert len(all_open) == 2  # aid1 + alert3
    print("OK: get open alerts")


def test_get_alert_history():
    als = PipelineAlertStore()
    als.create_alert("deploy", "threshold", "critical", "Alert 1")
    als.create_alert("deploy", "error", "warning", "Alert 2")
    history = als.get_alert_history(pipeline_name="deploy")
    assert len(history) == 2
    print("OK: get alert history")


def test_get_alert_summary():
    als = PipelineAlertStore()
    aid1 = als.create_alert("deploy", "threshold", "critical", "A1")
    aid2 = als.create_alert("deploy", "error", "warning", "A2")
    als.acknowledge_alert(aid1, "ops")
    als.resolve_alert(aid2)
    summary = als.get_alert_summary()
    assert summary["total"] == 2
    print("OK: get alert summary")


def test_list_pipelines_with_alerts():
    als = PipelineAlertStore()
    als.create_alert("deploy", "threshold", "critical", "A1")
    als.create_alert("test", "error", "warning", "A2")
    pipelines = als.list_pipelines_with_alerts()
    assert "deploy" in pipelines
    assert "test" in pipelines
    print("OK: list pipelines with alerts")


def test_purge():
    als = PipelineAlertStore()
    aid = als.create_alert("deploy", "threshold", "critical", "A1")
    als.resolve_alert(aid)  # purge only removes resolved alerts
    import time
    time.sleep(0.01)
    count = als.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    als = PipelineAlertStore()
    fired = []
    als.on_change("mon", lambda a, d: fired.append(a))
    als.create_alert("deploy", "threshold", "critical", "A1")
    assert len(fired) >= 1
    assert als.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    als = PipelineAlertStore()
    als.create_alert("deploy", "threshold", "critical", "A1")
    stats = als.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    als = PipelineAlertStore()
    als.create_alert("deploy", "threshold", "critical", "A1")
    als.reset()
    assert als.list_pipelines_with_alerts() == []
    print("OK: reset")


def main():
    print("=== Pipeline Alert Store Tests ===\n")
    test_create_alert()
    test_acknowledge_alert()
    test_resolve_alert()
    test_get_open_alerts()
    test_get_alert_history()
    test_get_alert_summary()
    test_list_pipelines_with_alerts()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
