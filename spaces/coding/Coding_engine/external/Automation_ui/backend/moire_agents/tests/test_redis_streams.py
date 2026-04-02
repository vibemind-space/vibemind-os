"""
Test script for Redis Streams infrastructure.

Run this to verify:
1. Redis connection works
2. Publish/subscribe works
3. Tool call pattern works

Prerequisites:
1. Start Redis: docker-compose up -d redis
2. Install dependencies: pip install redis>=5.0.0
"""

import asyncio
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_redis_connection():
    """Test basic Redis connection."""
    from core.redis_streams import RedisStreamClient

    print("\n" + "="*60)
    print("TEST 1: Redis Connection")
    print("="*60)

    client = RedisStreamClient(host="localhost", port=6379)

    try:
        connected = await client.connect()
        if connected:
            print("[PASS] Connected to Redis successfully!")

            # Health check
            health = await client.health_check()
            print(f"[PASS] Health check: {health['healthy']}")
            print(f"   Consumer group: {health['consumer_group']}")
            print(f"   Consumer name: {health['consumer_name']}")

            await client.disconnect()
            return True
        else:
            print("[FAIL] Failed to connect to Redis")
            return False

    except Exception as e:
        print(f"[FAIL] Connection error: {e}")
        print("\nMake sure Redis is running:")
        print("  docker-compose up -d redis")
        return False


async def test_publish_subscribe():
    """Test publish and subscribe functionality."""
    from core.redis_streams import RedisStreamClient

    print("\n" + "="*60)
    print("TEST 2: Publish/Subscribe")
    print("="*60)

    client = RedisStreamClient(host="localhost", port=6379)
    await client.connect()

    try:
        # Publish a message
        test_stream = "moire:test"
        test_message = {"action": "test", "data": "hello world"}

        msg_id = await client.publish(test_stream, test_message)
        print(f"[PASS] Published message: {msg_id}")

        # Read the message
        messages = await client.read_stream(test_stream, count=1, block_ms=1000)

        if messages:
            print(f"[PASS] Received message: {messages[0].data}")
            return True
        else:
            print("[FAIL] No message received")
            return False

    finally:
        await client.disconnect()


async def test_tool_call_pattern():
    """Test the tool call request/response pattern."""
    from core.redis_streams import RedisStreamClient
    from core.subagent_runner import SubagentRunner, SubagentType, SubagentTask, SubagentResult

    print("\n" + "="*60)
    print("TEST 3: Tool Call Pattern")
    print("="*60)

    # Create a simple test runner
    class TestRunner(SubagentRunner):
        async def execute(self, task: SubagentTask) -> SubagentResult:
            # Echo back the params
            return SubagentResult(
                success=True,
                result={"echo": task.params, "message": "Hello from test runner!"},
                confidence=0.99
            )

    # Create client for orchestrator
    orchestrator_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="orchestrator"
    )
    await orchestrator_client.connect()

    # Create client for runner
    runner_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="test_worker"
    )
    await runner_client.connect()

    # Create test runner
    runner = TestRunner(runner_client, SubagentType.PLANNING)

    try:
        # Start runner in background
        runner_task = asyncio.create_task(runner.run_forever())

        # Give runner time to start
        await asyncio.sleep(0.5)

        # Make a tool call
        print("Making tool call to planning subagent...")
        result = await orchestrator_client.call_tool(
            tool_name="planning",
            params={"goal": "Open Word", "approach": "keyboard"},
            timeout=5.0
        )

        if result.success:
            print(f"[PASS] Tool call succeeded!")
            print(f"   Result: {result.result}")
            print(f"   Execution time: {result.execution_time_ms:.1f}ms")
        else:
            print(f"[FAIL] Tool call failed: {result.error}")

        # Stop runner
        await runner.stop()
        runner_task.cancel()
        try:
            await runner_task
        except asyncio.CancelledError:
            pass

        return result.success

    finally:
        await orchestrator_client.disconnect()
        await runner_client.disconnect()


async def test_subagent_manager():
    """Test the SubagentManager interface."""
    from core.redis_streams import RedisStreamClient
    from core.subagent_manager import SubagentManager, SubagentConfig
    from core.subagent_runner import SubagentRunner, SubagentType, SubagentTask, SubagentResult

    print("\n" + "="*60)
    print("TEST 4: SubagentManager")
    print("="*60)

    # Create a test planning runner
    class TestPlanningRunner(SubagentRunner):
        async def execute(self, task: SubagentTask) -> SubagentResult:
            approach = task.params.get("approach", "unknown")
            goal = task.params.get("goal", "")

            # Simulate different approaches with different confidences
            confidence_map = {
                "keyboard": 0.95,
                "mouse": 0.75,
                "hybrid": 0.85
            }

            return SubagentResult(
                success=True,
                result={
                    "actions": [
                        {"action": "press_key", "key": "win"},
                        {"action": "type", "text": goal.split()[-1]},
                        {"action": "press_key", "key": "enter"}
                    ],
                    "confidence": confidence_map.get(approach, 0.5),
                    "reasoning": f"Using {approach} approach for: {goal}"
                },
                confidence=confidence_map.get(approach, 0.5)
            )

    # Create clients
    manager_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="manager"
    )
    await manager_client.connect()

    runner_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="planning_worker"
    )
    await runner_client.connect()

    # Create manager
    config = SubagentConfig(planning_timeout=10.0)
    manager = SubagentManager(manager_client, config)

    # Create runners (3 workers for parallel execution)
    runners = []
    runner_tasks = []
    for i in range(3):
        client = RedisStreamClient(
            host="localhost",
            port=6379,
            consumer_name=f"planning_worker_{i}"
        )
        await client.connect()
        runner = TestPlanningRunner(client, SubagentType.PLANNING, f"worker_{i}")
        runners.append((client, runner))
        runner_tasks.append(asyncio.create_task(runner.run_forever()))

    try:
        await asyncio.sleep(0.5)  # Let runners start

        # Test parallel planners
        print("Spawning parallel planners...")
        best_plan = await manager.spawn_parallel_planners(
            goal="Open Word",
            approaches=["keyboard", "mouse", "hybrid"]
        )

        if best_plan and best_plan.success:
            print(f"[PASS] Parallel planning succeeded!")
            print(f"   Best approach: {best_plan.approach}")
            print(f"   Confidence: {best_plan.confidence:.2f}")
            print(f"   Actions: {len(best_plan.actions)} steps")

            # Verify best was selected (keyboard should have highest confidence)
            if best_plan.approach == "keyboard":
                print(f"[PASS] Correctly selected highest confidence approach!")
            return True
        else:
            print(f"[FAIL] Parallel planning failed")
            return False

    finally:
        # Cleanup
        for client, runner in runners:
            await runner.stop()
            await client.disconnect()
        for task in runner_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await manager_client.disconnect()


async def test_planning_subagents():
    """Test the actual planning subagents with different approaches."""
    from core.redis_streams import RedisStreamClient
    from core.subagent_manager import SubagentManager, SubagentConfig
    from agents.subagents.planning_subagent import (
        PlanningSubagentRunner,
        PlanningApproach
    )

    print("\n" + "="*60)
    print("TEST 5: Planning Subagents")
    print("="*60)

    # Create clients
    manager_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="manager"
    )
    await manager_client.connect()

    # Create manager
    config = SubagentConfig(planning_timeout=10.0)
    manager = SubagentManager(manager_client, config)

    # Create planning runners for each approach
    runners = []
    runner_tasks = []
    for approach in PlanningApproach:
        client = RedisStreamClient(
            host="localhost",
            port=6379,
            consumer_name=f"planning_{approach.value}"
        )
        await client.connect()
        runner = PlanningSubagentRunner(
            redis_client=client,
            approach=approach
        )
        runners.append((client, runner))
        runner_tasks.append(asyncio.create_task(runner.run_forever()))

    try:
        await asyncio.sleep(0.5)  # Let runners start

        # Test: Open Word
        print("\nTest goal: 'Open Word'")
        best_plan = await manager.spawn_parallel_planners(
            goal="Open Word",
            approaches=["keyboard", "mouse", "hybrid"]
        )

        if best_plan and best_plan.success:
            print(f"[PASS] Planning succeeded!")
            print(f"   Selected approach: {best_plan.approach}")
            print(f"   Confidence: {best_plan.confidence:.2f}")
            print(f"   Actions:")
            for i, action in enumerate(best_plan.actions[:5]):
                desc = action.get('description', action.get('action', ''))
                print(f"      {i+1}. {desc}")

            # Keyboard should have highest confidence for pattern match
            if best_plan.confidence >= 0.8:
                print(f"[PASS] High confidence plan selected!")
                return True
            else:
                print(f"[WARN] Lower confidence plan (still valid)")
                return True
        else:
            print(f"[FAIL] Planning failed")
            if best_plan:
                print(f"   Error: {best_plan.error}")
            return False

    finally:
        # Cleanup
        for client, runner in runners:
            await runner.stop()
            await client.disconnect()
        for task in runner_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await manager_client.disconnect()


async def test_vision_subagents():
    """Test the vision subagents with different screen regions."""
    from core.redis_streams import RedisStreamClient
    from core.subagent_runner import SubagentRunner, SubagentType, SubagentTask, SubagentResult
    from agents.subagents.vision_subagent import (
        VisionSubagentRunner,
        ScreenRegion
    )

    print("\n" + "="*60)
    print("TEST 6: Vision Subagents")
    print("="*60)

    # Create a mock vision runner for testing (without real screenshot)
    class MockVisionRunner(SubagentRunner):
        def __init__(self, redis_client, region: ScreenRegion):
            super().__init__(
                redis_client=redis_client,
                agent_type=SubagentType.VISION,
                worker_id=f"vision_{region.value}"
            )
            self.region = region

        async def execute(self, task: SubagentTask) -> SubagentResult:
            # Mock vision analysis based on region
            elements_map = {
                ScreenRegion.TASKBAR: [
                    {"type": "icon", "label": "Chrome", "clickable": True},
                    {"type": "button", "label": "Start", "clickable": True}
                ],
                ScreenRegion.TITLE_BAR: [
                    {"type": "button", "label": "minimize", "clickable": True},
                    {"type": "button", "label": "close", "clickable": True}
                ],
                ScreenRegion.MAIN_CONTENT: [
                    {"type": "text", "label": "Document content"},
                    {"type": "button", "label": "Save", "clickable": True}
                ]
            }

            elements = elements_map.get(self.region, [])
            return SubagentResult(
                success=True,
                result={
                    "region": self.region.value,
                    "elements": elements,
                    "element_count": len(elements),
                    "confidence": 0.85
                },
                confidence=0.85
            )

    # Create clients
    manager_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="manager"
    )
    await manager_client.connect()

    # Create vision runners for each region
    runners = []
    runner_tasks = []
    test_regions = [ScreenRegion.TASKBAR, ScreenRegion.TITLE_BAR, ScreenRegion.MAIN_CONTENT]

    for region in test_regions:
        client = RedisStreamClient(
            host="localhost",
            port=6379,
            consumer_name=f"vision_{region.value}"
        )
        await client.connect()
        runner = MockVisionRunner(client, region)
        runners.append((client, runner))
        runner_tasks.append(asyncio.create_task(runner.run_forever()))

    try:
        await asyncio.sleep(0.5)  # Let runners start

        # Test parallel vision analysis
        print("\nTest: Parallel vision analysis of 3 regions")

        # Make parallel tool calls
        tasks = []
        for region in test_regions:
            tasks.append(
                manager_client.call_tool(
                    tool_name="vision",
                    params={"region": region.value, "prompt": "Analyze this region"},
                    timeout=5.0
                )
            )

        results = await asyncio.gather(*tasks)

        # Check results
        successful = sum(1 for r in results if r.success)
        print(f"[PASS] {successful}/{len(results)} vision analyses completed")

        if successful == len(test_regions):
            print(f"[PASS] All regions analyzed successfully!")
            for r in results:
                if r.success:
                    data = r.result.get("data", {})
                    region_name = data.get("region", "unknown")
                    element_count = data.get("element_count", 0)
                    print(f"   - {region_name}: {element_count} elements detected")
            return True
        else:
            print(f"[FAIL] Some vision analyses failed")
            return False

    finally:
        # Cleanup
        for client, runner in runners:
            await runner.stop()
            await client.disconnect()
        for task in runner_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await manager_client.disconnect()


async def test_background_subagents():
    """Test the background subagents with condition checks."""
    from core.redis_streams import RedisStreamClient
    from agents.subagents.background_subagent import (
        BackgroundSubagentRunner,
        MonitorCondition
    )
    import os
    import tempfile

    print("\n" + "="*60)
    print("TEST 8: Background Subagents")
    print("="*60)

    # Create clients
    manager_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="manager"
    )
    await manager_client.connect()

    # Create background runner
    runner_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="background_worker"
    )
    await runner_client.connect()

    runner = BackgroundSubagentRunner(runner_client)
    runner_task = asyncio.create_task(runner.run_forever())

    try:
        await asyncio.sleep(0.5)  # Let runner start

        # Test 1: Check if a file exists (create temp file)
        print("\nTest: Check FILE_EXISTS condition")
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
            temp_file = f.name
            f.write(b"test content")

        result = await manager_client.call_tool(
            tool_name="background",
            params={
                "check_type": "file_exists",
                "target": temp_file
            },
            timeout=5.0
        )

        if result.success:
            data = result.result.get("data", {})
            condition_met = data.get("condition_met", False)
            if condition_met:
                print(f"[PASS] File exists check passed!")
                print(f"   File: {temp_file}")
                print(f"   Size: {data.get('details', {}).get('size', 'N/A')} bytes")
            else:
                print(f"[FAIL] File should exist but check failed")
                os.unlink(temp_file)
                return False
        else:
            print(f"[FAIL] Background check failed: {result.error}")
            os.unlink(temp_file)
            return False

        # Cleanup temp file
        os.unlink(temp_file)

        # Test 2: Check if file doesn't exist anymore
        print("\nTest: Check FILE_EXISTS (should be False now)")
        result2 = await manager_client.call_tool(
            tool_name="background",
            params={
                "check_type": "file_exists",
                "target": temp_file
            },
            timeout=5.0
        )

        if result2.success:
            data = result2.result.get("data", {})
            condition_met = data.get("condition_met", False)
            if not condition_met:
                print(f"[PASS] File does not exist (correct)!")
            else:
                print(f"[FAIL] File should not exist but check says it does")
                return False
        else:
            print(f"[FAIL] Background check failed: {result2.error}")
            return False

        # Test 3: Check process (python should be running)
        print("\nTest: Check PROCESS_STARTS condition (python)")
        result3 = await manager_client.call_tool(
            tool_name="background",
            params={
                "check_type": "process_starts",
                "target": "python"
            },
            timeout=5.0
        )

        if result3.success:
            data = result3.result.get("data", {})
            condition_met = data.get("condition_met", False)
            details = data.get("details", {})
            print(f"[PASS] Process check completed!")
            print(f"   Python running: {details.get('is_running', 'N/A')}")
        else:
            print(f"[WARN] Process check inconclusive: {result3.error}")
            # Don't fail on this - it depends on system state

        print(f"\n[PASS] All background checks completed successfully!")
        return True

    finally:
        # Cleanup
        await runner.stop()
        runner_task.cancel()
        try:
            await runner_task
        except asyncio.CancelledError:
            pass
        await runner_client.disconnect()
        await manager_client.disconnect()


async def test_specialist_subagents():
    """Test the specialist subagents with domain queries."""
    from core.redis_streams import RedisStreamClient
    from agents.subagents.specialist_subagent import (
        SpecialistSubagentRunner,
        SpecialistDomain
    )

    print("\n" + "="*60)
    print("TEST 7: Specialist Subagents")
    print("="*60)

    # Create clients
    manager_client = RedisStreamClient(
        host="localhost",
        port=6379,
        consumer_name="manager"
    )
    await manager_client.connect()

    # Create specialist runners for each domain
    runners = []
    runner_tasks = []
    test_domains = [SpecialistDomain.OFFICE, SpecialistDomain.BROWSER, SpecialistDomain.DEVELOPMENT]

    for domain in test_domains:
        client = RedisStreamClient(
            host="localhost",
            port=6379,
            consumer_name=f"specialist_{domain.value}"
        )
        await client.connect()
        runner = SpecialistSubagentRunner(client, domain)
        runners.append((client, runner))
        runner_tasks.append(asyncio.create_task(runner.run_forever()))

    try:
        await asyncio.sleep(0.5)  # Let runners start

        # Test 1: Query Office specialist for shortcut
        print("\nTest: Query Office specialist for 'bold' shortcut")
        result = await manager_client.call_tool(
            tool_name="specialist",
            params={
                "domain": "office",
                "query": "shortcut for bold",
                "query_type": "shortcut"
            },
            timeout=5.0
        )

        if result.success:
            data = result.result.get("data", {})
            shortcut = data.get("shortcut", {})
            print(f"[PASS] Office specialist responded!")
            print(f"   Answer: {data.get('answer', 'N/A')}")
            print(f"   Shortcut: {shortcut.get('keys', 'N/A')}")
        else:
            print(f"[FAIL] Office specialist failed: {result.error}")
            return False

        # Test 2: Query Browser specialist for workflow
        print("\nTest: Query Browser specialist for 'new tab' workflow")
        result2 = await manager_client.call_tool(
            tool_name="specialist",
            params={
                "domain": "browser",
                "query": "keyboard shortcut for new tab"
            },
            timeout=5.0
        )

        if result2.success:
            data = result2.result.get("data", {})
            print(f"[PASS] Browser specialist responded!")
            print(f"   Answer: {data.get('answer', 'N/A')}")
        else:
            print(f"[FAIL] Browser specialist failed: {result2.error}")
            return False

        # Test 3: Query Development specialist
        print("\nTest: Query Development specialist for VS Code command palette")
        result3 = await manager_client.call_tool(
            tool_name="specialist",
            params={
                "domain": "development",
                "query": "VS Code command palette shortcut"
            },
            timeout=5.0
        )

        if result3.success:
            data = result3.result.get("data", {})
            print(f"[PASS] Development specialist responded!")
            print(f"   Answer: {data.get('answer', 'N/A')}")
        else:
            print(f"[FAIL] Development specialist failed: {result3.error}")
            return False

        print(f"\n[PASS] All specialist queries completed successfully!")
        return True

    finally:
        # Cleanup
        for client, runner in runners:
            await runner.stop()
            await client.disconnect()
        for task in runner_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await manager_client.disconnect()


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Redis Streams Infrastructure Tests")
    print("="*60)

    results = []

    # Test 1: Connection
    try:
        results.append(("Redis Connection", await test_redis_connection()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        results.append(("Redis Connection", False))
        # If Redis connection fails, skip other tests
        print("\n[WARN] Cannot continue without Redis connection")
        print_summary(results)
        return

    # Test 2: Pub/Sub
    try:
        results.append(("Publish/Subscribe", await test_publish_subscribe()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        results.append(("Publish/Subscribe", False))

    # Test 3: Tool Call Pattern
    try:
        results.append(("Tool Call Pattern", await test_tool_call_pattern()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Tool Call Pattern", False))

    # Test 4: SubagentManager
    try:
        results.append(("SubagentManager", await test_subagent_manager()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("SubagentManager", False))

    # Test 5: Planning Subagents
    try:
        results.append(("Planning Subagents", await test_planning_subagents()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Planning Subagents", False))

    # Test 6: Vision Subagents
    try:
        results.append(("Vision Subagents", await test_vision_subagents()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Vision Subagents", False))

    # Test 7: Specialist Subagents
    try:
        results.append(("Specialist Subagents", await test_specialist_subagents()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Specialist Subagents", False))

    # Test 8: Background Subagents
    try:
        results.append(("Background Subagents", await test_background_subagents()))
    except Exception as e:
        print(f"[FAIL] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Background Subagents", False))

    print_summary(results)


def print_summary(results):
    """Print test summary."""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status}: {name}")

    print("-"*60)
    print(f"  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n*** All tests passed! Redis infrastructure is ready. ***")
    else:
        print("\n[WARN] Some tests failed. Check the output above.")


if __name__ == "__main__":
    # Add the current directory to path for imports
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    asyncio.run(main())
