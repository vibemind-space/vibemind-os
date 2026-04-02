"""Test pipeline health reporter."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_health_reporter import PipelineHealthReporter


def test_register():
    """Register and retrieve component."""
    hr = PipelineHealthReporter()
    assert hr.register("database", tags=["core"]) is True

    c = hr.get_component("database")
    assert c is not None
    assert c["component"] == "database"
    assert c["current_status"] == "unknown"
    assert "core" in c["tags"]

    assert hr.unregister("database") is True
    assert hr.unregister("database") is False
    print("OK: register")


def test_invalid_register():
    """Invalid registration rejected."""
    hr = PipelineHealthReporter()
    assert hr.register("") is False
    print("OK: invalid register")


def test_duplicate():
    """Duplicate name rejected."""
    hr = PipelineHealthReporter()
    hr.register("db")
    assert hr.register("db") is False
    print("OK: duplicate")


def test_max_components():
    """Max components enforced."""
    hr = PipelineHealthReporter(max_components=2)
    hr.register("a")
    hr.register("b")
    assert hr.register("c") is False
    print("OK: max components")


def test_check_no_fn():
    """Check with no check_fn returns healthy."""
    hr = PipelineHealthReporter()
    hr.register("db")

    status = hr.check("db")
    assert status == "healthy"
    assert hr.get_component("db")["current_status"] == "healthy"
    print("OK: check no fn")


def test_check_bool_fn():
    """Check with bool-returning check_fn."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: True)
    assert hr.check("db") == "healthy"

    hr.register("cache", check_fn=lambda: False)
    assert hr.check("cache") == "unhealthy"
    print("OK: check bool fn")


def test_check_str_fn():
    """Check with string-returning check_fn."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: "degraded")
    assert hr.check("db") == "degraded"
    print("OK: check str fn")


def test_check_dict_fn():
    """Check with dict-returning check_fn."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: {
        "status": "degraded",
        "message": "high latency",
        "metrics": {"latency_ms": 500.0},
    })
    assert hr.check("db") == "degraded"
    print("OK: check dict fn")


def test_check_exception():
    """Check handles exceptions."""
    def bad_fn():
        raise RuntimeError("connection refused")

    hr = PipelineHealthReporter()
    hr.register("db", check_fn=bad_fn)
    assert hr.check("db") == "unhealthy"
    print("OK: check exception")


def test_check_nonexistent():
    """Check nonexistent returns None."""
    hr = PipelineHealthReporter()
    assert hr.check("nonexistent") is None
    print("OK: check nonexistent")


def test_check_all():
    """Check all components."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: True)
    hr.register("cache", check_fn=lambda: False)

    results = hr.check_all()
    assert results["db"] == "healthy"
    assert results["cache"] == "unhealthy"
    print("OK: check all")


def test_generate_report():
    """Generate health report."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: True)
    hr.register("cache", check_fn=lambda: "degraded")
    hr.check_all()

    report = hr.generate_report()
    assert report["total_components"] == 2
    assert report["healthy"] == 1
    assert report["degraded"] == 1
    assert report["overall"] == "degraded"
    assert "db" in report["components"]
    print("OK: generate report")


def test_report_overall_status():
    """Report overall status logic."""
    hr = PipelineHealthReporter()
    hr.register("a", check_fn=lambda: True)
    hr.register("b", check_fn=lambda: True)
    hr.check_all()
    assert hr.generate_report()["overall"] == "healthy"

    hr2 = PipelineHealthReporter()
    hr2.register("a", check_fn=lambda: True)
    hr2.register("b", check_fn=lambda: False)
    hr2.check_all()
    assert hr2.generate_report()["overall"] == "unhealthy"
    print("OK: report overall status")


def test_history():
    """Health check history."""
    hr = PipelineHealthReporter()
    hr.register("db")
    hr.check("db")
    hr.check("db")

    hist = hr.get_history()
    assert len(hist) == 2

    by_comp = hr.get_history(component="db")
    assert len(by_comp) == 2

    limited = hr.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_history_status_filter():
    """History filtered by status."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: True)
    hr.register("cache", check_fn=lambda: False)
    hr.check_all()

    healthy = hr.get_history(status="healthy")
    assert len(healthy) == 1
    unhealthy = hr.get_history(status="unhealthy")
    assert len(unhealthy) == 1
    print("OK: history status filter")


def test_list_components():
    """List components with filters."""
    hr = PipelineHealthReporter()
    hr.register("db", tags=["core"])
    hr.register("cache")
    hr.check_all()

    all_c = hr.list_components()
    assert len(all_c) == 2

    by_status = hr.list_components(status="healthy")
    assert len(by_status) == 2

    by_tag = hr.list_components(tag="core")
    assert len(by_tag) == 1
    print("OK: list components")


def test_get_unhealthy():
    """Get unhealthy components."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: True)
    hr.register("cache", check_fn=lambda: "degraded")
    hr.register("api", check_fn=lambda: False)
    hr.check_all()

    unhealthy = hr.get_unhealthy()
    assert len(unhealthy) == 2
    assert "cache" in unhealthy
    assert "api" in unhealthy
    print("OK: get unhealthy")


def test_is_all_healthy():
    """Check if all components healthy."""
    hr = PipelineHealthReporter()
    hr.register("db", check_fn=lambda: True)
    hr.register("cache", check_fn=lambda: True)
    hr.check_all()
    assert hr.is_all_healthy() is True

    hr.register("api", check_fn=lambda: False)
    hr.check_all()
    assert hr.is_all_healthy() is False
    print("OK: is all healthy")


def test_callback():
    """Callback fires on events."""
    hr = PipelineHealthReporter()
    fired = []
    hr.on_change("mon", lambda a, d: fired.append(a))

    hr.register("db")
    assert "component_registered" in fired

    hr.register("cache", check_fn=lambda: False)
    hr.check("cache")
    assert "health_degraded" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    hr = PipelineHealthReporter()
    assert hr.on_change("mon", lambda a, d: None) is True
    assert hr.on_change("mon", lambda a, d: None) is False
    assert hr.remove_callback("mon") is True
    assert hr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    hr = PipelineHealthReporter()
    hr.register("db")
    hr.register("cache")
    hr.check_all()
    hr.generate_report()

    stats = hr.get_stats()
    assert stats["current_components"] == 2
    assert stats["total_checks"] == 2
    assert stats["total_reports"] == 1
    assert stats["history_size"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    hr = PipelineHealthReporter()
    hr.register("db")
    hr.check("db")

    hr.reset()
    assert hr.list_components() == []
    stats = hr.get_stats()
    assert stats["current_components"] == 0
    assert stats["history_size"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Health Reporter Tests ===\n")
    test_register()
    test_invalid_register()
    test_duplicate()
    test_max_components()
    test_check_no_fn()
    test_check_bool_fn()
    test_check_str_fn()
    test_check_dict_fn()
    test_check_exception()
    test_check_nonexistent()
    test_check_all()
    test_generate_report()
    test_report_overall_status()
    test_history()
    test_history_status_filter()
    test_list_components()
    test_get_unhealthy()
    test_is_all_healthy()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
