#!/usr/bin/env python3
"""Test all component imports"""
import sys

print('Testing component imports...\n')

try:
    from tool_category_filter import ToolCategoryFilter
    print('  tool_category_filter: OK')
except Exception as e:
    print(f'  tool_category_filter: FAILED - {e}')

try:
    from smart_agent_selector import SmartAgentSelector
    print('  smart_agent_selector: OK')
except Exception as e:
    print(f'  smart_agent_selector: FAILED - {e}')

try:
    from tool_execution_cache import ToolExecutionCache
    print('  tool_execution_cache: OK')
except Exception as e:
    print(f'  tool_execution_cache: FAILED - {e}')

try:
    from parallel_executor import ParallelExecutor
    print('  parallel_executor: OK')
except Exception as e:
    print(f'  parallel_executor: FAILED - {e}')

try:
    from error_classifier import ErrorClassifier
    print('  error_classifier: OK')
except Exception as e:
    print(f'  error_classifier: FAILED - {e}')

try:
    from recovery_strategies import RecoveryOrchestrator
    print('  recovery_strategies: OK')
except Exception as e:
    print(f'  recovery_strategies: FAILED - {e}')

try:
    from circuit_breaker import ToolCircuitBreaker
    print('  circuit_breaker: OK')
except Exception as e:
    print(f'  circuit_breaker: FAILED - {e}')

try:
    from execution_history import ExecutionHistoryStore
    print('  execution_history: OK')
except Exception as e:
    print(f'  execution_history: FAILED - {e}')

try:
    from orchestrator_metrics import OrchestratorMetrics
    print('  orchestrator_metrics: OK')
except Exception as e:
    print(f'  orchestrator_metrics: FAILED - {e}')

try:
    from adaptive_prompts import AdaptivePromptGenerator
    print('  adaptive_prompts: OK')
except Exception as e:
    print(f'  adaptive_prompts: FAILED - {e}')

print('\n--- Testing autogen_orchestrator import ---')
try:
    # Need the parent paths for shared modules
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

    from autogen_orchestrator import EventFixOrchestrator
    print('  autogen_orchestrator: OK')
except Exception as e:
    print(f'  autogen_orchestrator: FAILED - {e}')

print('\n=== All imports completed ===')
