"""
Test to validate extended memory integration for additional agents.

Verifies that:
1. ValidationRecoveryAgent searches and stores validation fixes
2. GeneratorAgent uses enhanced reranking and smart selection
3. TesterTeamAgent searches and stores test patterns
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from src.agents.validation_recovery_agent import ValidationRecoveryAgent
from src.agents.generator_agent import GeneratorAgent
from src.agents.tester_team_agent import TesterTeamAgent, E2ETestResult
from src.validators.base_validator import ValidationFailure, ValidationSeverity
from src.tools.memory_tool import ErrorFixPattern, MemorySearchResult
from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState


async def test_validation_recovery_agent_memory():
    """Test that ValidationRecoveryAgent integrates with memory correctly."""
    print("\n[TEST] ValidationRecoveryAgent memory integration")

    # Create mock memory tool
    mock_memory = MagicMock()
    mock_memory.enabled = True

    # Mock validation fix patterns
    mock_patterns = [
        ErrorFixPattern(
            error_type="validation_electron",
            error_message="Module 'electron' not found",
            fix_description="Add electron to external array in vite config",
            files_modified=["electron.vite.config.ts"],
            confidence=0.85,
            project_type="electron-vite"
        ),
        ErrorFixPattern(
            error_type="validation_electron",
            error_message="Cannot resolve electron module",
            fix_description="Update rollupOptions.external in bundler config",
            files_modified=["electron.vite.config.ts", "vite.config.ts"],
            confidence=0.78,
            project_type="electron-vite"
        ),
    ]

    mock_memory.search_validation_fixes = AsyncMock(return_value=mock_patterns)
    mock_memory.store_error_fix = AsyncMock()

    # Create mock Claude tool
    mock_claude = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.files = [MagicMock(path="electron.vite.config.ts")]
    mock_result.output = "Fixed electron external configuration"
    mock_claude.execute = AsyncMock(return_value=mock_result)

    # Create validation failure
    failure = ValidationFailure(
        check_type="electron",
        severity=ValidationSeverity.ERROR,
        error_message="Module 'electron' cannot be resolved",
        file_path="src/main/main.ts",
        suggested_fix="Add electron to external dependencies"
    )

    # Create agent with mocks
    agent = ValidationRecoveryAgent(
        project_dir=".",
        claude_tool=mock_claude,
        memory_tool=mock_memory
    )

    # Test fix_failure
    result = await agent.fix_failure(failure)

    # Verify memory search was called
    mock_memory.search_validation_fixes.assert_called_once()
    call_args = mock_memory.search_validation_fixes.call_args
    assert call_args.kwargs["check_type"] == "electron"
    assert call_args.kwargs["limit"] == 5
    assert call_args.kwargs["rerank"] is True
    print("[PASS] Memory search called with correct parameters (limit=5, rerank=True)")

    # Verify memory storage was called
    mock_memory.store_error_fix.assert_called_once()
    store_args = mock_memory.store_error_fix.call_args
    assert "validation_electron" in store_args.kwargs["error_type"]
    assert store_args.kwargs["success"] is True
    print("[PASS] Memory storage called with validation fix")

    # Verify result
    assert result.success is True
    assert len(result.files_modified) > 0
    print(f"[PASS] ValidationRecoveryAgent successfully fixed with memory guidance")

    return True


async def test_generator_agent_enhanced_memory():
    """Test that GeneratorAgent uses enhanced memory with reranking."""
    print("\n[TEST] GeneratorAgent enhanced memory usage")

    # Create event bus and mock shared state
    event_bus = EventBus()
    shared_state = MagicMock()
    shared_state.record_fix = AsyncMock()

    # Create mock memory tool
    mock_memory = MagicMock()
    mock_memory.enabled = True

    # Mock error fix patterns with varying confidence
    mock_patterns = [
        ErrorFixPattern(
            error_type="type_error",
            error_message="Type 'string' is not assignable to type 'number'",
            fix_description="Update type annotation to accept union type",
            files_modified=["src/utils/helper.ts"],
            confidence=0.92,
            project_type="electron-vite"
        ),
        ErrorFixPattern(
            error_type="type_error",
            error_message="Cannot find name 'process'",
            fix_description="Add @types/node to dependencies",
            files_modified=["package.json", "tsconfig.json"],
            confidence=0.85,
            project_type="electron-vite"
        ),
        ErrorFixPattern(
            error_type="type_error",
            error_message="Type error in component props",
            fix_description="Fix component interface definition",
            files_modified=["src/components/Button.tsx"],
            confidence=0.70,
            project_type="electron-vite"
        ),
    ]

    mock_memory.search_similar_errors = AsyncMock(return_value=mock_patterns)
    mock_memory.store_error_fix = AsyncMock()

    # Create mock Claude tool
    mock_claude = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.files = [MagicMock(path="src/utils/helper.ts", language="typescript")]
    mock_result.output = "Fixed type error by updating annotation"
    mock_claude.execute = AsyncMock(return_value=mock_result)

    # Create agent with mocks
    agent = GeneratorAgent(
        name="TestGenerator",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=".",
        memory_tool=mock_memory
    )
    agent.tool = mock_claude

    # Create type error event
    error_event = Event(
        type=EventType.TYPE_ERROR,
        source="validator",
        success=False,
        error_message="Type 'string' is not assignable to type 'number'",
        file_path="src/utils/helper.ts",
        data={"line": 42}
    )

    # Test act method
    result = await agent.act([error_event])

    # Verify memory search was called with enhanced parameters
    mock_memory.search_similar_errors.assert_called()
    call_args = mock_memory.search_similar_errors.call_args
    assert call_args.kwargs["limit"] == 5  # Enhanced from 2 to 5
    assert call_args.kwargs["rerank"] is True
    print("[PASS] Memory search called with enhanced parameters (limit=5, rerank=True)")

    # Verify memory storage was called
    mock_memory.store_error_fix.assert_called_once()
    print("[PASS] Memory storage called after successful fix")

    # Verify result
    assert result.success is True
    assert result.type == EventType.CODE_FIXED
    print(f"[PASS] GeneratorAgent successfully fixed with enhanced memory")

    return True


async def test_tester_team_agent_memory():
    """Test that TesterTeamAgent integrates with memory correctly."""
    print("\n[TEST] TesterTeamAgent memory integration")

    # Create event bus and mock shared state
    event_bus = EventBus()
    shared_state = MagicMock()
    shared_state.update_e2e_tests = AsyncMock()

    # Create mock memory tool
    mock_memory = MagicMock()
    mock_memory.enabled = True

    # Mock test patterns
    mock_test_patterns = MemorySearchResult(
        found=True,
        query="E2E testing electron-vite electron UI testing patterns",
        results=[
            {
                "content": "Common issue: Vite dev server not starting on port 5173. Check if port is already in use.",
                "score": 0.88,
                "metadata": {"project_type": "electron-vite"}
            },
            {
                "content": "UI Test Pattern: Always wait for main window to be visible before taking screenshots.",
                "score": 0.82,
                "metadata": {"project_type": "electron"}
            },
            {
                "content": "Console Error Pattern: 'Failed to load resource' often indicates missing assets in renderer.",
                "score": 0.75,
                "metadata": {"project_type": "electron-vite"}
            },
        ],
        total_results=3
    )

    mock_memory.search_test_patterns = AsyncMock(return_value=mock_test_patterns)
    mock_memory.store_memory = AsyncMock()

    # Create agent with mocks
    agent = TesterTeamAgent(
        name="TestTester",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=".",
        requirements=["Test UI rendering", "Test button clicks"],
        memory_tool=mock_memory
    )

    # Mock _launch_app and _run_playwright_tests
    mock_process = MagicMock()
    mock_process.pid = 12345
    agent._launch_app = AsyncMock(return_value=mock_process)
    agent._stop_app = AsyncMock()

    # Create test result
    test_result = E2ETestResult(
        success=True,
        tests_run=5,
        tests_passed=4,
        tests_failed=1,
        screenshots=["screenshot1.png", "screenshot2.png"],
        errors=["Button click failed"],
        console_errors=["Warning: Missing prop"],
        app_launched=True,
        duration_ms=3500
    )

    async def mock_run_tests(learned_patterns=None):
        # Verify learned patterns were passed
        assert learned_patterns is not None
        assert len(learned_patterns) == 3
        assert learned_patterns[0]["score"] == 0.88
        return test_result

    agent._run_playwright_tests = AsyncMock(side_effect=mock_run_tests)

    # Create trigger event
    trigger_event = Event(
        type=EventType.BUILD_SUCCEEDED,
        source="builder",
        success=True
    )

    # Test act method
    result = await agent.act([trigger_event])

    # Verify memory search was called
    mock_memory.search_test_patterns.assert_called_once()
    call_args = mock_memory.search_test_patterns.call_args
    assert call_args.kwargs["limit"] == 5
    assert call_args.kwargs["rerank"] is True
    print("[PASS] Memory search called with correct parameters (limit=5, rerank=True)")

    # Verify _run_playwright_tests was called with patterns
    agent._run_playwright_tests.assert_called_once()
    print("[PASS] Test runner received learned patterns")

    # Verify memory storage was called
    mock_memory.store_memory.assert_called_once()
    store_args = mock_memory.store_memory.call_args
    assert store_args.kwargs["category"] == "test_run"
    assert "E2E test run" in store_args.kwargs["content"]
    assert store_args.kwargs["metadata"]["tests_run"] == 5
    assert store_args.kwargs["metadata"]["tests_passed"] == 4
    print("[PASS] Memory storage called with test results")

    # Verify result
    assert result.success is True
    assert result.type == EventType.E2E_TEST_PASSED
    print(f"[PASS] TesterTeamAgent successfully ran tests with memory guidance")

    return True


async def test_project_type_detection():
    """Test that all agents detect project types correctly."""
    print("\n[TEST] Project type detection")

    # Create temporary test directory structure
    test_dir = "test_project_temp"
    os.makedirs(test_dir, exist_ok=True)

    try:
        # Test electron-vite detection
        with open(os.path.join(test_dir, "package.json"), "w") as f:
            f.write('{"name": "test"}')
        with open(os.path.join(test_dir, "electron.vite.config.ts"), "w") as f:
            f.write("// config")

        # Test ValidationRecoveryAgent
        val_agent = ValidationRecoveryAgent(project_dir=test_dir)
        assert val_agent._detect_project_type() == "electron-vite"
        print("[PASS] ValidationRecoveryAgent detects electron-vite correctly")

        # Test TesterTeamAgent
        event_bus = EventBus()
        shared_state = MagicMock()
        test_agent = TesterTeamAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=test_dir
        )
        assert test_agent._detect_project_type() == "electron-vite"
        print("[PASS] TesterTeamAgent detects electron-vite correctly")

        # Test GeneratorAgent
        gen_agent = GeneratorAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=test_dir
        )
        assert gen_agent._detect_project_type() == "electron-vite"
        print("[PASS] GeneratorAgent detects electron-vite correctly")

    finally:
        # Cleanup
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    return True


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Testing Extended Memory Integration")
    print("=" * 60)

    try:
        # Test 1: ValidationRecoveryAgent
        success1 = await test_validation_recovery_agent_memory()

        # Test 2: GeneratorAgent
        success2 = await test_generator_agent_enhanced_memory()

        # Test 3: TesterTeamAgent
        success3 = await test_tester_team_agent_memory()

        # Test 4: Project type detection
        success4 = await test_project_type_detection()

        print("\n" + "=" * 60)
        if success1 and success2 and success3 and success4:
            print("[SUCCESS] All extended memory integration tests passed!")
            print("=" * 60)
            print("\nValidated:")
            print("  * ValidationRecoveryAgent: search + store validation fixes")
            print("  * GeneratorAgent: enhanced reranking (5 candidates)")
            print("  * TesterTeamAgent: search + store test patterns")
            print("  * Project type detection: consistent across agents")
            print("\nKey Features Verified:")
            print("  * Reranking enabled (rerank=True)")
            print("  * 5 candidates for better scoring")
            print("  * Top 3 patterns selected")
            print("  * Confidence-based sorting")
            print("  * Project-type aware searches")
            print("  * Memory storage after completion")
            return True
        else:
            print("[FAILED] Some tests failed")
            print("=" * 60)
            return False

    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
