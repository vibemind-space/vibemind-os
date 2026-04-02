#!/usr/bin/env python3
from src.llm_config import get_model
"""
Comprehensive Orchestrator Test - All 5 Iterations

Tests all new components:
- Iteration 1: Tool Category Filtering
- Iteration 2: Smart Agent Selector
- Iteration 3: Tool Execution Cache + Parallel Executor
- Iteration 4: Error Classification + Circuit Breaker
- Iteration 5: Execution History + Metrics + Adaptive Prompts
"""

import asyncio
import json
import sys
import os
import time

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

async def test_all_components():
    """Test all orchestrator components"""
    print("=" * 70)
    print("ORCHESTRATOR FULL TEST - ALL 5 ITERATIONS")
    print("=" * 70)
    print()

    results = {
        "passed": 0,
        "failed": 0,
        "tests": []
    }

    def log_test(name: str, passed: bool, details: str = ""):
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        if details:
            print(f"       {details}")
        results["tests"].append({"name": name, "passed": passed, "details": details})
        if passed:
            results["passed"] += 1
        else:
            results["failed"] += 1

    # =========================================================================
    # Iteration 1: Tool Category Filter
    # =========================================================================
    print("\n--- ITERATION 1: Tool Category Filter ---\n")

    try:
        from tool_category_filter import ToolCategoryFilter, DynamicPromptGenerator

        class MockTool:
            def __init__(self, name):
                self.name = name

        tools = [MockTool(f"filesystem_{op}") for op in ["read_file", "write_file", "list_directory"]]
        tools += [MockTool(f"docker_{op}") for op in ["container_logs", "compose_up"]]
        tools += [MockTool(f"git_{op}") for op in ["status", "commit"]]

        filter = ToolCategoryFilter(max_tools=30)

        # Test filtering
        result = filter.filter_for_task(tools, "write_code")
        log_test(
            "Tool filtering for write_code",
            len(result.tools) < len(tools),
            f"Filtered {len(tools)} -> {len(result.tools)} tools"
        )

        # Test dynamic prompt
        prompt_gen = DynamicPromptGenerator(filter)
        prompt = prompt_gen.generate_prompt(result, "write_code")
        log_test(
            "Dynamic prompt generation",
            len(prompt) > 100 and "Filesystem" in prompt,
            f"Generated {len(prompt)} char prompt"
        )

    except Exception as e:
        log_test("Iteration 1 components", False, str(e))

    # =========================================================================
    # Iteration 2: Smart Agent Selector
    # =========================================================================
    print("\n--- ITERATION 2: Smart Agent Selector ---\n")

    try:
        from smart_agent_selector import SmartAgentSelector

        selector = SmartAgentSelector(max_consecutive_errors=2)

        # Normal selection
        result = selector.select_next_agent("ReasoningAgent")
        log_test(
            "Normal agent selection",
            result.selected_agent == "ValidatorAgent",
            f"Selected: {result.selected_agent}"
        )

        # Error detection
        selector.reset()
        selector.update_context({"content": "Error: file not found", "source": "tool"})
        selector.update_context({"content": "Failed to write", "source": "tool"})
        result = selector.select_next_agent("ReasoningAgent")
        log_test(
            "Error detection switches to FixAgent",
            result.selected_agent == "FixSuggestionAgent",
            f"Selected: {result.selected_agent}, reason: {result.reason}"
        )

    except Exception as e:
        log_test("Iteration 2 components", False, str(e))

    # =========================================================================
    # Iteration 3: Cache + Parallel Executor
    # =========================================================================
    print("\n--- ITERATION 3: Cache + Parallel Executor ---\n")

    try:
        from tool_execution_cache import ToolExecutionCache
        from parallel_executor import ParallelExecutor, ToolCall

        # Cache test
        cache = ToolExecutionCache(max_entries=100)
        cache.set("filesystem_read_file", {"path": "/test.txt"}, "content")
        cached = cache.get("filesystem_read_file", {"path": "/test.txt"})
        log_test(
            "Tool execution caching",
            cached == "content",
            f"Cache stats: {cache.get_stats()['hit_rate']}"
        )

        # Parallel executor test
        async def mock_execute(tool, args):
            await asyncio.sleep(0.05)
            return f"Result: {tool}"

        executor = ParallelExecutor(max_parallel=3, cache=cache)
        calls = [
            ToolCall("filesystem_read_file", {"path": f"/file{i}.txt"}, f"call_{i}")
            for i in range(5)
        ]
        plan = executor.create_execution_plan(calls)
        log_test(
            "Parallel execution planning",
            len(plan.batches) <= 2,
            f"5 calls in {len(plan.batches)} batches"
        )

        start = time.time()
        results_exec = await executor.execute_calls(calls, mock_execute)
        duration = time.time() - start
        log_test(
            "Parallel execution",
            len(results_exec) == 5 and duration < 0.3,
            f"5 calls in {duration:.2f}s (parallel)"
        )

    except Exception as e:
        log_test("Iteration 3 components", False, str(e))

    # =========================================================================
    # Iteration 4: Error Classification + Circuit Breaker
    # =========================================================================
    print("\n--- ITERATION 4: Error Classification + Circuit Breaker ---\n")

    try:
        from error_classifier import ErrorClassifier, ErrorType
        from circuit_breaker import ToolCircuitBreaker, CircuitState

        # Error classification
        classifier = ErrorClassifier()
        errors = [
            ("ENOENT: no such file", ErrorType.NOT_FOUND),
            ("permission denied", ErrorType.PERMISSION),
            ("connection refused", ErrorType.CONNECTION),
            ("SyntaxError: unexpected token", ErrorType.SYNTAX),
        ]
        all_correct = True
        for msg, expected_type in errors:
            result = classifier.classify(msg)
            if result.error_type != expected_type:
                all_correct = False
                print(f"       Mismatch: '{msg}' -> {result.error_type} (expected {expected_type})")

        log_test(
            "Error classification",
            all_correct,
            f"Classified {len(errors)} error types correctly"
        )

        # Circuit breaker
        breaker = ToolCircuitBreaker(failure_threshold=2, timeout_seconds=1)
        tool = "test_tool"

        breaker.record_failure(tool)
        breaker.record_failure(tool)

        log_test(
            "Circuit breaker opens after failures",
            breaker.is_open(tool),
            f"State: {breaker.get_state(tool).value}"
        )

        # Wait for timeout
        await asyncio.sleep(1.5)
        log_test(
            "Circuit breaker transitions to half-open",
            breaker.get_state(tool) == CircuitState.HALF_OPEN,
            f"State after timeout: {breaker.get_state(tool).value}"
        )

    except Exception as e:
        log_test("Iteration 4 components", False, str(e))

    # =========================================================================
    # Iteration 5: History + Metrics + Adaptive Prompts
    # =========================================================================
    print("\n--- ITERATION 5: History + Metrics + Adaptive Prompts ---\n")

    try:
        from execution_history import ExecutionHistoryStore, ToolExecution
        from orchestrator_metrics import OrchestratorMetrics
        from adaptive_prompts import AdaptivePromptGenerator
        import tempfile
        from pathlib import Path

        # Execution history
        db_path = Path(tempfile.gettempdir()) / "test_history.db"
        if db_path.exists():
            db_path.unlink()

        history = ExecutionHistoryStore(str(db_path))
        session = f"test_{int(time.time())}"

        for i in range(5):
            history.record(ToolExecution(
                tool_name="filesystem_read_file",
                success=True,
                duration_ms=50 + i * 10,
                task_type="write_code",
                session_id=session
            ))

        stats = history.get_tool_stats("filesystem_read_file")
        log_test(
            "Execution history recording",
            stats.total_calls == 5 and stats.success_rate == 100.0,
            f"Recorded 5 calls, success_rate={stats.success_rate}%"
        )

        # Cleanup
        db_path.unlink()

        # Metrics
        metrics = OrchestratorMetrics()
        metrics.record_task_started()
        metrics.record_task_completed(True, 1000)
        metrics.record_tool_call("test_tool", True, 100, False)

        export = metrics.export_for_dashboard()
        log_test(
            "Orchestrator metrics",
            export["counters"]["tasks_total"] == 1,
            f"Tasks: {export['counters']['tasks_total']}, Tools: {export['counters']['tool_calls_total']}"
        )

        # Adaptive prompts
        from tool_category_filter import ToolCategoryFilter
        filter = ToolCategoryFilter()
        prompt_gen = AdaptivePromptGenerator(tool_filter=filter)

        tools = ["filesystem_read_file", "filesystem_write_file", "git_status"]
        prompt = prompt_gen.generate_reasoning_prompt("write_code", "Test task", tools)
        log_test(
            "Adaptive prompt generation",
            len(prompt) > 100,
            f"Generated {len(prompt)} char adaptive prompt"
        )

    except Exception as e:
        log_test("Iteration 5 components", False, str(e))

    # =========================================================================
    # Full Orchestrator Import
    # =========================================================================
    print("\n--- FULL ORCHESTRATOR ---\n")

    try:
        from autogen_orchestrator import EventFixOrchestrator

        orchestrator = EventFixOrchestrator(
            model=get_model("mcp_standard"),
            max_turns=5
        )

        status = orchestrator.get_status()
        log_test(
            "Orchestrator initialization",
            not status["initialized"],  # Not initialized yet
            f"Status keys: {list(status.keys())[:5]}..."
        )

        # Check all new components are in status
        expected_keys = ["cache_stats", "circuit_breaker_health", "metrics"]
        has_all_keys = all(k in status for k in expected_keys)
        log_test(
            "All iteration components integrated",
            has_all_keys,
            f"Has cache_stats: {('cache_stats' in status)}, circuit_breaker: {('circuit_breaker_health' in status)}"
        )

    except Exception as e:
        log_test("Full orchestrator", False, str(e))

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Total:  {results['passed'] + results['failed']}")
    print()

    if results['failed'] > 0:
        print("Failed tests:")
        for test in results['tests']:
            if not test['passed']:
                print(f"  - {test['name']}: {test['details']}")

    print("\n" + "=" * 70)

    return results['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(test_all_components())
    sys.exit(0 if success else 1)
