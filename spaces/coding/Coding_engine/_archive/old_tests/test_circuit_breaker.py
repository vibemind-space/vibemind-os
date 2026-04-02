"""Test circuit breaker pattern."""
import asyncio
import sys
sys.path.insert(0, ".")

from src.services.circuit_breaker import (
    CircuitBreaker, CircuitBreakerError, CircuitState,
    get_circuit_breaker, get_all_breaker_status, reset_circuit_breaker,
    circuit_protected,
)


async def test_closed_state_passes_through():
    """Normal operation: calls pass through in CLOSED state."""
    breaker = CircuitBreaker("test-svc-1", failure_threshold=3)
    assert breaker.state == CircuitState.CLOSED

    async with breaker:
        pass  # simulates successful call

    assert breaker.stats.successful_calls == 1
    assert breaker.stats.consecutive_failures == 0
    print("OK: CLOSED state passes through")


async def test_opens_after_threshold_failures():
    """Circuit opens after N consecutive failures."""
    breaker = CircuitBreaker("test-svc-2", failure_threshold=3, recovery_timeout=60)

    for i in range(3):
        try:
            async with breaker:
                raise ConnectionError(f"fail {i}")
        except ConnectionError:
            pass

    assert breaker.state == CircuitState.OPEN, f"Expected OPEN, got {breaker.state}"
    assert breaker.stats.consecutive_failures == 3

    # Next call should be rejected
    try:
        async with breaker:
            pass
        assert False, "Should have raised CircuitBreakerError"
    except CircuitBreakerError as e:
        assert e.service_name == "test-svc-2"
        assert breaker.stats.rejected_calls == 1

    print("OK: circuit opens after threshold failures")


async def test_half_open_recovery():
    """Circuit transitions OPEN -> HALF_OPEN -> CLOSED on success."""
    breaker = CircuitBreaker(
        "test-svc-3",
        failure_threshold=2,
        recovery_timeout=0.1,  # Very short for testing
        success_threshold=2,
    )

    # Trip the circuit
    for i in range(2):
        try:
            async with breaker:
                raise ConnectionError("fail")
        except ConnectionError:
            pass

    assert breaker.state == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(0.15)
    assert breaker.state == CircuitState.HALF_OPEN

    # Successful probe calls should close it
    async with breaker:
        pass  # success 1
    async with breaker:
        pass  # success 2

    assert breaker.state == CircuitState.CLOSED
    print("OK: HALF_OPEN recovers to CLOSED on success")


async def test_half_open_failure_reopens():
    """Failure in HALF_OPEN immediately reopens the circuit."""
    breaker = CircuitBreaker(
        "test-svc-4",
        failure_threshold=2,
        recovery_timeout=0.1,
    )

    # Trip it
    for i in range(2):
        try:
            async with breaker:
                raise ConnectionError("fail")
        except ConnectionError:
            pass

    assert breaker.state == CircuitState.OPEN

    # Wait for half-open
    await asyncio.sleep(0.15)
    assert breaker.state == CircuitState.HALF_OPEN

    # Fail in half-open
    try:
        async with breaker:
            raise ConnectionError("still failing")
    except ConnectionError:
        pass

    assert breaker._state == CircuitState.OPEN
    print("OK: HALF_OPEN failure reopens circuit")


async def test_decorator():
    """@circuit_protected decorator works."""
    call_count = 0

    @circuit_protected("test-svc-5", failure_threshold=2, recovery_timeout=60)
    async def risky_call():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionError("boom")
        return "ok"

    # Fail twice to trip
    for _ in range(2):
        try:
            await risky_call()
        except ConnectionError:
            pass

    # Next call should be rejected by circuit
    try:
        await risky_call()
        assert False, "Should have raised"
    except CircuitBreakerError:
        pass

    assert call_count == 2  # Only 2 real calls, 3rd was rejected
    print("OK: decorator works")


async def test_fallback():
    """Circuit breaker with fallback returns fallback value when open."""
    @circuit_protected(
        "test-svc-6",
        failure_threshold=1,
        recovery_timeout=60,
        fallback=lambda: {"status": "unavailable"},
    )
    async def flaky_service():
        raise ConnectionError("down")

    # First call fails and trips the circuit
    try:
        await flaky_service()
    except ConnectionError:
        pass

    # Second call should return fallback
    result = await flaky_service()
    assert result == {"status": "unavailable"}
    print("OK: fallback works when circuit is open")


async def test_registry():
    """Global registry creates singletons and reports status."""
    b1 = get_circuit_breaker("registry-test")
    b2 = get_circuit_breaker("registry-test")
    assert b1 is b2, "Should be same instance"

    status = get_all_breaker_status()
    assert "registry-test" in status
    assert status["registry-test"]["state"] == "closed"

    # Force reset
    reset_circuit_breaker("registry-test")
    print("OK: registry works")


async def test_to_dict():
    """Circuit breaker status serializes correctly."""
    breaker = CircuitBreaker("dict-test", failure_threshold=5)
    async with breaker:
        pass

    d = breaker.to_dict()
    assert d["service"] == "dict-test"
    assert d["state"] == "closed"
    assert d["stats"]["successful"] == 1
    assert d["config"]["failure_threshold"] == 5
    print("OK: to_dict serialization works")


async def main():
    print("=== Circuit Breaker Tests ===\n")
    await test_closed_state_passes_through()
    await test_opens_after_threshold_failures()
    await test_half_open_recovery()
    await test_half_open_failure_reopens()
    await test_decorator()
    await test_fallback()
    await test_registry()
    await test_to_dict()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
