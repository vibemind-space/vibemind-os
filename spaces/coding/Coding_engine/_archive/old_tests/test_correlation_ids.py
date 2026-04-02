"""Test correlation ID propagation through the event system."""
import asyncio
import sys
sys.path.insert(0, ".")

from src.mind.event_bus import (
    Event, EventType, EventBus, PipelineTrace,
    generate_trace_id, generate_span_id,
    get_current_correlation_id, set_current_correlation_id,
)


async def test_trace_id_generation():
    """Test trace and span ID format."""
    tid = generate_trace_id()
    sid = generate_span_id()
    assert tid.startswith("t-"), f"Expected t- prefix, got {tid}"
    assert sid.startswith("s-"), f"Expected s- prefix, got {sid}"
    assert len(tid) == 10, f"Expected 10 chars, got {len(tid)}"
    assert len(sid) == 8, f"Expected 8 chars, got {len(sid)}"
    print(f"OK: trace_id={tid}, span_id={sid}")


async def test_event_inherits_correlation_from_context():
    """Events should auto-inherit correlation_id from PipelineTrace context."""
    events_received = []

    bus = EventBus()
    bus.subscribe(EventType.BUILD_STARTED, lambda e: events_received.append(e))

    # Without trace context, correlation_id should be None
    evt1 = Event(type=EventType.BUILD_STARTED, source="test")
    assert evt1.correlation_id is None, "Should be None outside trace context"

    # Within a PipelineTrace, events should auto-get the trace's correlation_id
    async with PipelineTrace("test-pipeline") as trace:
        evt2 = Event(type=EventType.BUILD_STARTED, source="test")
        assert evt2.correlation_id == trace.trace_id, (
            f"Expected {trace.trace_id}, got {evt2.correlation_id}"
        )
        assert evt2.span_id == trace.span_id, (
            f"Expected {trace.span_id}, got {evt2.span_id}"
        )

        # Publish via bus should also inherit
        await bus.publish(evt2)
        assert len(events_received) == 1
        assert events_received[0].correlation_id == trace.trace_id

    # After exiting trace context, correlation_id should be None again
    evt3 = Event(type=EventType.BUILD_STARTED, source="test")
    assert evt3.correlation_id is None, "Should be None after exiting trace context"
    print(f"OK: correlation_id auto-propagation works (trace={trace.trace_id})")


async def test_nested_traces():
    """Nested PipelineTrace should create independent trace IDs."""
    async with PipelineTrace("outer") as outer:
        evt_outer = Event(type=EventType.PIPELINE_STARTED, source="test")
        assert evt_outer.correlation_id == outer.trace_id

        async with PipelineTrace("inner", parent_trace=outer) as inner:
            evt_inner = Event(type=EventType.BUILD_STARTED, source="test")
            assert evt_inner.correlation_id == inner.trace_id
            assert inner.parent_id == outer.trace_id
            assert inner.trace_id != outer.trace_id

        # After exiting inner, should be back to outer trace
        evt_back = Event(type=EventType.BUILD_SUCCEEDED, source="test")
        assert evt_back.correlation_id == outer.trace_id

    print(f"OK: nested traces work (outer={outer.trace_id}, inner={inner.trace_id})")


async def test_explicit_correlation_id_not_overridden():
    """Explicitly set correlation_id should not be overridden by context."""
    async with PipelineTrace("test") as trace:
        custom_id = "custom-123"
        evt = Event(type=EventType.BUILD_STARTED, source="test", correlation_id=custom_id)
        assert evt.correlation_id == custom_id, (
            f"Explicit ID should be preserved, got {evt.correlation_id}"
        )
    print("OK: explicit correlation_id preserved")


async def test_to_dict_includes_trace_fields():
    """Event.to_dict() should include correlation fields."""
    async with PipelineTrace("test") as trace:
        evt = Event(type=EventType.BUILD_STARTED, source="test")
        d = evt.to_dict()
        assert d["correlation_id"] == trace.trace_id
        assert d["span_id"] == trace.span_id
        assert "parent_id" in d
    print("OK: to_dict includes trace fields")


async def main():
    print("=== Correlation ID Tests ===\n")
    await test_trace_id_generation()
    await test_event_inherits_correlation_from_context()
    await test_nested_traces()
    await test_explicit_correlation_id_not_overridden()
    await test_to_dict_includes_trace_fields()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
