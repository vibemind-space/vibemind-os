"""
Integration Test - Full System Test with Monitoring

Tests the complete system:
1. Agent Monitor with real-time dashboard
2. Code Quality Agent integration
3. Document Registry inter-agent flow
4. All autonomous agents working together
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState
from src.mind.agent_monitor import AgentMonitor, create_monitor
from src.mind.convergence import FAST_ITERATION_CRITERIA
from src.registry.document_registry import DocumentRegistry
from src.registry.document_types import DocumentType
from src.registry.documents import TestSpec, QualityReport, TestResults, TestCase, DocumentationTask


async def test_full_integration():
    """Run full integration test with all components."""
    print("=" * 70)
    print("         FULL SYSTEM INTEGRATION TEST WITH MONITORING")
    print("=" * 70)

    # Setup core components
    print("\n[1] Setting up core components...")
    event_bus = EventBus()
    shared_state = SharedState()

    # Create output directory for test
    output_dir = Path("output_integration_test")
    output_dir.mkdir(exist_ok=True)

    # Initialize document registry
    doc_registry = DocumentRegistry(str(output_dir))
    print("    + EventBus created")
    print("    + SharedState created")
    print("    + DocumentRegistry created")

    # Create monitor with logging display
    log_lines = []
    def log_display(text: str):
        log_lines.append(text)
        # Print just the summary lines
        lines = text.split("\n")
        for line in lines:
            if "Iteration:" in line or "AGENT" in line[:10] or line.startswith(">") or line.startswith("*"):
                print(f"    {line}")

    monitor = create_monitor(
        event_bus=event_bus,
        shared_state=shared_state,
        display_callback=log_display,
    )
    print("    + AgentMonitor created")

    # Start monitoring
    print("\n[2] Starting monitoring...")
    monitor.start()

    # Simulate full agent workflow
    print("\n[3] Simulating agent workflow...")

    # Step 1: Agents start
    agents = ["Generator", "TesterTeam", "CodeQuality", "PlaywrightE2E"]
    for agent in agents:
        await event_bus.publish(Event(
            type=EventType.AGENT_STARTED,
            source=agent,
        ))
    await asyncio.sleep(0.2)
    print("    + All agents started")

    # Step 2: Generator generates code
    await event_bus.publish(Event(
        type=EventType.AGENT_ACTING,
        source="Generator",
        data={"action": "Generating initial project structure"},
    ))
    await event_bus.publish(Event(
        type=EventType.CODE_GENERATED,
        source="Generator",
        file_path="src/App.tsx",
    ))
    await event_bus.publish(Event(
        type=EventType.CODE_GENERATED,
        source="Generator",
        file_path="src/main.ts",
    ))
    await asyncio.sleep(0.1)
    print("    + Code generated")

    # Step 3: Build
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
    print("    + Build succeeded")

    # Step 4: Tests
    await shared_state.update_tests(total=5, passed=5, failed=0)
    await event_bus.publish(Event(
        type=EventType.TEST_SUITE_COMPLETE,
        source="TesterTeam",
        data={"total": 5, "passed": 5, "failed": 0},
    ))
    await asyncio.sleep(0.1)
    print("    + Tests passed (5/5)")

    # Step 5: Document Registry flow
    print("\n[4] Testing Document Registry flow...")

    # Create TestSpec (from TesterTeam)
    test_spec = TestSpec(
        id=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        timestamp=datetime.now(),
        source_agent="TesterTeam",
        responding_to=None,
        test_cases=[
            TestCase(id="tc1", name="App renders", description="Test app rendering", steps=["Navigate to app", "Check title"]),
            TestCase(id="tc2", name="Button clicks", description="Test button clicks", steps=["Click button", "Verify count"]),
        ],
        coverage_targets=["src/App.tsx", "src/components/Button.tsx"],
        results=TestResults(total=5, passed=5, failed=0, skipped=0),
    )

    await doc_registry.write_document(test_spec, priority=2)
    await event_bus.publish(Event(
        type=EventType.TEST_SPEC_CREATED,
        source="TesterTeam",
        data={"doc_id": test_spec.id},
    ))
    print(f"    + TestSpec created: {test_spec.id}")

    # CodeQuality consumes TestSpec
    pending = await doc_registry.get_pending_for_agent("CodeQuality")
    if pending:
        print(f"    + CodeQuality found {len(pending)} pending document(s)")
        await doc_registry.mark_consumed(pending[0].id, "CodeQuality")

    # Create QualityReport (from CodeQuality)
    quality_report = QualityReport(
        id=f"quality_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        timestamp=datetime.now(),
        source_agent="CodeQuality",
        responding_to=test_spec.id,
        documentation_tasks=[
            DocumentationTask(id="doc1", task_type="readme", target_path="README.md", scope=["*"], priority=1),
        ],
        cleanup_tasks=[],
        refactor_tasks=[],
        total_files_analyzed=10,
        unused_files_found=0,
        large_files_found=0,
        documentation_gaps=1,
        requires_action=True,
    )

    await doc_registry.write_document(quality_report, priority=3)
    await event_bus.publish(Event(
        type=EventType.QUALITY_REPORT_CREATED,
        source="CodeQuality",
        data={
            "doc_id": quality_report.id,
            "requires_action": True,
            "cleanup_tasks": 0,
            "refactor_tasks": 0,
            "doc_tasks": 1,
        },
    ))
    print(f"    + QualityReport created: {quality_report.id}")

    # Generator receives quality report
    pending_for_gen = await doc_registry.get_pending_for_agent("Generator")
    if pending_for_gen:
        print(f"    + Generator found {len(pending_for_gen)} pending QualityReport(s)")

    await asyncio.sleep(0.2)

    # Step 6: Complete all agents
    print("\n[5] Completing agents...")
    for agent in agents:
        await event_bus.publish(Event(
            type=EventType.AGENT_COMPLETED,
            source=agent,
            data={"actions_taken": 3},
        ))
    await asyncio.sleep(0.1)
    print("    + All agents completed")

    # Step 7: Convergence update
    await shared_state.increment_iteration()
    await event_bus.publish(Event(
        type=EventType.CONVERGENCE_UPDATE,
        source="orchestrator",
        data={
            "iteration": 1,
            "confidence": shared_state.metrics.confidence_score,
        },
    ))

    # Stop monitoring
    monitor.stop()

    # Print results
    print("\n" + "=" * 70)
    print("                    INTEGRATION TEST RESULTS")
    print("=" * 70)

    # Agent metrics
    print("\nAgent Status:")
    all_status = monitor.get_all_agent_status()
    for name, status in sorted(all_status.items()):
        if status["actions_taken"] > 0 or status["documents_produced"] > 0:
            print(f"  {name}:")
            print(f"    Status: {status['status']}")
            print(f"    Actions: {status['actions_taken']}")
            print(f"    Documents: {status['documents_produced']} produced, {status['documents_consumed']} consumed")

    # Document flow
    print("\nDocument Flow:")
    doc_flow = monitor.get_document_flow()
    for flow in doc_flow:
        print(f"  {flow['source']} -> {flow['type']}")

    # Event history
    history = monitor.get_event_history()
    print(f"\nTotal Events Logged: {len(history)}")

    # Registry stats
    stats = doc_registry.get_stats()
    print(f"\nDocument Registry Stats:")
    print(f"  Total documents: {stats.get('total_documents', 0)}")
    print(f"  By type: {stats.get('by_type', {})}")

    # Convergence metrics
    metrics = shared_state.metrics
    print(f"\nConvergence Metrics:")
    print(f"  Confidence Score: {metrics.confidence_score:.1%}")
    print(f"  Build Success: {metrics.build_success}")
    print(f"  Tests: {metrics.tests_passed}/{metrics.total_tests} passed")

    # Final verification
    print("\n" + "-" * 70)
    all_passed = True

    # Check agents completed
    completed_count = sum(1 for s in all_status.values() if s["status"] == "completed")
    print(f"[{'OK' if completed_count >= 4 else 'FAIL'}] Agents completed: {completed_count}/4")
    all_passed = all_passed and completed_count >= 4

    # Check document flow
    print(f"[{'OK' if len(doc_flow) >= 2 else 'FAIL'}] Document flow: {len(doc_flow)} transfers")
    all_passed = all_passed and len(doc_flow) >= 2

    # Check events logged
    print(f"[{'OK' if len(history) >= 10 else 'FAIL'}] Events logged: {len(history)}")
    all_passed = all_passed and len(history) >= 10

    # Check build/tests
    print(f"[{'OK' if metrics.build_success else 'FAIL'}] Build success")
    all_passed = all_passed and metrics.build_success

    print(f"[{'OK' if metrics.tests_passed == metrics.total_tests else 'FAIL'}] All tests passed")
    all_passed = all_passed and metrics.tests_passed == metrics.total_tests

    print("-" * 70)

    if all_passed:
        print("\n[SUCCESS] All integration tests passed!")
    else:
        print("\n[PARTIAL] Some tests did not pass - review above")

    # Print final dashboard
    print("\n" + "=" * 70)
    print("                    FINAL DASHBOARD")
    print("=" * 70)
    print(monitor.get_dashboard())

    return all_passed


async def main():
    """Run the integration test."""
    try:
        success = await test_full_integration()
        return 0 if success else 1
    except Exception as e:
        print(f"\n[ERROR] Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
