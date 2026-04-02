"""
CTM Async Reasoner - Background Deep Reasoning

Wraps CTMReasoner to run asynchronously in the background while
the main prediction system continues. Results can be retrieved
when needed for retry strategies or detailed explanations.

Usage:
    reasoner = CTMAsyncReasoner()
    task_id = reasoner.start_reasoning_async(task_description)

    # Do other work...

    if reasoner.is_complete(task_id):
        result = reasoner.get_result(task_id)
"""

import threading
import uuid
import time
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
import numpy as np

from core.shared_enums import ReasoningStatus

try:
    from core.ctm_integration import CTMReasoner, ThoughtState
except ImportError:
    # Fallback to root if core version doesn't exist
    from ctm_integration import CTMReasoner, ThoughtState


@dataclass
class CTMAsyncResult:
    """
    Result from async CTM reasoning
    """
    task_id: str
    task_description: str
    status: ReasoningStatus

    # Results (if completed)
    final_state: Optional[ThoughtState] = None
    reasoning_trace: Optional[List[str]] = None

    # Metadata
    steps_taken: int = 0
    converged: bool = False
    confidence: float = 0.0
    elapsed_time: float = 0.0

    # Error info (if failed)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'task_id': self.task_id,
            'task_description': self.task_description,
            'status': self.status.value,
            'steps_taken': self.steps_taken,
            'converged': self.converged,
            'confidence': float(self.confidence),
            'elapsed_time': float(self.elapsed_time)
        }

        if self.reasoning_trace:
            result['reasoning_trace'] = self.reasoning_trace[:10]  # Limit to first 10 thoughts
            result['total_thoughts'] = len(self.reasoning_trace)

        if self.error_message:
            result['error_message'] = self.error_message

        return result

    def get_insights_summary(self) -> str:
        """
        Get human-readable summary of CTM insights

        Returns:
            Formatted summary string
        """
        if not self.reasoning_trace:
            return "No insights available"

        lines = []
        lines.append(f"CTM Deep Reasoning ({self.steps_taken} steps, {self.elapsed_time:.1f}s)")
        lines.append(f"Confidence: {self.confidence:.0%}, Converged: {self.converged}")
        lines.append("\nKey Thoughts:")

        # Sample thoughts from beginning, middle, end
        n = len(self.reasoning_trace)
        if n <= 5:
            samples = self.reasoning_trace
        else:
            samples = [
                self.reasoning_trace[0],
                self.reasoning_trace[n//4],
                self.reasoning_trace[n//2],
                self.reasoning_trace[3*n//4],
                self.reasoning_trace[-1]
            ]

        for i, thought in enumerate(samples, 1):
            lines.append(f"  {i}. {thought}")

        return "\n".join(lines)


class CTMAsyncReasoner:
    """
    Async wrapper for CTMReasoner

    Manages background reasoning threads and provides non-blocking
    interface for starting and retrieving CTM reasoning results.
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 3,
        default_steps: int = 50,
        default_convergence: float = 0.9,
        timeout_seconds: float = 30.0
    ):
        """
        Initialize async CTM reasoner

        Args:
            max_concurrent_tasks: Max number of reasoning tasks in parallel
            default_steps: Default max reasoning steps
            default_convergence: Default convergence threshold
            timeout_seconds: Timeout for reasoning tasks
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.default_steps = default_steps
        self.default_convergence = default_convergence
        self.timeout_seconds = timeout_seconds

        # Create CTM reasoner instance (shared across threads)
        self.ctm_reasoner = CTMReasoner(adaptive=True, thought_dim=128)

        # Task tracking
        self.tasks: Dict[str, CTMAsyncResult] = {}
        self.active_threads: Dict[str, threading.Thread] = {}
        self.lock = threading.Lock()

        # Statistics
        self.total_tasks_started = 0
        self.total_tasks_completed = 0
        self.total_reasoning_time = 0.0

    def start_reasoning_async(
        self,
        task_description: str,
        initial_visual: Optional[np.ndarray] = None,
        initial_verbal: Optional[np.ndarray] = None,
        goal: Optional[np.ndarray] = None,
        steps: Optional[int] = None,
        convergence_threshold: Optional[float] = None,
        priority: str = "normal"
    ) -> str:
        """
        Start CTM reasoning in background thread

        Args:
            task_description: Task to reason about
            initial_visual: Initial visual input
            initial_verbal: Initial verbal input
            goal: Goal state
            steps: Max reasoning steps
            convergence_threshold: Convergence threshold
            priority: Priority level ('low', 'normal', 'high')

        Returns:
            task_id: Unique task identifier for retrieving results
        """
        with self.lock:
            # Check concurrent limit
            active_count = sum(1 for t in self.active_threads.values() if t.is_alive())
            if active_count >= self.max_concurrent_tasks:
                raise RuntimeError(
                    f"Too many concurrent reasoning tasks ({active_count}/{self.max_concurrent_tasks}). "
                    f"Wait for some to complete or increase max_concurrent_tasks."
                )

            # Generate task ID
            task_id = str(uuid.uuid4())[:8]

            # Create result placeholder
            result = CTMAsyncResult(
                task_id=task_id,
                task_description=task_description,
                status=ReasoningStatus.PENDING
            )
            self.tasks[task_id] = result

            # Use defaults if not specified
            steps = steps or self.default_steps
            convergence_threshold = convergence_threshold or self.default_convergence

            # Start background thread
            thread = threading.Thread(
                target=self._reasoning_worker,
                args=(
                    task_id,
                    task_description,
                    initial_visual,
                    initial_verbal,
                    goal,
                    steps,
                    convergence_threshold
                ),
                daemon=True,
                name=f"CTM-{task_id}"
            )
            thread.start()
            self.active_threads[task_id] = thread

            self.total_tasks_started += 1

            return task_id

    def _reasoning_worker(
        self,
        task_id: str,
        task_description: str,
        initial_visual: Optional[np.ndarray],
        initial_verbal: Optional[np.ndarray],
        goal: Optional[np.ndarray],
        steps: int,
        convergence_threshold: float
    ):
        """
        Worker function that runs CTM reasoning
        (Runs in background thread)
        """
        start_time = time.time()

        try:
            # Update status to running
            with self.lock:
                self.tasks[task_id].status = ReasoningStatus.RUNNING

            # Run CTM reasoning
            final_state, reasoning_trace = self.ctm_reasoner.reason(
                problem=task_description,
                initial_visual=initial_visual,
                initial_verbal=initial_verbal,
                goal=goal,
                steps=steps,
                convergence_threshold=convergence_threshold,
                log_dir=None  # No logging for async tasks
            )

            # Update result
            elapsed_time = time.time() - start_time

            with self.lock:
                result = self.tasks[task_id]
                result.status = ReasoningStatus.COMPLETED
                result.final_state = final_state
                result.reasoning_trace = reasoning_trace
                result.steps_taken = final_state.step + 1
                result.converged = final_state.converged
                result.confidence = final_state.confidence
                result.elapsed_time = elapsed_time

                self.total_tasks_completed += 1
                self.total_reasoning_time += elapsed_time

        except Exception as e:
            # Handle errors
            elapsed_time = time.time() - start_time

            with self.lock:
                result = self.tasks[task_id]
                result.status = ReasoningStatus.FAILED
                result.error_message = str(e)
                result.elapsed_time = elapsed_time

    def is_complete(self, task_id: str) -> bool:
        """
        Check if reasoning task is complete

        Args:
            task_id: Task identifier

        Returns:
            True if completed (success or failure), False if still running
        """
        with self.lock:
            if task_id not in self.tasks:
                raise ValueError(f"Unknown task_id: {task_id}")

            status = self.tasks[task_id].status
            return status in [ReasoningStatus.COMPLETED, ReasoningStatus.FAILED, ReasoningStatus.INTERRUPTED]

    def get_result(self, task_id: str, wait: bool = False, timeout: Optional[float] = None) -> CTMAsyncResult:
        """
        Get result of reasoning task

        Args:
            task_id: Task identifier
            wait: If True, block until task completes
            timeout: Max wait time in seconds (if wait=True)

        Returns:
            CTMAsyncResult with reasoning results
        """
        if wait:
            start_time = time.time()
            timeout = timeout or self.timeout_seconds

            while not self.is_complete(task_id):
                if time.time() - start_time > timeout:
                    # Timeout - interrupt the task
                    with self.lock:
                        if task_id in self.tasks:
                            self.tasks[task_id].status = ReasoningStatus.INTERRUPTED
                            self.tasks[task_id].error_message = "Timeout"
                    break

                time.sleep(0.1)  # Poll every 100ms

        with self.lock:
            if task_id not in self.tasks:
                raise ValueError(f"Unknown task_id: {task_id}")

            return self.tasks[task_id]

    def get_partial_result(self, task_id: str) -> Optional[CTMAsyncResult]:
        """
        Get partial result even if task is still running

        Args:
            task_id: Task identifier

        Returns:
            Current CTMAsyncResult (may be incomplete)
        """
        with self.lock:
            if task_id not in self.tasks:
                return None
            return self.tasks[task_id]

    def cancel_task(self, task_id: str):
        """
        Cancel a running reasoning task

        Note: This marks the task as interrupted but doesn't forcefully
        stop the thread (threads can't be killed safely in Python).

        Args:
            task_id: Task identifier
        """
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = ReasoningStatus.INTERRUPTED

    def cleanup_completed_tasks(self, keep_last_n: int = 10):
        """
        Remove old completed tasks to free memory

        Args:
            keep_last_n: Number of recent tasks to keep
        """
        with self.lock:
            completed_ids = [
                task_id for task_id, result in self.tasks.items()
                if self.is_complete(task_id)
            ]

            # Sort by completion time (approximate with task_id)
            completed_ids.sort()

            # Remove oldest
            if len(completed_ids) > keep_last_n:
                to_remove = completed_ids[:-keep_last_n]
                for task_id in to_remove:
                    del self.tasks[task_id]
                    if task_id in self.active_threads:
                        del self.active_threads[task_id]

    def get_statistics(self) -> Dict:
        """Get statistics about async reasoning tasks"""
        with self.lock:
            active_count = sum(1 for t in self.active_threads.values() if t.is_alive())

            avg_reasoning_time = (
                self.total_reasoning_time / self.total_tasks_completed
                if self.total_tasks_completed > 0
                else 0.0
            )

            return {
                'total_tasks_started': self.total_tasks_started,
                'total_tasks_completed': self.total_tasks_completed,
                'active_tasks': active_count,
                'cached_tasks': len(self.tasks),
                'average_reasoning_time': avg_reasoning_time,
                'total_reasoning_time': self.total_reasoning_time
            }

    def __repr__(self):
        stats = self.get_statistics()
        return (
            f"CTMAsyncReasoner("
            f"completed={stats['total_tasks_completed']}, "
            f"active={stats['active_tasks']}, "
            f"avg_time={stats['average_reasoning_time']:.1f}s)"
        )


# Singleton instance for shared use
_global_ctm_async = None

def get_global_ctm_async() -> CTMAsyncReasoner:
    """Get global CTMAsyncReasoner instance (singleton)"""
    global _global_ctm_async
    if _global_ctm_async is None:
        _global_ctm_async = CTMAsyncReasoner()
    return _global_ctm_async


if __name__ == "__main__":
    print("=" * 70)
    print("CTM ASYNC REASONER - DEMO")
    print("=" * 70)

    # Create async reasoner
    reasoner = CTMAsyncReasoner(max_concurrent_tasks=2)

    # Start multiple reasoning tasks
    task1_id = reasoner.start_reasoning_async(
        "Solve a complex spatial reasoning puzzle",
        steps=20
    )
    print(f"\n✓ Started task 1: {task1_id}")

    task2_id = reasoner.start_reasoning_async(
        "Plan a multi-step optimization strategy",
        steps=20
    )
    print(f"✓ Started task 2: {task2_id}")

    # Do other work while reasoning happens in background
    print("\n[Main thread] Doing other work while CTM thinks in background...")
    time.sleep(2)

    # Check status
    print(f"\n[Main thread] Task 1 complete: {reasoner.is_complete(task1_id)}")
    print(f"[Main thread] Task 2 complete: {reasoner.is_complete(task2_id)}")

    # Wait for results
    print("\n[Main thread] Waiting for task 1 to complete...")
    result1 = reasoner.get_result(task1_id, wait=True, timeout=30.0)

    print(f"\n✓ Task 1 completed!")
    print(result1.get_insights_summary())

    print("\n[Main thread] Waiting for task 2...")
    result2 = reasoner.get_result(task2_id, wait=True, timeout=30.0)

    print(f"\n✓ Task 2 completed!")
    print(result2.get_insights_summary())

    # Statistics
    print("\n" + "=" * 70)
    print("STATISTICS")
    print("=" * 70)
    stats = reasoner.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n✓ Demo complete!")
