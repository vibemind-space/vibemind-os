"""Test pipeline circuit breaker -- unit tests."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_circuit_breaker import PipelineCircuitBreaker


def test_create_circuit():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("api_svc", failure_threshold=3, recovery_timeout_ms=100.0)
    assert cid.startswith("cb-") or cid.startswith("pcb-")
    c = cb.get_circuit(cid)
    assert c is not None
    assert c["name"] == "api_svc"
    assert c["state"] == "closed"
    print("OK: create circuit")


def test_success_keeps_closed():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("svc", failure_threshold=3)
    cb.record_success(cid)
    cb.record_success(cid)
    c = cb.get_circuit(cid)
    assert c["state"] == "closed"
    print("OK: success keeps closed")


def test_failures_open_circuit():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("svc", failure_threshold=3)
    cb.record_failure(cid)
    cb.record_failure(cid)
    cb.record_failure(cid)
    c = cb.get_circuit(cid)
    assert c["state"] == "open"
    assert cb.allow_call(cid) is False
    print("OK: failures open circuit")


def test_half_open_recovery():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("svc", failure_threshold=2, recovery_timeout_ms=50.0, half_open_max_calls=1)
    cb.record_failure(cid)
    cb.record_failure(cid)
    assert cb.get_circuit(cid)["state"] == "open"
    time.sleep(0.06)
    assert cb.allow_call(cid) is True  # should transition to half_open
    cb.record_success(cid)
    c = cb.get_circuit(cid)
    assert c["state"] == "closed"
    print("OK: half open recovery")


def test_half_open_failure_reopens():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("svc", failure_threshold=2, recovery_timeout_ms=50.0, half_open_max_calls=3)
    cb.record_failure(cid)
    cb.record_failure(cid)
    time.sleep(0.06)
    cb.allow_call(cid)  # trigger half_open
    cb.record_failure(cid)  # should reopen
    c = cb.get_circuit(cid)
    assert c["state"] == "open"
    print("OK: half open failure reopens")


def test_force_open():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("svc")
    assert cb.force_open(cid) is True
    assert cb.get_circuit(cid)["state"] == "open"
    print("OK: force open")


def test_force_close():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("svc", failure_threshold=2)
    cb.record_failure(cid)
    cb.record_failure(cid)
    assert cb.force_close(cid) is True
    c = cb.get_circuit(cid)
    assert c["state"] == "closed"
    print("OK: force close")


def test_get_open_circuits():
    cb = PipelineCircuitBreaker()
    cid1 = cb.create_circuit("s1", failure_threshold=1)
    cid2 = cb.create_circuit("s2", failure_threshold=1)
    cb.create_circuit("s3")
    cb.record_failure(cid1)
    cb.record_failure(cid2)
    opens = cb.get_open_circuits()
    assert len(opens) == 2
    print("OK: get open circuits")


def test_list_circuits():
    cb = PipelineCircuitBreaker()
    cb.create_circuit("s1")
    cb.create_circuit("s2")
    assert len(cb.list_circuits()) == 2
    print("OK: list circuits")


def test_remove_circuit():
    cb = PipelineCircuitBreaker()
    cid = cb.create_circuit("s1")
    assert cb.remove_circuit(cid) is True
    assert cb.remove_circuit(cid) is False
    print("OK: remove circuit")


def test_callbacks():
    cb = PipelineCircuitBreaker()
    fired = []
    cb.on_change("mon", lambda a, d: fired.append(a))
    cb.create_circuit("s1")
    assert len(fired) >= 1
    assert cb.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cb = PipelineCircuitBreaker()
    cb.create_circuit("s1")
    stats = cb.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cb = PipelineCircuitBreaker()
    cb.create_circuit("s1")
    cb.reset()
    assert cb.list_circuits() == []
    print("OK: reset")


def main():
    print("=== Pipeline Circuit Breaker Tests ===\n")
    test_create_circuit()
    test_success_keeps_closed()
    test_failures_open_circuit()
    test_half_open_recovery()
    test_half_open_failure_reopens()
    test_force_open()
    test_force_close()
    test_get_open_circuits()
    test_list_circuits()
    test_remove_circuit()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
