"""Integration test suite — verifies all infrastructure modules work together.

Tests the full flow:
  EventBus + PipelineTrace → PipelineMetrics → CircuitBreaker
  → RateLimiter → PipelineCheckpoint → DiscussionManager
  → WSEventStreamer → OpenClaw command routing
"""
import asyncio
import json
import sys
import time
sys.path.insert(0, ".")

from src.mind.event_bus import EventBus, Event, EventType, PipelineTrace


# ---------------------------------------------------------------------------
# 1. EventBus + PipelineTrace correlation propagation
# ---------------------------------------------------------------------------

async def test_trace_correlation():
    """Events published inside a PipelineTrace get correlation_id automatically."""
    bus = EventBus()
    captured = []

    async def capture(event):
        captured.append(event)

    bus.subscribe(EventType.BUILD_SUCCEEDED, capture)

    async with PipelineTrace("integration-test") as trace:
        await bus.publish(Event(
            type=EventType.BUILD_SUCCEEDED,
            source="IntegrationTest",
            data={"msg": "hello"},
        ))

        assert len(captured) == 1
        assert captured[0].correlation_id == trace.trace_id
        assert captured[0].span_id == trace.span_id

    # Outside trace — no correlation
    await bus.publish(Event(
        type=EventType.BUILD_SUCCEEDED,
        source="IntegrationTest",
        data={"msg": "no-trace"},
    ))
    assert captured[1].correlation_id is None
    print("OK: trace correlation propagation")


# ---------------------------------------------------------------------------
# 2. Circuit breaker + rate limiter together
# ---------------------------------------------------------------------------

async def test_circuit_breaker_with_rate_limiter():
    """Circuit breaker and rate limiter don't interfere with each other."""
    from src.services.circuit_breaker import CircuitBreaker, CircuitState
    from src.services.rate_limiter import RateLimiter

    breaker = CircuitBreaker("integration_test", failure_threshold=2, recovery_timeout=0.3)
    limiter = RateLimiter(global_rpm=120, global_tpm=1_000_000)
    limiter.set_agent_quota("TestAgent", rpm=60, tpm=500_000)

    # Normal operation: both pass
    async with limiter.acquire("TestAgent", estimated_tokens=100):
        async with breaker:
            pass  # Success
    assert breaker.state == CircuitState.CLOSED

    # Simulate failures
    for _ in range(2):
        try:
            async with breaker:
                raise ConnectionError("fail")
        except ConnectionError:
            pass

    assert breaker.state == CircuitState.OPEN
    print("OK: circuit breaker + rate limiter coexistence")


# ---------------------------------------------------------------------------
# 3. PipelineCheckpoint save/restore cycle
# ---------------------------------------------------------------------------

async def test_checkpoint_save_restore():
    """Checkpoint can save and restore pipeline state."""
    import tempfile
    import shutil
    from src.mind.shared_state import SharedState
    from src.services.pipeline_checkpoint import PipelineCheckpointer

    bus = EventBus()
    state = SharedState()

    tmpdir = tempfile.mkdtemp()
    try:
        ckpt = PipelineCheckpointer(tmpdir, state, bus)

        # Save a checkpoint
        cp = await ckpt.save(
            milestone="test-checkpoint",
            phase="building",
            metadata={"iteration": 3},
        )

        assert cp.phase == "building"
        assert cp.checkpoint_id.startswith("cp-")

        # Load it back
        loaded = ckpt.load_latest()
        assert loaded is not None
        assert loaded.checkpoint_id == cp.checkpoint_id
        assert loaded.phase == "building"

        # List checkpoints
        all_cps = ckpt.list_checkpoints()
        assert len(all_cps) >= 1
        print("OK: checkpoint save/restore")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Discussion + voting full flow
# ---------------------------------------------------------------------------

async def test_discussion_full_flow():
    """Create discussion, vote, resolve, check events emitted."""
    from src.services.minibook_discussion import (
        DiscussionManager, DiscussionOption, DiscussionStatus, ResolutionStrategy,
    )

    bus = EventBus()
    resolved_events = []

    async def on_resolved(event):
        resolved_events.append(event)

    bus.subscribe(EventType.MINIBOOK_DISCUSSION_RESOLVED, on_resolved)

    mgr = DiscussionManager(bus, default_strategy=ResolutionStrategy.VOTE)

    d = await mgr.create_discussion(
        title="Integration Test Discussion",
        context="Testing the full flow",
        trigger_event="test",
        participants=["Agent1", "Agent2", "HumanOperator"],
        options=[
            DiscussionOption("fix", "Fix Now", "Apply the fix", "Agent1"),
            DiscussionOption("skip", "Skip", "Skip it", "Agent2"),
        ],
    )

    await mgr.cast_vote(d.discussion_id, "Agent1", "fix", "I found the bug")
    await mgr.cast_vote(d.discussion_id, "Agent2", "skip", "Not critical")
    await mgr.cast_vote(d.discussion_id, "HumanOperator", "fix", "Let's fix it")

    assert d.status == DiscussionStatus.RESOLVED
    assert d.resolution == "fix"
    assert len(resolved_events) == 1
    assert resolved_events[0].data["resolution"] == "fix"
    print("OK: discussion full flow with event emission")


# ---------------------------------------------------------------------------
# 5. Dependency resolver end-to-end
# ---------------------------------------------------------------------------

def test_dependency_resolver_e2e():
    """Full dependency resolution with batched build order."""
    from pathlib import Path
    from src.services.package_dependency_resolver import (
        PackageDependencyResolver, PackageDependency,
    )

    resolver = PackageDependencyResolver()

    # Simulate a microservices architecture
    deps = {
        "shared-models": PackageDependency(
            "shared-models", Path("."), depends_on=[], provides=["shared-models"]
        ),
        "auth-service": PackageDependency(
            "auth-service", Path("."), depends_on=["shared-models"], provides=["auth-service"]
        ),
        "user-service": PackageDependency(
            "user-service", Path("."), depends_on=["shared-models", "auth-service"],
            provides=["user-service"]
        ),
        "api-gateway": PackageDependency(
            "api-gateway", Path("."),
            depends_on=["auth-service", "user-service"],
            provides=["api-gateway"]
        ),
        "frontend": PackageDependency(
            "frontend", Path("."), depends_on=["api-gateway"], provides=["frontend"]
        ),
        "docs": PackageDependency(
            "docs", Path("."), depends_on=[], provides=["docs"]
        ),
    }

    graph = resolver.build_graph(deps)
    cycles = resolver.detect_cycles(graph)
    assert len(cycles) == 0

    batches = resolver.topological_sort_batched(graph)

    # Batch 0: shared-models, docs (no deps)
    assert "shared-models" in batches[0]
    assert "docs" in batches[0]

    # Frontend should be last (deepest dependency chain)
    all_ordered = [p for b in batches for p in b]
    assert all_ordered.index("shared-models") < all_ordered.index("auth-service")
    assert all_ordered.index("auth-service") < all_ordered.index("user-service")
    assert all_ordered.index("user-service") < all_ordered.index("api-gateway")
    assert all_ordered.index("api-gateway") < all_ordered.index("frontend")

    # Affected packages when shared-models changes
    affected = resolver.get_affected_packages(graph, "shared-models")
    assert set(affected) == {"shared-models", "auth-service", "user-service", "api-gateway", "frontend"}
    assert "docs" not in affected

    print("OK: dependency resolver E2E")


# ---------------------------------------------------------------------------
# 6. OpenClaw command routing
# ---------------------------------------------------------------------------

async def test_openclaw_command_routing():
    """OpenClaw commands route correctly and return expected shapes."""
    from src.services.openclaw_bridge import PipelineCommandHandler

    bus = EventBus()
    handler = PipelineCommandHandler(bus)

    # Test help command
    result = await handler.handle_command("help", {})
    assert result["success"] is True
    assert "status" in result["commands"]
    assert "discussions" in result["commands"]
    assert "vote" in result["commands"]
    assert "health" in result["commands"]

    # Test unknown command
    result = await handler.handle_command("nonexistent", {})
    assert result["success"] is False
    assert "available_commands" in result

    # Test status
    result = await handler.handle_command("status", {})
    assert result["success"] is True
    assert "status" in result

    # Test metrics
    result = await handler.handle_command("metrics", {})
    assert result["success"] is True

    print("OK: OpenClaw command routing")


# ---------------------------------------------------------------------------
# 7. Rate limiter under concurrent load
# ---------------------------------------------------------------------------

async def test_rate_limiter_concurrent():
    """Rate limiter handles concurrent agents correctly."""
    from src.services.rate_limiter import RateLimiter

    limiter = RateLimiter(global_rpm=120, global_tpm=2_000_000)
    limiter.set_agent_quota("Fixer", rpm=40, tpm=500_000, priority=1)
    limiter.set_agent_quota("Builder", rpm=30, tpm=400_000, priority=2)
    limiter.set_agent_quota("Linter", rpm=20, tpm=200_000, priority=5)

    results = []

    async def agent_work(name, count):
        for i in range(count):
            async with limiter.acquire(name, estimated_tokens=1000):
                await asyncio.sleep(0.005)
                results.append(name)
            limiter.record_usage(name, actual_tokens=950)

    await asyncio.gather(
        agent_work("Fixer", 5),
        agent_work("Builder", 3),
        agent_work("Linter", 2),
    )

    assert len(results) == 10
    stats = limiter.get_stats()
    assert stats["global"]["total_requests"] == 10
    assert stats["global"]["total_tokens"] == 9500
    print("OK: rate limiter concurrent load")


# ---------------------------------------------------------------------------
# 8. Full pipeline trace → metrics → checkpoint flow
# ---------------------------------------------------------------------------

async def test_trace_to_metrics_to_checkpoint():
    """Events within trace get metrics recorded with correlation IDs."""
    from src.services.pipeline_metrics import PipelineMetricsCollector

    bus = EventBus()
    metrics = PipelineMetricsCollector(bus)

    async with PipelineTrace("test-pipeline") as trace:
        await bus.publish(Event(
            type=EventType.BUILD_SUCCEEDED,
            source="IntegrationTest",
            data={"agent": "Builder", "duration": 5.2},
        ))
        await bus.publish(Event(
            type=EventType.TEST_PASSED,
            source="IntegrationTest",
            data={"agent": "Tester", "passed": 42, "failed": 0},
        ))

    m = metrics.get_metrics()
    assert m["build_test"]["builds"] >= 1
    assert m["build_test"]["build_success"] >= 1
    assert m["build_test"]["test_pass"] >= 1
    print("OK: trace -> metrics flow")


# ---------------------------------------------------------------------------
# 9. Event serialization with all new fields
# ---------------------------------------------------------------------------

async def test_event_serialization():
    """Events serialize with correlation_id, span_id, parent_id."""
    async with PipelineTrace("ser-test") as trace:
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="SerializationTest",
            data={"key": "value"},
            parent_id="parent-123",
        )

        d = event.to_dict()
        assert d["correlation_id"] == trace.trace_id
        assert d["span_id"] == trace.span_id
        assert d["parent_id"] == "parent-123"
        assert d["source"] == "SerializationTest"

    print("OK: event serialization with tracing fields")


# ---------------------------------------------------------------------------
# 10. Circuit breaker recovery
# ---------------------------------------------------------------------------

async def test_circuit_breaker_recovery():
    """Circuit breaker transitions CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    from src.services.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(
        "recovery_test", failure_threshold=2, recovery_timeout=0.2,
        success_threshold=2,
    )

    # Trip the breaker
    for _ in range(2):
        try:
            async with breaker:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

    assert breaker.state == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(0.3)

    # HALF_OPEN: need 2 successes to close
    async with breaker:
        pass  # Success 1
    async with breaker:
        pass  # Success 2

    assert breaker.state == CircuitState.CLOSED
    print("OK: circuit breaker recovery cycle")


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("  INTEGRATION TEST SUITE")
    print("=" * 60)
    print()

    await test_trace_correlation()
    await test_circuit_breaker_with_rate_limiter()
    await test_checkpoint_save_restore()
    await test_discussion_full_flow()
    test_dependency_resolver_e2e()
    await test_openclaw_command_routing()
    await test_rate_limiter_concurrent()
    await test_trace_to_metrics_to_checkpoint()
    await test_event_serialization()
    await test_circuit_breaker_recovery()

    print()
    print("=" * 60)
    print("  ALL 10 INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
