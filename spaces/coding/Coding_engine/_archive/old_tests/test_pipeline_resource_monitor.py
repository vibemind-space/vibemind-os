"""Test pipeline resource monitor."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_resource_monitor import PipelineResourceMonitor


def test_register_resource():
    """Register and retrieve resource."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu_usage", component="worker",
                                resource_type="cpu", max_value=100,
                                unit="%", tags=["core"])
    assert rid.startswith("res-")

    r = rm.get_resource(rid)
    assert r is not None
    assert r["name"] == "cpu_usage"
    assert r["component"] == "worker"
    assert r["status"] == "normal"
    assert r["current_value"] == 0.0

    assert rm.remove_resource(rid) is True
    assert rm.remove_resource(rid) is False
    print("OK: register resource")


def test_invalid_resource():
    """Invalid resource rejected."""
    rm = PipelineResourceMonitor()
    assert rm.register_resource("") == ""
    assert rm.register_resource("x", resource_type="invalid") == ""
    print("OK: invalid resource")


def test_duplicate_name():
    """Duplicate name rejected."""
    rm = PipelineResourceMonitor()
    rm.register_resource("cpu")
    assert rm.register_resource("cpu") == ""
    print("OK: duplicate name")


def test_max_resources():
    """Max resources enforced."""
    rm = PipelineResourceMonitor(max_resources=2)
    rm.register_resource("a")
    rm.register_resource("b")
    assert rm.register_resource("c") == ""
    print("OK: max resources")


def test_record_sample():
    """Record and track samples."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("mem", resource_type="memory")

    sid = rm.record_sample(rid, 45.0)
    assert sid.startswith("smp-")
    assert rm.get_resource(rid)["current_value"] == 45.0
    assert rm.get_resource(rid)["status"] == "normal"
    print("OK: record sample")


def test_warning_threshold():
    """Warning threshold triggers."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu", threshold_warning=80.0,
                                threshold_critical=95.0)

    rm.record_sample(rid, 85.0)
    assert rm.get_resource(rid)["status"] == "warning"
    print("OK: warning threshold")


def test_critical_threshold():
    """Critical threshold triggers."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu", threshold_warning=80.0,
                                threshold_critical=95.0)

    rm.record_sample(rid, 98.0)
    assert rm.get_resource(rid)["status"] == "critical"
    print("OK: critical threshold")


def test_recovery():
    """Status returns to normal below thresholds."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu", threshold_warning=80.0,
                                threshold_critical=95.0)

    rm.record_sample(rid, 98.0)
    assert rm.get_resource(rid)["status"] == "critical"

    rm.record_sample(rid, 50.0)
    assert rm.get_resource(rid)["status"] == "normal"
    print("OK: recovery")


def test_get_samples():
    """Get sample history."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu")

    rm.record_sample(rid, 10.0)
    rm.record_sample(rid, 20.0)
    rm.record_sample(rid, 30.0)

    samples = rm.get_samples(rid)
    assert len(samples) == 3
    print("OK: get samples")


def test_resource_avg():
    """Get resource average."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu")

    rm.record_sample(rid, 10.0)
    rm.record_sample(rid, 20.0)
    rm.record_sample(rid, 30.0)

    avg = rm.get_resource_avg(rid)
    assert avg == 20.0
    print("OK: resource avg")


def test_get_by_name():
    """Get resource by name."""
    rm = PipelineResourceMonitor()
    rm.register_resource("my_resource")

    r = rm.get_resource_by_name("my_resource")
    assert r is not None
    assert r["name"] == "my_resource"
    assert rm.get_resource_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_resources():
    """List resources with filters."""
    rm = PipelineResourceMonitor()
    r1 = rm.register_resource("cpu", component="worker",
                               resource_type="cpu", tags=["core"])
    r2 = rm.register_resource("mem", component="api",
                               resource_type="memory",
                               threshold_warning=50.0)
    rm.record_sample(r2, 60.0)

    all_r = rm.list_resources()
    assert len(all_r) == 2

    by_component = rm.list_resources(component="worker")
    assert len(by_component) == 1

    by_type = rm.list_resources(resource_type="memory")
    assert len(by_type) == 1

    by_status = rm.list_resources(status="warning")
    assert len(by_status) == 1

    by_tag = rm.list_resources(tag="core")
    assert len(by_tag) == 1
    print("OK: list resources")


def test_get_alerts():
    """Get active alerts."""
    rm = PipelineResourceMonitor()
    r1 = rm.register_resource("cpu", threshold_warning=80.0)
    r2 = rm.register_resource("mem", threshold_critical=90.0)
    rm.record_sample(r1, 85.0)  # warning
    rm.record_sample(r2, 95.0)  # critical

    alerts = rm.get_alerts()
    assert len(alerts) == 2
    print("OK: get alerts")


def test_remove_cascades():
    """Remove resource removes samples."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu")
    rm.record_sample(rid, 50.0)

    rm.remove_resource(rid)
    assert rm.get_samples(rid) == []
    print("OK: remove cascades")


def test_callback():
    """Callback fires on threshold events."""
    rm = PipelineResourceMonitor()
    fired = []
    rm.on_change("mon", lambda a, d: fired.append(a))

    rid = rm.register_resource("cpu", threshold_warning=80.0,
                                threshold_critical=95.0)
    rm.record_sample(rid, 85.0)
    assert "resource_warning" in fired

    rm.record_sample(rid, 98.0)
    assert "resource_critical" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    rm = PipelineResourceMonitor()
    assert rm.on_change("mon", lambda a, d: None) is True
    assert rm.on_change("mon", lambda a, d: None) is False
    assert rm.remove_callback("mon") is True
    assert rm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu", threshold_warning=50.0,
                                threshold_critical=90.0)
    rm.record_sample(rid, 60.0)  # warning
    rm.record_sample(rid, 95.0)  # critical

    stats = rm.get_stats()
    assert stats["total_resources"] == 1
    assert stats["total_samples"] == 2
    assert stats["total_warnings"] == 1
    assert stats["total_criticals"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rm = PipelineResourceMonitor()
    rid = rm.register_resource("cpu")
    rm.record_sample(rid, 50.0)

    rm.reset()
    assert rm.list_resources() == []
    stats = rm.get_stats()
    assert stats["current_resources"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Resource Monitor Tests ===\n")
    test_register_resource()
    test_invalid_resource()
    test_duplicate_name()
    test_max_resources()
    test_record_sample()
    test_warning_threshold()
    test_critical_threshold()
    test_recovery()
    test_get_samples()
    test_resource_avg()
    test_get_by_name()
    test_list_resources()
    test_get_alerts()
    test_remove_cascades()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
