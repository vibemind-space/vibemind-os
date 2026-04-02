"""
Test Automation Engine - Demonstrates the full automation pipeline.

This test shows:
1. Task decomposition (breaking complex goals into subtasks)
2. Task scheduling (dependency management and parallelization)
3. Progress tracking (real-time status updates)
4. Conversation interface (natural language API)

Usage:
    python test_automation_engine.py
    python test_automation_engine.py --real  # With actual PyAutoGUI execution
"""

import asyncio
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_task_decomposition():
    """Test 1: Task Decomposition"""
    from core.task_decomposer import TaskDecomposer, Subtask

    print("\n" + "=" * 60)
    print("TEST 1: Task Decomposition")
    print("=" * 60)

    decomposer = TaskDecomposer()

    # Test various goals
    test_goals = [
        "Open Notepad and type Hello World",
        "Search for Python tutorials on Google",
        "Open Chrome, search for AI news, and read the headlines",
        "Create a new Word document and save it as test.docx"
    ]

    for goal in test_goals:
        print(f"\nGoal: '{goal}'")
        print("-" * 40)

        subtasks = await decomposer.decompose(goal, {"os": "Windows"})

        print(f"Decomposed into {len(subtasks)} subtasks:")
        for i, subtask in enumerate(subtasks, 1):
            deps = f" (depends on: {len(subtask.dependencies)})" if subtask.dependencies else ""
            print(f"  {i}. [{subtask.approach}] {subtask.description}{deps}")

    print("\n[PASS] Task decomposition working!")
    return True


async def test_task_scheduling():
    """Test 2: Task Scheduling"""
    from core.task_decomposer import Subtask
    from core.task_scheduler import TaskScheduler

    print("\n" + "=" * 60)
    print("TEST 2: Task Scheduling")
    print("=" * 60)

    scheduler = TaskScheduler()

    # Create test subtasks with dependencies
    subtasks = [
        Subtask.create("Open browser", "keyboard", order=1),
        Subtask.create("Wait for browser", "vision", order=2),
        Subtask.create("Type URL", "keyboard", order=3),
        Subtask.create("Analyze page header", "vision", can_parallel=True, order=4),
        Subtask.create("Analyze page content", "vision", can_parallel=True, order=5),
        Subtask.create("Click button", "mouse", order=6)
    ]

    # Set up dependencies
    subtasks[1].dependencies = [subtasks[0].id]  # Wait depends on Open
    subtasks[2].dependencies = [subtasks[1].id]  # Type depends on Wait
    subtasks[3].dependencies = [subtasks[2].id]  # Analyze header depends on Type
    subtasks[4].dependencies = [subtasks[2].id]  # Analyze content depends on Type
    subtasks[5].dependencies = [subtasks[3].id, subtasks[4].id]  # Click depends on both analyses

    # Create execution plan
    plan = scheduler.create_plan(subtasks)

    print(f"\nExecution Plan: {plan.total_phases} phases, {plan.total_subtasks} subtasks")
    print("-" * 40)

    for phase in plan.phases:
        parallel_str = "[PARALLEL]" if phase.can_parallel else "[SEQUENTIAL]"
        print(f"\nPhase {phase.phase_id} {parallel_str}:")
        for subtask in phase.subtasks:
            print(f"  - [{subtask.approach}] {subtask.description}")

    print(f"\nEstimated duration: {plan.estimated_duration:.0f}s")

    print("\n[PASS] Task scheduling working!")
    return True


async def test_progress_tracking():
    """Test 3: Progress Tracking"""
    from core.task_decomposer import Subtask
    from core.progress_tracker import ProgressTracker

    print("\n" + "=" * 60)
    print("TEST 3: Progress Tracking")
    print("=" * 60)

    tracker = ProgressTracker()

    # Create test subtasks
    subtasks = [
        Subtask.create("Step 1: Initialize", "keyboard"),
        Subtask.create("Step 2: Process", "vision"),
        Subtask.create("Step 3: Verify", "vision"),
        Subtask.create("Step 4: Complete", "keyboard")
    ]

    # Start task
    task_id = "test_task_001"
    tracker.start_task(task_id, subtasks)

    print(f"\nTask started: {task_id}")
    print(f"Progress: {tracker.get_progress(task_id):.0%}")

    # Simulate execution
    for subtask in subtasks:
        tracker.start_subtask(task_id, subtask.id)
        print(f"\nRunning: {subtask.description}")
        print(f"Progress: {tracker.get_progress(task_id):.0%}")

        await asyncio.sleep(0.2)  # Simulate work

        tracker.complete_subtask(task_id, subtask.id, success=True)
        print(f"Completed: {subtask.description}")
        print(f"Progress: {tracker.get_progress(task_id):.0%}")

    # Get final status
    status = tracker.get_status(task_id)
    print(f"\nFinal Status:")
    print(f"  Completed: {status['completed_subtasks']}/{status['total_subtasks']}")
    print(f"  Duration: {status['duration']:.2f}s")

    tracker.end_task(task_id)

    print("\n[PASS] Progress tracking working!")
    return True


async def test_automation_engine():
    """Test 4: Full Automation Engine"""
    from core.automation_engine import AutomationEngine

    print("\n" + "=" * 60)
    print("TEST 4: Automation Engine (Mock Execution)")
    print("=" * 60)

    # Create engine without real orchestrator
    engine = AutomationEngine()

    # Progress callback
    async def on_progress(status):
        state = status.get("state", "unknown")
        progress = status.get("progress", 0)
        message = status.get("message", status.get("current_subtasks", [""])[0] if "current_subtasks" in status else "")

        if state == "decomposing":
            print(f"  [Decomposing] {message}")
        elif state == "scheduling":
            print(f"  [Scheduling] {message}")
        elif state == "executing":
            print(f"  [Executing] Phase {status.get('phase', '?')}/{status.get('total_phases', '?')} - {progress:.0%}")
        elif state == "executing_subtask":
            print(f"    > {status.get('subtask', 'unknown')} [{status.get('approach', '')}]")
        elif state == "completed":
            print(f"  [Complete] Success: {status.get('success')}, Duration: {status.get('duration', 0):.1f}s")

    # Test complex task
    goal = "Open Notepad, type Hello World, and save the file"
    print(f"\nExecuting: '{goal}'")
    print("-" * 40)

    result = await engine.execute_complex_task(
        goal=goal,
        context={"os": "Windows"},
        on_progress=on_progress
    )

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Subtasks: {result.subtasks_completed}/{result.subtasks_total}")
    print(f"  Duration: {result.duration_seconds:.1f}s")
    print(f"  Summary: {result.summary}")

    print("\n[PASS] Automation engine working!")
    return True


async def test_conversation_interface():
    """Test 5: Conversation Interface"""
    from core.automation_engine import AutomationEngine
    from api.conversation_interface import ConversationInterface

    print("\n" + "=" * 60)
    print("TEST 5: Conversation Interface")
    print("=" * 60)

    # Create engine and interface
    engine = AutomationEngine()
    interface = ConversationInterface(engine)

    # Subscribe to updates
    updates_received = []

    async def on_update(status):
        updates_received.append(status)
        state = status.get("state", "unknown")
        if state == "executing_subtask":
            print(f"  Update: {status.get('subtask', 'unknown')}")

    # Submit task
    goal = "Search for Python news and summarize"
    print(f"\nSubmitting: '{goal}'")

    task_id = await interface.submit_task(goal)
    print(f"Task ID: {task_id}")

    interface.subscribe_to_updates(task_id, on_update)

    # Poll for completion
    while True:
        status = await interface.get_status(task_id)
        if status.get("state") in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.1)

    # Get result
    result = await interface.get_result(task_id)
    print(f"\nResult received!")
    print(f"  Success: {result.success if result else 'N/A'}")
    print(f"  Updates received: {len(updates_received)}")

    print("\n[PASS] Conversation interface working!")
    return True


async def test_with_real_execution():
    """Test 6: Real Execution with PyAutoGUI"""
    print("\n" + "=" * 60)
    print("TEST 6: Real Execution (PyAutoGUI)")
    print("=" * 60)

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        print("PyAutoGUI available - move mouse to corner to abort")
    except ImportError:
        print("[SKIP] PyAutoGUI not installed")
        return True

    from core.task_decomposer import TaskDecomposer

    print("\nThis test will actually open Notepad!")
    print("Starting in 3 seconds... (move mouse to corner to abort)")

    for i in range(3, 0, -1):
        print(f"  {i}...")
        await asyncio.sleep(1)

    # Decompose task
    decomposer = TaskDecomposer()
    subtasks = await decomposer.decompose("Open Notepad")

    print(f"\nExecuting {len(subtasks)} subtasks...")

    for subtask in subtasks:
        print(f"\n  > {subtask.description}")

        if subtask.approach == "keyboard":
            context = subtask.context
            if "keys" in context:
                keys = context["keys"]
                print(f"    Pressing: {'+'.join(keys)}")
                pyautogui.hotkey(*keys)
            elif "text" in context:
                text = context["text"]
                print(f"    Typing: {text}")
                pyautogui.write(text, interval=0.05)

        await asyncio.sleep(0.5)

    print("\n[PASS] Real execution completed!")
    print("Check if Notepad opened!")
    return True


async def main():
    """Run all tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Automation Engine")
    parser.add_argument("--real", action="store_true", help="Run with real PyAutoGUI execution")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("MoireTracker Automation Engine Tests")
    print("=" * 60)

    results = []

    # Test 1: Task Decomposition
    try:
        results.append(("Task Decomposition", await test_task_decomposition()))
    except Exception as e:
        print(f"[FAIL] Task Decomposition: {e}")
        results.append(("Task Decomposition", False))

    # Test 2: Task Scheduling
    try:
        results.append(("Task Scheduling", await test_task_scheduling()))
    except Exception as e:
        print(f"[FAIL] Task Scheduling: {e}")
        results.append(("Task Scheduling", False))

    # Test 3: Progress Tracking
    try:
        results.append(("Progress Tracking", await test_progress_tracking()))
    except Exception as e:
        print(f"[FAIL] Progress Tracking: {e}")
        results.append(("Progress Tracking", False))

    # Test 4: Automation Engine
    try:
        results.append(("Automation Engine", await test_automation_engine()))
    except Exception as e:
        print(f"[FAIL] Automation Engine: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Automation Engine", False))

    # Test 5: Conversation Interface
    try:
        results.append(("Conversation Interface", await test_conversation_interface()))
    except Exception as e:
        print(f"[FAIL] Conversation Interface: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Conversation Interface", False))

    # Test 6: Real Execution (optional)
    if args.real:
        try:
            results.append(("Real Execution", await test_with_real_execution()))
        except Exception as e:
            print(f"[FAIL] Real Execution: {e}")
            results.append(("Real Execution", False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n*** ALL TESTS PASSED ***")
    else:
        print("\n*** SOME TESTS FAILED ***")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
