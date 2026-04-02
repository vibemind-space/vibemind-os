"""Test pipeline circuit analyzer."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_circuit_analyzer import PipelineCircuitAnalyzer


def test_register():
    """Register and retrieve stage."""
    ca = PipelineCircuitAnalyzer()
    sid = ca.register_stage("auth", tags=["critical"])
    assert sid.startswith("cst-")

    s = ca.get_stage("auth")
    assert s is not None
    assert s["name"] == "auth"
    assert s["status"] == "healthy"

    assert ca.remove_stage("auth") is True
    assert ca.remove_stage("auth") is False
    print("OK: register")


def test_invalid_register():
    """Invalid register rejected."""
    ca = PipelineCircuitAnalyzer()
    assert ca.register_stage("") == ""
    print("OK: invalid register")


def test_duplicate():
    """Duplicate name rejected."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")
    assert ca.register_stage("s1") == ""
    print("OK: duplicate")


def test_max_stages():
    """Max stages enforced."""
    ca = PipelineCircuitAnalyzer(max_stages=2)
    ca.register_stage("a")
    ca.register_stage("b")
    assert ca.register_stage("c") == ""
    print("OK: max stages")


def test_record_success():
    """Record success updates metrics."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")

    assert ca.record_success("s1", latency=10.0) is True
    s = ca.get_stage("s1")
    assert s["total_calls"] == 1
    assert s["avg_latency"] == 10.0
    assert s["status"] == "healthy"

    assert ca.record_success("nonexistent") is False
    print("OK: record success")


def test_record_failure():
    """Record failure updates metrics."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")

    assert ca.record_failure("s1", latency=5.0) is True
    s = ca.get_stage("s1")
    assert s["total_failures"] == 1
    assert s["consecutive_failures"] == 1

    assert ca.record_failure("nonexistent") is False
    print("OK: record failure")


def test_status_degraded():
    """Status becomes degraded on failure."""
    ca = PipelineCircuitAnalyzer(degraded_threshold=20.0)
    ca.register_stage("s1")

    # 1 success, 1 failure = 50% failure rate > 20% = failing
    ca.record_success("s1")
    ca.record_failure("s1")
    s = ca.get_stage("s1")
    assert s["status"] == "failing"
    print("OK: status degraded")


def test_status_open():
    """Status becomes open on consecutive failures."""
    ca = PipelineCircuitAnalyzer(failure_threshold=3)
    ca.register_stage("s1")

    ca.record_failure("s1")
    ca.record_failure("s1")
    ca.record_failure("s1")
    s = ca.get_stage("s1")
    assert s["status"] == "open"
    print("OK: status open")


def test_consecutive_reset():
    """Success resets consecutive failures."""
    ca = PipelineCircuitAnalyzer(failure_threshold=5)
    ca.register_stage("s1")

    ca.record_failure("s1")
    ca.record_failure("s1")
    ca.record_success("s1")
    s = ca.get_stage("s1")
    assert s["consecutive_failures"] == 0
    print("OK: consecutive reset")


def test_latency_tracking():
    """Latency metrics are tracked."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")

    ca.record_success("s1", latency=10.0)
    ca.record_success("s1", latency=20.0)
    ca.record_success("s1", latency=30.0)

    s = ca.get_stage("s1")
    assert s["min_latency"] == 10.0
    assert s["max_latency"] == 30.0
    assert s["avg_latency"] == 20.0
    print("OK: latency tracking")


def test_reset_stage():
    """Reset stage clears metrics."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")
    ca.record_failure("s1")

    assert ca.reset_stage("s1") is True
    s = ca.get_stage("s1")
    assert s["total_calls"] == 0
    assert s["status"] == "healthy"

    assert ca.reset_stage("nonexistent") is False
    print("OK: reset stage")


def test_get_failure_rate():
    """Get failure rate."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")
    ca.record_success("s1")
    ca.record_failure("s1")

    rate = ca.get_failure_rate("s1")
    assert abs(rate - 50.0) < 0.01

    assert ca.get_failure_rate("nonexistent") == 0.0
    print("OK: get failure rate")


def test_get_unhealthy():
    """Get unhealthy stages."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("healthy")
    ca.register_stage("sick")
    ca.record_failure("sick")

    unhealthy = ca.get_unhealthy()
    assert len(unhealthy) == 1
    assert unhealthy[0]["name"] == "sick"
    print("OK: get unhealthy")


def test_list_stages():
    """List stages with filters."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1", tags=["critical"])
    ca.register_stage("s2")
    ca.record_failure("s2")

    all_s = ca.list_stages()
    assert len(all_s) == 2

    by_tag = ca.list_stages(tag="critical")
    assert len(by_tag) == 1
    print("OK: list stages")


def test_status_change_callback():
    """Status change fires callback."""
    ca = PipelineCircuitAnalyzer(failure_threshold=2)
    fired = []
    ca.on_change("mon", lambda a, d: fired.append(a))

    ca.register_stage("s1")
    ca.record_failure("s1")
    ca.record_failure("s1")

    assert "status_changed" in fired
    print("OK: status change callback")


def test_history():
    """History tracking."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")
    ca.record_success("s1", latency=5.0)
    ca.record_failure("s1", latency=10.0)

    hist = ca.get_history()
    assert len(hist) == 2

    by_action = ca.get_history(action="call_success")
    assert len(by_action) == 1

    limited = ca.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callbacks():
    """Callback registration."""
    ca = PipelineCircuitAnalyzer()
    assert ca.on_change("mon", lambda a, d: None) is True
    assert ca.on_change("mon", lambda a, d: None) is False
    assert ca.remove_callback("mon") is True
    assert ca.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")
    ca.register_stage("s2")
    ca.record_success("s1")
    ca.record_failure("s2")

    stats = ca.get_stats()
    assert stats["current_stages"] == 2
    assert stats["total_registered"] == 2
    assert stats["total_calls"] == 2
    assert stats["total_failures"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ca = PipelineCircuitAnalyzer()
    ca.register_stage("s1")

    ca.reset()
    assert ca.list_stages() == []
    stats = ca.get_stats()
    assert stats["current_stages"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Circuit Analyzer Tests ===\n")
    test_register()
    test_invalid_register()
    test_duplicate()
    test_max_stages()
    test_record_success()
    test_record_failure()
    test_status_degraded()
    test_status_open()
    test_consecutive_reset()
    test_latency_tracking()
    test_reset_stage()
    test_get_failure_rate()
    test_get_unhealthy()
    test_list_stages()
    test_status_change_callback()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
