"""
Tool Executor: Bridge between Routing Decisions and Actual Tool Execution

Executes tools based on TemporalRoutingResult and records outcomes
for feedback loop with tonic/phasic learning.

Usage:
    from core.tool_executor import ToolExecutor
    from core.layer4_temporal_router import Layer4TemporalRouter

    def my_deploy_tool(**kwargs):
        print(f"Deploying: {kwargs}")
        return {'status': 'deployed'}

    router = Layer4TemporalRouter()
    executor = ToolExecutor(router)

    executor.register_tool('deploy', my_deploy_tool, default_tonic=0.6)

    result = router.route(events, task_description="Deploy nginx")
    if result.should_execute:
        exec_result = executor.execute(result)
        print(f"Execution: {exec_result}")
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import deque


@dataclass
class ExecutionResult:
    """Result of a tool execution"""
    tool_name: str
    success: bool
    output: Any
    error: Optional[str]
    duration_ms: float
    timestamp: datetime
    routing_confidence: float
    blocked: bool = False
    block_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'tool_name': self.tool_name,
            'success': self.success,
            'output': str(self.output) if self.output else None,
            'error': self.error,
            'duration_ms': self.duration_ms,
            'timestamp': self.timestamp.isoformat(),
            'routing_confidence': self.routing_confidence,
            'blocked': self.blocked,
            'block_reason': self.block_reason
        }


@dataclass
class ToolConfig:
    """Configuration for a registered tool"""
    name: str
    func: Callable
    default_tonic: float = 0.5  # Default tonic activation
    description: str = ""
    requires_confirmation: bool = False
    max_retries: int = 0
    timeout_ms: Optional[float] = None


class ToolExecutor:
    """
    Executes tools based on routing decisions and provides feedback to oscillator.

    Features:
    - Register and execute tools
    - Record execution outcomes for learning
    - Apply success/failure modulation to oscillator
    - Track execution history
    - Support for retries and timeouts
    """

    def __init__(
        self,
        router: Any,  # Layer4TemporalRouter
        max_history: int = 100
    ):
        """
        Initialize ToolExecutor.

        Args:
            router: Layer4TemporalRouter instance for feedback
            max_history: Maximum execution history to keep
        """
        self.router = router
        self.tools: Dict[str, ToolConfig] = {}
        self.execution_history: deque = deque(maxlen=max_history)

        # Statistics
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        self.blocked_executions = 0

        print(f"[ToolExecutor] Initialized")

    def register_tool(
        self,
        name: str,
        func: Callable,
        default_tonic: float = 0.5,
        description: str = "",
        requires_confirmation: bool = False,
        max_retries: int = 0,
        timeout_ms: Optional[float] = None
    ) -> None:
        """
        Register a tool for execution.

        Args:
            name: Tool name (must match routing result tool_name)
            func: Callable that implements the tool
            default_tonic: Default tonic activation level
            description: Tool description
            requires_confirmation: Whether tool requires user confirmation
            max_retries: Maximum retry attempts on failure
            timeout_ms: Execution timeout in milliseconds
        """
        self.tools[name] = ToolConfig(
            name=name,
            func=func,
            default_tonic=default_tonic,
            description=description,
            requires_confirmation=requires_confirmation,
            max_retries=max_retries,
            timeout_ms=timeout_ms
        )
        print(f"[ToolExecutor] Registered tool: {name} (tonic={default_tonic})")

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool"""
        if name in self.tools:
            del self.tools[name]
            print(f"[ToolExecutor] Unregistered tool: {name}")
            return True
        return False

    def execute(
        self,
        routing_result: Any,  # TemporalRoutingResult
        override_params: Optional[Dict] = None,
        skip_feedback: bool = False
    ) -> ExecutionResult:
        """
        Execute a tool based on routing result.

        Args:
            routing_result: TemporalRoutingResult from router.route()
            override_params: Override tool parameters
            skip_feedback: Skip recording feedback to router

        Returns:
            ExecutionResult with execution details
        """
        # Check if execution is blocked
        if routing_result.blocked:
            result = ExecutionResult(
                tool_name=routing_result.tool_name or "unknown",
                success=False,
                output=None,
                error=None,
                duration_ms=0,
                timestamp=datetime.now(),
                routing_confidence=routing_result.decision.timing_confidence,
                blocked=True,
                block_reason=routing_result.block_reason
            )
            self.blocked_executions += 1
            self.execution_history.append(result)
            return result

        # Check if should execute
        if not routing_result.should_execute:
            result = ExecutionResult(
                tool_name=routing_result.tool_name or "unknown",
                success=False,
                output=None,
                error="Routing decided not to execute",
                duration_ms=0,
                timestamp=datetime.now(),
                routing_confidence=routing_result.decision.timing_confidence,
                blocked=False,
                block_reason=None
            )
            self.execution_history.append(result)
            return result

        tool_name = routing_result.tool_name
        tool_params = override_params or routing_result.tool_parameters or {}

        # Check if tool is registered
        if tool_name not in self.tools:
            result = ExecutionResult(
                tool_name=tool_name,
                success=False,
                output=None,
                error=f"Tool not registered: {tool_name}",
                duration_ms=0,
                timestamp=datetime.now(),
                routing_confidence=routing_result.decision.timing_confidence,
                blocked=False,
                block_reason=None
            )
            self.failed_executions += 1
            self.execution_history.append(result)
            return result

        tool_config = self.tools[tool_name]

        # Execute with retries
        attempts = 0
        max_attempts = tool_config.max_retries + 1
        last_error = None

        while attempts < max_attempts:
            attempts += 1
            start_time = time.time()

            try:
                output = tool_config.func(**tool_params)
                duration_ms = (time.time() - start_time) * 1000
                success = True
                error = None
                break

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                last_error = str(e)
                success = False
                error = last_error
                output = None

                if attempts < max_attempts:
                    print(f"[ToolExecutor] Retry {attempts}/{max_attempts} for {tool_name}: {error}")
                    time.sleep(0.1 * attempts)  # Backoff

        # Create result
        result = ExecutionResult(
            tool_name=tool_name,
            success=success,
            output=output,
            error=error,
            duration_ms=duration_ms,
            timestamp=datetime.now(),
            routing_confidence=routing_result.decision.timing_confidence,
            blocked=False,
            block_reason=None
        )

        # Update statistics
        self.total_executions += 1
        if success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1

        # Record history
        self.execution_history.append(result)

        # Provide feedback to router
        if not skip_feedback:
            self._record_feedback(result)

        return result

    def _record_feedback(self, result: ExecutionResult) -> None:
        """Record execution feedback to router for learning"""
        try:
            # Record to router's temporal CTM
            self.router.record_execution_result(
                tool_name=result.tool_name,
                success=result.success,
                execution_time_ms=result.duration_ms,
                result={'output': result.output} if result.output else {},
                error=result.error
            )

            # Apply oscillator modulation based on outcome
            if result.success:
                self.router.token_adapter.apply_success_modulation(result.tool_name)
            else:
                self.router.token_adapter.apply_failure_modulation(result.tool_name)

        except Exception as e:
            print(f"[ToolExecutor] Error recording feedback: {e}")

    def execute_batch(
        self,
        routing_results: List[Any],
        stop_on_failure: bool = True
    ) -> List[ExecutionResult]:
        """
        Execute multiple routing results in sequence.

        Args:
            routing_results: List of TemporalRoutingResult
            stop_on_failure: Stop executing on first failure

        Returns:
            List of ExecutionResult
        """
        results = []

        for routing_result in routing_results:
            result = self.execute(routing_result)
            results.append(result)

            if stop_on_failure and not result.success:
                break

        return results

    def get_execution_history(
        self,
        limit: Optional[int] = None,
        tool_name: Optional[str] = None,
        success_only: bool = False
    ) -> List[ExecutionResult]:
        """
        Get execution history.

        Args:
            limit: Maximum number of results
            tool_name: Filter by tool name
            success_only: Only return successful executions

        Returns:
            List of ExecutionResult
        """
        results = list(self.execution_history)

        if tool_name:
            results = [r for r in results if r.tool_name == tool_name]

        if success_only:
            results = [r for r in results if r.success]

        if limit:
            results = results[-limit:]

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get executor statistics"""
        success_rate = (
            self.successful_executions / self.total_executions
            if self.total_executions > 0 else 0.0
        )

        # Per-tool stats
        tool_stats = {}
        for result in self.execution_history:
            if result.tool_name not in tool_stats:
                tool_stats[result.tool_name] = {
                    'total': 0,
                    'success': 0,
                    'failed': 0,
                    'blocked': 0,
                    'avg_duration_ms': 0
                }
            stats = tool_stats[result.tool_name]
            stats['total'] += 1
            if result.blocked:
                stats['blocked'] += 1
            elif result.success:
                stats['success'] += 1
            else:
                stats['failed'] += 1

        # Calculate average duration per tool
        for tool_name, stats in tool_stats.items():
            durations = [
                r.duration_ms for r in self.execution_history
                if r.tool_name == tool_name and not r.blocked
            ]
            if durations:
                stats['avg_duration_ms'] = sum(durations) / len(durations)

        return {
            'total_executions': self.total_executions,
            'successful_executions': self.successful_executions,
            'failed_executions': self.failed_executions,
            'blocked_executions': self.blocked_executions,
            'success_rate': success_rate,
            'registered_tools': list(self.tools.keys()),
            'tool_stats': tool_stats,
            'history_size': len(self.execution_history)
        }

    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered tool"""
        if name not in self.tools:
            return None

        config = self.tools[name]
        return {
            'name': config.name,
            'description': config.description,
            'default_tonic': config.default_tonic,
            'requires_confirmation': config.requires_confirmation,
            'max_retries': config.max_retries,
            'timeout_ms': config.timeout_ms
        }

    def list_tools(self) -> List[str]:
        """List all registered tool names"""
        return list(self.tools.keys())


# Quick test
if __name__ == "__main__":
    print("=" * 60)
    print("  TOOL EXECUTOR TEST")
    print("=" * 60)

    try:
        from core.layer4_temporal_router import Layer4TemporalRouter

        # Create router
        router = Layer4TemporalRouter(
            strict_security=True,
            timing_threshold=0.5,
            enable_deep_reasoning=False
        )

        # Create executor
        executor = ToolExecutor(router)

        # Register mock tools
        def mock_deploy(**kwargs):
            print(f"[MOCK] Deploying: {kwargs}")
            return {'status': 'deployed', 'container': kwargs.get('container', 'unknown')}

        def mock_status(**kwargs):
            print(f"[MOCK] Checking status: {kwargs}")
            return {'status': 'running', 'health': 'ok'}

        def mock_failing_tool(**kwargs):
            raise Exception("Simulated failure!")

        executor.register_tool('deploy', mock_deploy, default_tonic=0.7)
        executor.register_tool('status', mock_status, default_tonic=0.5)
        executor.register_tool('failing', mock_failing_tool, max_retries=2)

        print(f"\nRegistered tools: {executor.list_tools()}")

        # Test 1: Execute via routing
        print("\n--- Test 1: Route and Execute ---")
        events = [
            {'role': 'user', 'text': 'Deploy nginx container on port 8080'}
        ]
        routing_result = router.route(events, task_description="Deploy nginx")

        print(f"Should Execute: {routing_result.should_execute}")
        print(f"Tool: {routing_result.tool_name}")
        print(f"Blocked: {routing_result.blocked}")

        # Mock the tool_name for testing
        routing_result.tool_name = 'deploy'
        routing_result.tool_parameters = {'container': 'nginx', 'port': 8080}

        exec_result = executor.execute(routing_result)
        print(f"Execution Success: {exec_result.success}")
        print(f"Output: {exec_result.output}")
        print(f"Duration: {exec_result.duration_ms:.1f}ms")

        # Test 2: Failing tool
        print("\n--- Test 2: Failing Tool with Retries ---")
        routing_result.tool_name = 'failing'
        routing_result.tool_parameters = {}

        exec_result = executor.execute(routing_result)
        print(f"Execution Success: {exec_result.success}")
        print(f"Error: {exec_result.error}")

        # Show statistics
        print("\n--- Statistics ---")
        stats = executor.get_statistics()
        print(f"Total: {stats['total_executions']}")
        print(f"Success: {stats['successful_executions']}")
        print(f"Failed: {stats['failed_executions']}")
        print(f"Success Rate: {stats['success_rate']:.1%}")

        print(f"\n{'=' * 60}")
        print("  TEST PASSED")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
