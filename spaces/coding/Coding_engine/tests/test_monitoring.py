"""
Test script for Agent Monitoring System.

Tests:
1. AgentMonitor creation and event subscription
2. Event handling and metrics tracking
3. Dashboard generation
4. Integration with Orchestrator
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState
from src.mind.agent_monitor import AgentMonitor, create_monitor


async def test_monitor_creation():
    """Test creating an agent monitor."""
    print("\n[1] Testing AgentMonitor creation...")

    event_bus = EventBus()
    shared_state = SharedState()

    monitor = create_monitor(
        event_bus=event_bus,
        shared_state=shared_state,
    )

    assert monitor is not None
    assert monitor.event_bus == event_bus
    assert monitor.shared_state == shared_state
    print("   [OK] AgentMonitor created successfully")

    return monitor, event_bus, shared_state


async def test_event_handling():
    """Test event handling and metrics tracking."""
    print("\n[2] Testing event handling...")

    event_bus = EventBus()
    shared_state = SharedState()
    monitor = create_monitor(event_bus, shared_state)

    # Simulate agent lifecycle events
    await event_bus.publish(Event(
        type=EventType.AGENT_STARTED,
        source="Generator",
    ))
    await asyncio.sleep(0.1)

    # Check metrics updated
    metrics = monitor.get_agent_status("Generator")
    assert metrics is not None
    assert metrics.status == "running"
    print("   [OK] AGENT_STARTED event handled")

    # Simulate agent acting
    await event_bus.publish(Event(
        type=EventType.AGENT_ACTING,
        source="Generator",
        data={"action": "Generating code for App.tsx"},
    ))
    await asyncio.sleep(0.1)

    metrics = monitor.get_agent_status("Generator")
    assert metrics.status == "acting"
    assert metrics.last_action == "Generating code for App.tsx"
    print("   [OK] AGENT_ACTING event handled")

    # Simulate code generated
    await event_bus.publish(Event(
        type=EventType.CODE_GENERATED,
        source="Generator",
        file_path="src/App.tsx",
    ))
    await asyncio.sleep(0.1)

    metrics = monitor.get_agent_status("Generator")
    assert metrics.actions_taken == 1
    print("   [OK] CODE_GENERATED event handled")

    # Simulate agent completed
    await event_bus.publish(Event(
        type=EventType.AGENT_COMPLETED,
        source="Generator",
        data={"actions_taken": 5},
    ))
    await asyncio.sleep(0.1)

    metrics = monitor.get_agent_status("Generator")
    assert metrics.status == "completed"
    print("   [OK] AGENT_COMPLETED event handled")

    # Check event history
    history = monitor.get_event_history()
    assert len(history) >= 4
    print(f"   [OK] Event history contains {len(history)} events")

    return True


async def test_document_flow():
    """Test document flow tracking."""
    print("\n[3] Testing document flow tracking...")

    event_bus = EventBus()
    shared_state = SharedState()
    monitor = create_monitor(event_bus, shared_state)

    # Simulate document creation
    await event_bus.publish(Event(
        type=EventType.DEBUG_REPORT_CREATED,
        source="PlaywrightE2E",
        data={"doc_id": "debug_001", "priority": 2},
    ))
    await asyncio.sleep(0.1)

    # Check document flow
    flow = monitor.get_document_flow()
    assert len(flow) == 1
    assert flow[0]["type"] == "debug_report_created"
    print("   [OK] DEBUG_REPORT_CREATED tracked")

    # Simulate implementation plan
    await event_bus.publish(Event(
        type=EventType.IMPLEMENTATION_PLAN_CREATED,
        source="Generator",
        data={"doc_id": "impl_001", "responding_to": "debug_001"},
    ))
    await asyncio.sleep(0.1)

    flow = monitor.get_document_flow()
    assert len(flow) == 2
    print("   [OK] IMPLEMENTATION_PLAN_CREATED tracked")

    # Simulate quality report
    await event_bus.publish(Event(
        type=EventType.QUALITY_REPORT_CREATED,
        source="CodeQuality",
        data={
            "doc_id": "quality_001",
            "cleanup_tasks": 2,
            "refactor_tasks": 1,
            "doc_tasks": 3,
        },
    ))
    await asyncio.sleep(0.1)

    flow = monitor.get_document_flow()
    assert len(flow) == 3
    print("   [OK] QUALITY_REPORT_CREATED tracked")

    # Check metrics
    quality_metrics = monitor.get_agent_status("CodeQuality")
    assert quality_metrics.documents_produced == 1
    print("   [OK] Document producer metrics updated")

    return True


async def test_dashboard_output():
    """Test dashboard generation."""
    print("\n[4] Testing dashboard generation...")

    event_bus = EventBus()
    shared_state = SharedState()
    monitor = create_monitor(event_bus, shared_state)

    # Set up some state
    await shared_state.update_tests(total=10, passed=8, failed=2)
    await shared_state.update_build(attempted=True, success=True)
    await shared_state.increment_iteration()

    # Simulate some events
    for agent in ["Generator", "TesterTeam", "CodeQuality"]:
        await event_bus.publish(Event(
            type=EventType.AGENT_STARTED,
            source=agent,
        ))

    await asyncio.sleep(0.1)

    # Generate dashboard
    dashboard = monitor.get_dashboard()

    assert "AGENT MONITOR DASHBOARD" in dashboard
    assert "Generator" in dashboard
    assert "TesterTeam" in dashboard
    assert "CodeQuality" in dashboard
    print("   [OK] Dashboard generated successfully")

    # Print dashboard preview
    print("\n   Dashboard Preview:")
    print("-" * 40)
    lines = dashboard.split("\n")[:20]
    for line in lines:
        print(f"   {line}")
    print("   ...")
    print("-" * 40)

    return True


async def test_full_simulation():
    """Test a full simulation with multiple agents and events."""
    print("\n[5] Testing full agent simulation...")

    event_bus = EventBus()
    shared_state = SharedState()
    monitor = create_monitor(event_bus, shared_state)

    # Start monitoring with log-based display (no screen clear)
    displayed_count = [0]

    def log_display(text: str):
        displayed_count[0] += 1
        # Don't actually print - just count

    monitor.display_callback = log_display
    monitor.start()

    # Simulate full workflow
    agents = ["Generator", "TesterTeam", "PlaywrightE2E", "CodeQuality"]

    # Start all agents
    for agent in agents:
        await event_bus.publish(Event(
            type=EventType.AGENT_STARTED,
            source=agent,
        ))
    await asyncio.sleep(0.2)

    # Generator generates code
    await event_bus.publish(Event(
        type=EventType.AGENT_ACTING,
        source="Generator",
        data={"action": "Generating initial code"},
    ))
    await event_bus.publish(Event(
        type=EventType.CODE_GENERATED,
        source="Generator",
        file_path="src/App.tsx",
    ))
    await asyncio.sleep(0.1)

    # Build events
    await event_bus.publish(Event(
        type=EventType.BUILD_STARTED,
        source="Builder",
    ))
    await shared_state.update_build(attempted=True, success=True)
    await event_bus.publish(Event(
        type=EventType.BUILD_SUCCEEDED,
        source="Builder",
    ))
    await asyncio.sleep(0.1)

    # Test events
    await event_bus.publish(Event(
        type=EventType.TEST_SUITE_COMPLETE,
        source="TesterTeam",
        data={"total": 5, "passed": 5, "failed": 0},
    ))
    await shared_state.update_tests(total=5, passed=5, failed=0)
    await asyncio.sleep(0.1)

    # PlaywrightE2E creates debug report
    await event_bus.publish(Event(
        type=EventType.DEBUG_REPORT_CREATED,
        source="PlaywrightE2E",
        data={"doc_id": "debug_001"},
    ))
    await asyncio.sleep(0.1)

    # CodeQuality creates quality report
    await event_bus.publish(Event(
        type=EventType.QUALITY_REPORT_CREATED,
        source="CodeQuality",
        data={
            "doc_id": "quality_001",
            "requires_action": True,
            "cleanup_tasks": 1,
            "refactor_tasks": 0,
            "doc_tasks": 2,
        },
    ))
    await asyncio.sleep(0.1)

    # Complete all agents
    for agent in agents:
        await event_bus.publish(Event(
            type=EventType.AGENT_COMPLETED,
            source=agent,
            data={"actions_taken": 3},
        ))
    await asyncio.sleep(0.1)

    # Stop monitoring
    monitor.stop()

    # Verify results
    all_status = monitor.get_all_agent_status()
    completed = sum(1 for s in all_status.values() if s["status"] == "completed")
    assert completed >= 4
    print(f"   [OK] {completed} agents completed")

    doc_flow = monitor.get_document_flow()
    assert len(doc_flow) >= 2
    print(f"   [OK] {len(doc_flow)} documents tracked")

    history = monitor.get_event_history()
    print(f"   [OK] {len(history)} events logged")

    print(f"   [OK] Display updated {displayed_count[0]} times")

    # Print summary
    monitor.print_summary()

    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Agent Monitoring System Tests")
    print("=" * 60)

    try:
        # Test 1: Monitor creation
        await test_monitor_creation()

        # Test 2: Event handling
        await test_event_handling()

        # Test 3: Document flow
        await test_document_flow()

        # Test 4: Dashboard output
        await test_dashboard_output()

        # Test 5: Full simulation
        await test_full_simulation()

        print("\n" + "=" * 60)
        print("[OK] All Agent Monitoring tests passed!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
