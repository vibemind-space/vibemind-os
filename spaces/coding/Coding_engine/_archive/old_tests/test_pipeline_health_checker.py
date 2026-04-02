"""Test pipeline health checker."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_health_checker import PipelineHealthChecker


def test_register_check():
    """Register and retrieve check."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("db_check", component="database",
                             interval_ms=10000, failure_threshold=3,
                             tags=["core"])
    assert cid.startswith("hc-")

    c = hc.get_check(cid)
    assert c is not None
    assert c["name"] == "db_check"
    assert c["component"] == "database"
    assert c["status"] == "unknown"
    assert c["enabled"] is True

    assert hc.remove_check(cid) is True
    assert hc.remove_check(cid) is False
    print("OK: register check")


def test_invalid_check():
    """Invalid check rejected."""
    hc = PipelineHealthChecker()
    assert hc.register_check("") == ""
    print("OK: invalid check")


def test_duplicate_name():
    """Duplicate name rejected."""
    hc = PipelineHealthChecker()
    hc.register_check("db")
    assert hc.register_check("db") == ""
    print("OK: duplicate name")


def test_max_checks():
    """Max checks enforced."""
    hc = PipelineHealthChecker(max_checks=2)
    hc.register_check("a")
    hc.register_check("b")
    assert hc.register_check("c") == ""
    print("OK: max checks")


def test_enable_disable():
    """Enable and disable check."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test")

    assert hc.disable_check(cid) is True
    assert hc.get_check(cid)["enabled"] is False
    assert hc.disable_check(cid) is False

    assert hc.enable_check(cid) is True
    assert hc.get_check(cid)["enabled"] is True
    assert hc.enable_check(cid) is False
    print("OK: enable disable")


def test_run_check_pass():
    """Run check with pass."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test")

    rid = hc.run_check(cid, passed=True, duration_ms=5.0, message="OK")
    assert rid.startswith("cr-")

    c = hc.get_check(cid)
    assert c["status"] == "healthy"
    assert c["last_result"] is True
    assert c["consecutive_failures"] == 0
    print("OK: run check pass")


def test_run_check_degraded():
    """Check becomes degraded on failure below threshold."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test", failure_threshold=3)

    hc.run_check(cid, passed=False)
    assert hc.get_check(cid)["status"] == "degraded"
    assert hc.get_check(cid)["consecutive_failures"] == 1
    print("OK: run check degraded")


def test_run_check_unhealthy():
    """Check becomes unhealthy after threshold failures."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test", failure_threshold=2)

    hc.run_check(cid, passed=False)
    assert hc.get_check(cid)["status"] == "degraded"

    hc.run_check(cid, passed=False)
    assert hc.get_check(cid)["status"] == "unhealthy"
    print("OK: run check unhealthy")


def test_recovery():
    """Check recovers after pass."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test", failure_threshold=1)

    hc.run_check(cid, passed=False)
    assert hc.get_check(cid)["status"] == "unhealthy"

    hc.run_check(cid, passed=True)
    assert hc.get_check(cid)["status"] == "healthy"
    assert hc.get_check(cid)["consecutive_failures"] == 0
    print("OK: recovery")


def test_get_check_results():
    """Get check results."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test")

    hc.run_check(cid, passed=True)
    hc.run_check(cid, passed=False, message="timeout")

    results = hc.get_check_results(cid)
    assert len(results) == 2
    assert results[0]["passed"] is True
    assert results[1]["passed"] is False
    print("OK: get check results")


def test_get_by_name():
    """Get check by name."""
    hc = PipelineHealthChecker()
    hc.register_check("my_check")

    c = hc.get_check_by_name("my_check")
    assert c is not None
    assert c["name"] == "my_check"
    assert hc.get_check_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_checks():
    """List checks with filters."""
    hc = PipelineHealthChecker()
    c1 = hc.register_check("a", component="db", tags=["core"])
    hc.run_check(c1, passed=True)
    c2 = hc.register_check("b", component="api")
    hc.disable_check(c2)

    all_c = hc.list_checks()
    assert len(all_c) == 2

    by_status = hc.list_checks(status="healthy")
    assert len(by_status) == 1

    by_component = hc.list_checks(component="db")
    assert len(by_component) == 1

    by_enabled = hc.list_checks(enabled=False)
    assert len(by_enabled) == 1

    by_tag = hc.list_checks(tag="core")
    assert len(by_tag) == 1
    print("OK: list checks")


def test_overall_health():
    """Get overall health."""
    hc = PipelineHealthChecker()
    c1 = hc.register_check("a")
    hc.run_check(c1, passed=True)
    c2 = hc.register_check("b")
    hc.run_check(c2, passed=True)

    h = hc.get_overall_health()
    assert h["overall"] == "healthy"
    assert h["healthy"] == 2

    # Make one unhealthy
    hc2 = PipelineHealthChecker()
    c3 = hc2.register_check("x", failure_threshold=1)
    hc2.run_check(c3, passed=False)
    assert hc2.get_overall_health()["overall"] == "unhealthy"
    print("OK: overall health")


def test_remove_cascades():
    """Remove check removes results."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test")
    hc.run_check(cid, passed=True)

    hc.remove_check(cid)
    assert hc.get_check_results(cid) == []
    print("OK: remove cascades")


def test_unhealthy_callback():
    """Callback fires when component becomes unhealthy."""
    hc = PipelineHealthChecker()
    fired = []
    hc.on_change("mon", lambda a, d: fired.append(a))

    cid = hc.register_check("test", failure_threshold=1)
    hc.run_check(cid, passed=False)
    assert "component_unhealthy" in fired
    print("OK: unhealthy callback")


def test_callbacks():
    """Callback registration."""
    hc = PipelineHealthChecker()
    assert hc.on_change("mon", lambda a, d: None) is True
    assert hc.on_change("mon", lambda a, d: None) is False
    assert hc.remove_callback("mon") is True
    assert hc.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test")
    hc.run_check(cid, passed=True)
    hc.run_check(cid, passed=False)

    stats = hc.get_stats()
    assert stats["total_checks_created"] == 1
    assert stats["total_runs"] == 2
    assert stats["total_passes"] == 1
    assert stats["total_failures"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    hc = PipelineHealthChecker()
    cid = hc.register_check("test")
    hc.run_check(cid, passed=True)

    hc.reset()
    assert hc.list_checks() == []
    stats = hc.get_stats()
    assert stats["current_checks"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Health Checker Tests ===\n")
    test_register_check()
    test_invalid_check()
    test_duplicate_name()
    test_max_checks()
    test_enable_disable()
    test_run_check_pass()
    test_run_check_degraded()
    test_run_check_unhealthy()
    test_recovery()
    test_get_check_results()
    test_get_by_name()
    test_list_checks()
    test_overall_health()
    test_remove_cascades()
    test_unhealthy_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
