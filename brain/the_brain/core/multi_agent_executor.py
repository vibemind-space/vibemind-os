"""
Multi-Agent Tool Executor: Coordinated Parallel Tool Execution

Orchestrates multiple tool executors across specialized domains with:
- Domain-specific tool pools (docker, filesystem, network, etc.)
- Parallel tool execution with dependency tracking
- Consensus-based execution decisions
- Load balancing across executors
- Execution pipeline coordination

Usage:
    from core.multi_agent_executor import MultiAgentExecutor
    from core.layer4_temporal_router import Layer4TemporalRouter

    router = Layer4TemporalRouter()
    multi_executor = MultiAgentExecutor(router)

    # Register domain executors
    multi_executor.register_domain('docker', docker_tools)
    multi_executor.register_domain('filesystem', fs_tools)

    # Execute pipeline with dependencies
    pipeline = [
        {'id': 'step1', 'tool': 'docker_build', 'params': {...}},
        {'id': 'step2', 'tool': 'docker_push', 'depends_on': ['step1']},
    ]
    results = multi_executor.execute_pipeline(pipeline)
"""

import time
import threading
import queue
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

# Import custom exceptions
try:
    from .exceptions import (
        ToolExecutionError,
        ToolNotFoundError,
        ToolTimeoutError,
        ToolBlockedError
    )
except ImportError:
    # Fallback exceptions
    class ToolExecutionError(Exception):
        pass
    class ToolNotFoundError(Exception):
        pass
    class ToolTimeoutError(Exception):
        pass
    class ToolBlockedError(Exception):
        pass

# Import logger
try:
    from .brain_logger import get_logger
    logger = get_logger('multi_executor')
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

class ExecutionStatus(Enum):
    """Status of a pipeline step"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class DomainExecutor:
    """
    A specialized executor for a specific domain.

    Each domain (docker, filesystem, network) has its own
    executor with domain-specific tools and configuration.
    """
    domain: str
    tools: Dict[str, Callable] = field(default_factory=dict)

    # Performance tracking
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    avg_execution_time_ms: float = 0.0

    # Configuration
    max_concurrent: int = 3
    default_timeout_ms: float = 30000.0
    retry_count: int = 1

    # State
    current_load: int = 0
    is_available: bool = True

    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.successful_executions + self.failed_executions
        return self.successful_executions / total if total > 0 else 0.5

    def can_accept_work(self) -> bool:
        """Check if executor can accept more work"""
        return self.is_available and self.current_load < self.max_concurrent

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'domain': self.domain,
            'tools': list(self.tools.keys()),
            'total_executions': self.total_executions,
            'success_rate': self.success_rate(),
            'avg_execution_time_ms': self.avg_execution_time_ms,
            'current_load': self.current_load,
            'max_concurrent': self.max_concurrent,
            'is_available': self.is_available
        }


@dataclass
class PipelineStep:
    """
    A step in an execution pipeline.

    Steps can have dependencies on other steps and will only
    execute once all dependencies are complete.
    """
    step_id: str
    tool_name: str
    domain: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Dependencies
    depends_on: List[str] = field(default_factory=list)

    # Status
    status: ExecutionStatus = ExecutionStatus.PENDING

    # Result
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Configuration
    timeout_ms: float = 30000.0
    retries: int = 1
    critical: bool = True  # If true, failure stops pipeline

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'step_id': self.step_id,
            'tool_name': self.tool_name,
            'domain': self.domain,
            'status': self.status.value,
            'depends_on': self.depends_on,
            'duration_ms': self.duration_ms,
            'error': self.error,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


@dataclass
class PipelineResult:
    """Result of a pipeline execution"""
    pipeline_id: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    skipped_steps: int

    # Status
    success: bool
    overall_status: str

    # Results per step
    step_results: Dict[str, Dict] = field(default_factory=dict)

    # Timing
    total_duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'pipeline_id': self.pipeline_id,
            'total_steps': self.total_steps,
            'completed_steps': self.completed_steps,
            'failed_steps': self.failed_steps,
            'skipped_steps': self.skipped_steps,
            'success': self.success,
            'overall_status': self.overall_status,
            'total_duration_ms': self.total_duration_ms,
            'step_results': self.step_results
        }


@dataclass
class ConsensusVote:
    """A vote from an executor on whether to proceed"""
    executor_domain: str
    should_execute: bool
    confidence: float
    reason: str


# =============================================================================
# MULTI-AGENT EXECUTOR
# =============================================================================

class MultiAgentExecutor:
    """
    Coordinates multiple tool executors across specialized domains.

    Features:
    - Domain-specific tool pools (docker, filesystem, network)
    - Parallel tool execution with dependency tracking
    - Consensus-based execution decisions
    - Load balancing across executors
    - Pipeline execution with automatic dependency resolution
    """

    def __init__(
        self,
        router: Any = None,
        max_workers: int = 10,
        consensus_threshold: float = 0.6,
        enable_load_balancing: bool = True
    ):
        """
        Initialize MultiAgentExecutor.

        Args:
            router: Layer4TemporalRouter for routing feedback
            max_workers: Maximum concurrent worker threads
            consensus_threshold: Minimum agreement for execution
            enable_load_balancing: Enable load balancing across executors
        """
        self.router = router
        self.max_workers = max_workers
        self.consensus_threshold = consensus_threshold
        self.enable_load_balancing = enable_load_balancing

        # Domain executors
        self.domains: Dict[str, DomainExecutor] = {}

        # Tool to domain mapping
        self.tool_to_domain: Dict[str, str] = {}

        # Thread pool for parallel execution
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        # Pipeline tracking
        self.active_pipelines: Dict[str, List[PipelineStep]] = {}
        self.pipeline_history: List[PipelineResult] = []

        # Statistics
        self.total_pipelines = 0
        self.successful_pipelines = 0
        self.failed_pipelines = 0
        self.total_parallel_executions = 0

        # Lock for thread safety
        self._lock = threading.Lock()

        # Initialize default domains
        self._initialize_default_domains()

        logger.info(f"MultiAgentExecutor initialized (workers={max_workers})")

    def _initialize_default_domains(self):
        """Initialize default domain executors"""
        default_domains = [
            ('docker', {'max_concurrent': 3, 'default_timeout_ms': 60000.0}),
            ('filesystem', {'max_concurrent': 5, 'default_timeout_ms': 10000.0}),
            ('network', {'max_concurrent': 4, 'default_timeout_ms': 30000.0}),
            ('terminal', {'max_concurrent': 2, 'default_timeout_ms': 120000.0}),
            ('database', {'max_concurrent': 3, 'default_timeout_ms': 30000.0}),
        ]

        for domain_name, config in default_domains:
            self.domains[domain_name] = DomainExecutor(
                domain=domain_name,
                **config
            )

    def register_domain(
        self,
        domain: str,
        tools: Dict[str, Callable],
        max_concurrent: int = 3,
        default_timeout_ms: float = 30000.0,
        retry_count: int = 1
    ) -> None:
        """
        Register a domain with its tools.

        Args:
            domain: Domain name (e.g., 'docker', 'filesystem')
            tools: Dictionary of tool_name -> callable
            max_concurrent: Maximum concurrent executions
            default_timeout_ms: Default timeout for tools
            retry_count: Number of retries on failure
        """
        with self._lock:
            if domain not in self.domains:
                self.domains[domain] = DomainExecutor(domain=domain)

            executor = self.domains[domain]
            executor.tools.update(tools)
            executor.max_concurrent = max_concurrent
            executor.default_timeout_ms = default_timeout_ms
            executor.retry_count = retry_count

            # Update tool to domain mapping
            for tool_name in tools:
                self.tool_to_domain[tool_name] = domain

            logger.info(f"Registered domain '{domain}' with {len(tools)} tools")

    def register_tool(
        self,
        tool_name: str,
        func: Callable,
        domain: str
    ) -> None:
        """
        Register a single tool in a domain.

        Args:
            tool_name: Name of the tool
            func: Callable implementing the tool
            domain: Domain to register tool in
        """
        if domain not in self.domains:
            self.domains[domain] = DomainExecutor(domain=domain)

        with self._lock:
            self.domains[domain].tools[tool_name] = func
            self.tool_to_domain[tool_name] = domain

        logger.debug(f"Registered tool '{tool_name}' in domain '{domain}'")

    def get_domain_for_tool(self, tool_name: str) -> Optional[str]:
        """Get the domain for a tool"""
        return self.tool_to_domain.get(tool_name)

    def _select_executor(self, domain: str) -> Optional[DomainExecutor]:
        """
        Select the best executor for a domain.

        Args:
            domain: Target domain

        Returns:
            DomainExecutor or None if unavailable
        """
        if domain not in self.domains:
            return None

        executor = self.domains[domain]

        if not executor.can_accept_work():
            logger.warning(f"Domain '{domain}' is at capacity")
            return None

        return executor

    def execute_single(
        self,
        tool_name: str,
        parameters: Dict[str, Any] = None,
        timeout_ms: float = None
    ) -> Dict[str, Any]:
        """
        Execute a single tool.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            timeout_ms: Execution timeout

        Returns:
            Execution result dictionary
        """
        parameters = parameters or {}

        # Find domain for tool
        domain = self.get_domain_for_tool(tool_name)
        if not domain:
            raise ToolNotFoundError(tool_name)

        executor = self._select_executor(domain)
        if not executor:
            raise ToolExecutionError(
                f"Domain '{domain}' unavailable",
                tool_name=tool_name
            )

        if tool_name not in executor.tools:
            raise ToolNotFoundError(tool_name)

        # Execute tool
        start_time = time.time()
        timeout = timeout_ms or executor.default_timeout_ms

        try:
            with self._lock:
                executor.current_load += 1

            func = executor.tools[tool_name]
            result = func(**parameters)

            duration_ms = (time.time() - start_time) * 1000

            # Update statistics
            with self._lock:
                executor.total_executions += 1
                executor.successful_executions += 1
                executor.current_load -= 1

                # Update average execution time
                n = executor.successful_executions
                executor.avg_execution_time_ms = (
                    (executor.avg_execution_time_ms * (n - 1) + duration_ms) / n
                )

            return {
                'success': True,
                'tool_name': tool_name,
                'domain': domain,
                'result': result,
                'duration_ms': duration_ms
            }

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            with self._lock:
                executor.total_executions += 1
                executor.failed_executions += 1
                executor.current_load -= 1

            logger.error(f"Tool '{tool_name}' failed: {e}")

            return {
                'success': False,
                'tool_name': tool_name,
                'domain': domain,
                'error': str(e),
                'duration_ms': duration_ms
            }

    def execute_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        stop_on_failure: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tools in parallel.

        Args:
            tool_calls: List of {'tool_name': str, 'parameters': dict}
            stop_on_failure: Stop all execution on first failure

        Returns:
            List of execution results
        """
        self.total_parallel_executions += 1

        futures = {}
        results = {}

        for i, call in enumerate(tool_calls):
            tool_name = call.get('tool_name')
            parameters = call.get('parameters', {})
            timeout_ms = call.get('timeout_ms')

            future = self.thread_pool.submit(
                self.execute_single,
                tool_name,
                parameters,
                timeout_ms
            )
            futures[future] = i

        # Collect results
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                results[idx] = result

                if stop_on_failure and not result.get('success'):
                    # Cancel remaining futures
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    break

            except Exception as e:
                results[idx] = {
                    'success': False,
                    'tool_name': tool_calls[idx].get('tool_name'),
                    'error': str(e)
                }

        # Return results in original order
        return [results.get(i, {'success': False, 'error': 'Not executed'})
                for i in range(len(tool_calls))]

    def execute_pipeline(
        self,
        steps: List[Dict[str, Any]],
        pipeline_id: str = None
    ) -> PipelineResult:
        """
        Execute a pipeline with dependency tracking.

        Args:
            steps: List of step definitions:
                   {'id': str, 'tool': str, 'params': dict, 'depends_on': list}
            pipeline_id: Optional pipeline identifier

        Returns:
            PipelineResult with execution details
        """
        pipeline_id = pipeline_id or f"pipeline_{int(time.time())}"
        start_time = datetime.now()

        self.total_pipelines += 1

        # Convert step definitions to PipelineStep objects
        pipeline_steps: Dict[str, PipelineStep] = {}
        for step_def in steps:
            step_id = step_def.get('id', f"step_{len(pipeline_steps)}")
            tool_name = step_def.get('tool') or step_def.get('tool_name')
            domain = self.get_domain_for_tool(tool_name) or 'unknown'

            step = PipelineStep(
                step_id=step_id,
                tool_name=tool_name,
                domain=domain,
                parameters=step_def.get('params', step_def.get('parameters', {})),
                depends_on=step_def.get('depends_on', []),
                timeout_ms=step_def.get('timeout_ms', 30000.0),
                retries=step_def.get('retries', 1),
                critical=step_def.get('critical', True)
            )
            pipeline_steps[step_id] = step

        self.active_pipelines[pipeline_id] = list(pipeline_steps.values())

        # Execute pipeline with dependency resolution
        completed: Set[str] = set()
        failed: Set[str] = set()

        while len(completed) + len(failed) < len(pipeline_steps):
            # Find steps ready to execute
            ready_steps = []
            for step_id, step in pipeline_steps.items():
                if step_id in completed or step_id in failed:
                    continue

                # Check dependencies
                deps_met = all(dep in completed for dep in step.depends_on)
                deps_failed = any(dep in failed for dep in step.depends_on)

                if deps_failed:
                    # Skip this step - dependency failed
                    step.status = ExecutionStatus.SKIPPED
                    step.error = "Dependency failed"
                    failed.add(step_id)
                elif deps_met:
                    ready_steps.append(step)

            if not ready_steps:
                # No more steps can be executed
                break

            # Execute ready steps in parallel
            tool_calls = [
                {
                    'tool_name': step.tool_name,
                    'parameters': step.parameters,
                    'timeout_ms': step.timeout_ms
                }
                for step in ready_steps
            ]

            results = self.execute_parallel(tool_calls, stop_on_failure=False)

            # Process results
            for step, result in zip(ready_steps, results):
                step.completed_at = datetime.now()
                step.duration_ms = result.get('duration_ms', 0)
                step.result = result.get('result')
                step.error = result.get('error')

                if result.get('success'):
                    step.status = ExecutionStatus.SUCCESS
                    completed.add(step.step_id)
                else:
                    step.status = ExecutionStatus.FAILED
                    failed.add(step.step_id)

                    if step.critical:
                        # Stop pipeline on critical failure
                        logger.warning(f"Pipeline {pipeline_id} stopped: critical step '{step.step_id}' failed")
                        break

        # Calculate final statistics
        skipped = sum(1 for s in pipeline_steps.values()
                      if s.status == ExecutionStatus.SKIPPED)

        pipeline_result = PipelineResult(
            pipeline_id=pipeline_id,
            total_steps=len(pipeline_steps),
            completed_steps=len(completed),
            failed_steps=len(failed) - skipped,
            skipped_steps=skipped,
            success=len(failed) == 0,
            overall_status='success' if len(failed) == 0 else 'failed',
            step_results={s.step_id: s.to_dict() for s in pipeline_steps.values()},
            total_duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
            started_at=start_time,
            completed_at=datetime.now()
        )

        # Update statistics
        if pipeline_result.success:
            self.successful_pipelines += 1
        else:
            self.failed_pipelines += 1

        # Record history
        self.pipeline_history.append(pipeline_result)

        # Cleanup
        del self.active_pipelines[pipeline_id]

        logger.info(
            f"Pipeline {pipeline_id} completed: "
            f"{pipeline_result.completed_steps}/{pipeline_result.total_steps} steps, "
            f"status={pipeline_result.overall_status}"
        )

        return pipeline_result

    def collect_consensus(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Collect consensus from multiple domains on execution.

        Args:
            tool_name: Tool to execute
            parameters: Tool parameters

        Returns:
            Consensus result with votes and decision
        """
        votes: List[ConsensusVote] = []

        target_domain = self.get_domain_for_tool(tool_name)

        for domain_name, executor in self.domains.items():
            # Each domain votes based on its availability and relevance
            is_primary = domain_name == target_domain
            can_execute = executor.can_accept_work() if is_primary else False

            if is_primary:
                confidence = executor.success_rate()
                should_execute = can_execute and confidence > 0.3
                reason = f"Primary domain, success_rate={confidence:.2f}"
            else:
                confidence = 0.5
                should_execute = False
                reason = "Not primary domain"

            vote = ConsensusVote(
                executor_domain=domain_name,
                should_execute=should_execute,
                confidence=confidence,
                reason=reason
            )
            votes.append(vote)

        # Calculate consensus
        yes_votes = sum(1 for v in votes if v.should_execute)
        total_votes = len(votes)
        agreement = yes_votes / total_votes if total_votes > 0 else 0

        # Weighted confidence
        weighted_confidence = sum(
            v.confidence for v in votes if v.should_execute
        ) / yes_votes if yes_votes > 0 else 0

        should_execute = agreement >= self.consensus_threshold

        return {
            'should_execute': should_execute,
            'agreement': agreement,
            'weighted_confidence': weighted_confidence,
            'votes': [
                {
                    'domain': v.executor_domain,
                    'vote': v.should_execute,
                    'confidence': v.confidence,
                    'reason': v.reason
                }
                for v in votes
            ],
            'threshold': self.consensus_threshold
        }

    def get_load_status(self) -> Dict[str, Any]:
        """Get current load status across all executors"""
        domain_status = {}

        for domain_name, executor in self.domains.items():
            domain_status[domain_name] = {
                'current_load': executor.current_load,
                'max_concurrent': executor.max_concurrent,
                'utilization': executor.current_load / executor.max_concurrent,
                'available': executor.can_accept_work()
            }

        total_load = sum(e.current_load for e in self.domains.values())
        total_capacity = sum(e.max_concurrent for e in self.domains.values())

        return {
            'total_load': total_load,
            'total_capacity': total_capacity,
            'overall_utilization': total_load / total_capacity if total_capacity > 0 else 0,
            'domains': domain_status
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get executor statistics"""
        domain_stats = {
            name: executor.to_dict()
            for name, executor in self.domains.items()
        }

        return {
            'total_pipelines': self.total_pipelines,
            'successful_pipelines': self.successful_pipelines,
            'failed_pipelines': self.failed_pipelines,
            'pipeline_success_rate': (
                self.successful_pipelines / self.total_pipelines
                if self.total_pipelines > 0 else 0
            ),
            'total_parallel_executions': self.total_parallel_executions,
            'active_pipelines': len(self.active_pipelines),
            'domains': domain_stats,
            'load_status': self.get_load_status(),
            'registered_tools': list(self.tool_to_domain.keys())
        }

    def shutdown(self) -> None:
        """Shutdown the executor and cleanup resources"""
        logger.info("Shutting down MultiAgentExecutor...")
        self.thread_pool.shutdown(wait=True)
        logger.info("MultiAgentExecutor shutdown complete")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  MULTI-AGENT EXECUTOR TEST")
    print("=" * 60)

    # Create multi-agent executor
    executor = MultiAgentExecutor(max_workers=5)

    # Define some mock tools
    def mock_build(**kwargs):
        time.sleep(0.1)  # Simulate work
        return {'built': True, 'image': kwargs.get('image', 'test')}

    def mock_push(**kwargs):
        time.sleep(0.1)
        return {'pushed': True, 'registry': kwargs.get('registry', 'local')}

    def mock_deploy(**kwargs):
        time.sleep(0.1)
        return {'deployed': True, 'replicas': kwargs.get('replicas', 1)}

    def mock_verify(**kwargs):
        time.sleep(0.05)
        return {'healthy': True}

    # Register tools in domains
    executor.register_domain('docker', {
        'build': mock_build,
        'push': mock_push,
        'deploy': mock_deploy
    }, max_concurrent=3)

    executor.register_domain('monitoring', {
        'verify': mock_verify
    }, max_concurrent=5)

    print(f"\nRegistered domains: {list(executor.domains.keys())}")
    print(f"Registered tools: {list(executor.tool_to_domain.keys())}")

    # Test 1: Single execution
    print("\n--- Test 1: Single Execution ---")
    result = executor.execute_single('build', {'image': 'myapp:latest'})
    print(f"Build result: {result}")

    # Test 2: Parallel execution
    print("\n--- Test 2: Parallel Execution ---")
    parallel_calls = [
        {'tool_name': 'build', 'parameters': {'image': 'app1'}},
        {'tool_name': 'build', 'parameters': {'image': 'app2'}},
        {'tool_name': 'verify', 'parameters': {}}
    ]
    results = executor.execute_parallel(parallel_calls)
    for i, res in enumerate(results):
        print(f"  Call {i+1}: success={res.get('success')}, duration={res.get('duration_ms', 0):.1f}ms")

    # Test 3: Pipeline with dependencies
    print("\n--- Test 3: Pipeline Execution ---")
    pipeline = [
        {'id': 'build', 'tool': 'build', 'params': {'image': 'myapp:v1'}},
        {'id': 'push', 'tool': 'push', 'params': {'registry': 'docker.io'}, 'depends_on': ['build']},
        {'id': 'deploy', 'tool': 'deploy', 'params': {'replicas': 3}, 'depends_on': ['push']},
        {'id': 'verify', 'tool': 'verify', 'depends_on': ['deploy']}
    ]

    pipeline_result = executor.execute_pipeline(pipeline, pipeline_id="test_pipeline")
    print(f"Pipeline result:")
    print(f"  Success: {pipeline_result.success}")
    print(f"  Completed: {pipeline_result.completed_steps}/{pipeline_result.total_steps}")
    print(f"  Duration: {pipeline_result.total_duration_ms:.1f}ms")

    # Test 4: Consensus
    print("\n--- Test 4: Consensus Collection ---")
    consensus = executor.collect_consensus('build', {'image': 'test'})
    print(f"Should execute: {consensus['should_execute']}")
    print(f"Agreement: {consensus['agreement']:.2f}")

    # Statistics
    print("\n--- Statistics ---")
    stats = executor.get_statistics()
    print(f"Total pipelines: {stats['total_pipelines']}")
    print(f"Pipeline success rate: {stats['pipeline_success_rate']:.1%}")
    print(f"Parallel executions: {stats['total_parallel_executions']}")

    # Cleanup
    executor.shutdown()

    print("\n" + "=" * 60)
    print("  TEST COMPLETE")
    print("=" * 60)
