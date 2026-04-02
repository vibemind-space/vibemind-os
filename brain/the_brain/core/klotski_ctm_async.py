"""
Klotski CTM Async Reasoner - Background Deep Reasoning with Neurosymbolic Brain

Wraps KlotskiCTM to run asynchronously in the background while
the main prediction system continues. This provides System 2 (slow, deliberate)
reasoning powered by the Klotski neurosymbolic brain.

Usage:
    reasoner = KlotskiCTMAsyncReasoner()
    task_id = reasoner.start_reasoning_async(
        task="Deploy complex system",
        brain_state={...}
    )

    # Do other work (System 1 fast prediction)...

    if reasoner.is_complete(task_id):
        result = reasoner.get_result(task_id)
        print(f"Strategy: {result.suggested_strategy}")
"""

import threading
import uuid
import time
from typing import Dict, Optional, List
from dataclasses import dataclass

from core.shared_enums import ReasoningStatus

try:
    from core.klotski_ctm import KlotskiCTM, CTMInsight, KLOTSKI_AVAILABLE
except ImportError:
    from klotski_ctm import KlotskiCTM, CTMInsight, KLOTSKI_AVAILABLE


@dataclass
class KlotskiAsyncResult:
    """
    Result from async Klotski CTM reasoning

    Wraps CTMInsight with async metadata
    """
    task_id: str
    task_description: str
    status: ReasoningStatus

    # CTM Insight (if completed)
    ctm_insight: Optional[CTMInsight] = None

    # Metadata
    elapsed_time: float = 0.0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'task_id': self.task_id,
            'task_description': self.task_description,
            'status': self.status.value,
            'elapsed_time': float(self.elapsed_time)
        }

        if self.ctm_insight:
            result.update({
                'reasoning_steps': self.ctm_insight.reasoning_steps,
                'final_consciousness': float(self.ctm_insight.final_consciousness),
                'converged': self.ctm_insight.converged,
                'confidence': float(self.ctm_insight.confidence),
                'suggested_strategy': self.ctm_insight.suggested_strategy,
                'module_activations': {
                    k: float(v) for k, v in self.ctm_insight.module_activations.items()
                },
                'consciousness_trajectory': [float(x) for x in self.ctm_insight.consciousness_trajectory],
                'dmn_energy': float(self.ctm_insight.dmn_energy),
                'error_magnitude': float(self.ctm_insight.error_magnitude)
            })

            # Sample reasoning trace
            if self.ctm_insight.reasoning_trace:
                trace = self.ctm_insight.reasoning_trace
                result['reasoning_trace_sample'] = trace[::max(1, len(trace)//10)]  # Sample 10 steps
                result['total_reasoning_steps'] = len(trace)

        if self.error_message:
            result['error_message'] = self.error_message

        return result

    def get_insights_summary(self) -> str:
        """
        Get human-readable summary of Klotski CTM insights

        Returns:
            Formatted summary string
        """
        if not self.ctm_insight:
            return "No insights available"

        insight = self.ctm_insight
        lines = []
        lines.append(f"Klotski CTM Deep Reasoning")
        lines.append(f"Steps: {insight.reasoning_steps}, Time: {self.elapsed_time:.1f}s")
        lines.append(f"Consciousness: {insight.final_consciousness:.3f} (converged: {insight.converged})")
        lines.append(f"Confidence: {insight.confidence:.0%}")
        lines.append(f"\nStrategy: {insight.suggested_strategy}")

        lines.append(f"\nTop Brain Modules:")
        sorted_modules = sorted(
            insight.module_activations.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        for mod, act in sorted_modules:
            lines.append(f"  {mod}: {act:.3f}")

        lines.append(f"\nConsciousness Trajectory:")
        traj = insight.consciousness_trajectory
        if len(traj) > 10:
            # Show first, middle, last
            sample = [traj[0], traj[len(traj)//2], traj[-1]]
            lines.append(f"  Start: {sample[0]:.3f} -> Mid: {sample[1]:.3f} -> End: {sample[2]:.3f}")
        else:
            lines.append(f"  {[f'{x:.3f}' for x in traj]}")

        return "\n".join(lines)


class KlotskiCTMAsyncReasoner:
    """
    Async wrapper for KlotskiCTM

    Manages background reasoning threads with the Klotski neurosymbolic brain.
    Provides non-blocking interface for System 1 → System 2 reasoning integration.

    Architecture:
    - System 1 (Tahlamus fast heuristic) completes in <100ms
    - System 2 (Klotski CTM) runs 5-15s in background
    - Results retrieved when needed for retry or explanation
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 3,
        feature_dim: int = 256,
        consciousness_threshold: float = 0.85,
        max_reasoning_steps: int = 50,
        timeout_seconds: float = 30.0,
        device: str = 'cpu'
    ):
        """
        Initialize Klotski CTM async reasoner

        Args:
            max_concurrent_tasks: Max number of reasoning tasks in parallel
            feature_dim: Klotski brain feature dimension
            consciousness_threshold: Convergence threshold for consciousness
            max_reasoning_steps: Max CTM reasoning steps
            timeout_seconds: Timeout for reasoning tasks
            device: torch device ('cpu' or 'cuda')
        """
        if not KLOTSKI_AVAILABLE:
            raise RuntimeError("Klotski CTM not available. Install neurosymbolic brain.")

        self.max_concurrent_tasks = max_concurrent_tasks
        self.max_reasoning_steps = max_reasoning_steps
        self.timeout_seconds = timeout_seconds

        # Create Klotski CTM instance
        self.klotski_ctm = KlotskiCTM(
            feature_dim=feature_dim,
            consciousness_threshold=consciousness_threshold,
            max_reasoning_steps=max_reasoning_steps,
            device=device
        )

        # Task tracking
        self.tasks: Dict[str, KlotskiAsyncResult] = {}
        self.task_lock = threading.Lock()
        self.active_threads: Dict[str, threading.Thread] = {}

        print(f"[KlotskiCTMAsync] Initialized")
        print(f"[KlotskiCTMAsync] Max concurrent: {max_concurrent_tasks}")
        print(f"[KlotskiCTMAsync] Max steps: {max_reasoning_steps}")
        print(f"[KlotskiCTMAsync] Timeout: {timeout_seconds}s")

    def load_weights(self, checkpoint_path: str) -> bool:
        """
        Load trained weights from checkpoint file.

        Args:
            checkpoint_path: Path to .pth file with trained weights

        Returns:
            True if weights loaded successfully, False otherwise
        """
        return self.klotski_ctm.load_weights(checkpoint_path)

    def start_reasoning_async(
        self,
        task: str,
        brain_state: Dict,
        max_steps: Optional[int] = None,
        priority: str = 'normal'
    ) -> str:
        """
        Start background CTM reasoning

        Args:
            task: Task description
            brain_state: Current Tahlamus brain state
            max_steps: Override max reasoning steps
            priority: Priority level ('low', 'normal', 'high')

        Returns:
            Task ID for later retrieval
        """
        task_id = str(uuid.uuid4())[:8]

        # Check if we're at capacity
        with self.task_lock:
            active_count = sum(
                1 for t in self.tasks.values()
                if t.status in [ReasoningStatus.PENDING, ReasoningStatus.RUNNING]
            )

            if active_count >= self.max_concurrent_tasks:
                print(f"[KlotskiCTMAsync] Task {task_id} QUEUED (at capacity {active_count}/{self.max_concurrent_tasks})")
                # For now, skip queuing and just return immediately
                # In production, implement proper queue
                result = KlotskiAsyncResult(
                    task_id=task_id,
                    task_description=task,
                    status=ReasoningStatus.FAILED,
                    error_message="CTM at capacity"
                )
                self.tasks[task_id] = result
                return task_id

            # Create result placeholder
            result = KlotskiAsyncResult(
                task_id=task_id,
                task_description=task,
                status=ReasoningStatus.PENDING
            )
            self.tasks[task_id] = result

        # Start reasoning thread
        thread = threading.Thread(
            target=self._reasoning_worker,
            args=(task_id, task, brain_state, max_steps),
            daemon=True
        )
        thread.start()

        with self.task_lock:
            self.active_threads[task_id] = thread

        print(f"[KlotskiCTMAsync] Task {task_id} STARTED: {task[:50]}...")
        return task_id

    def _reasoning_worker(
        self,
        task_id: str,
        task: str,
        brain_state: Dict,
        max_steps: Optional[int]
    ):
        """
        Worker thread for CTM reasoning

        Args:
            task_id: Task identifier
            task: Task description
            brain_state: Brain state dict
            max_steps: Max reasoning steps
        """
        start_time = time.time()

        # Update status
        with self.task_lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = ReasoningStatus.RUNNING

        try:
            # Run Klotski CTM reasoning
            insight = self.klotski_ctm.reason(
                task=task,
                brain_state=brain_state,
                max_steps=max_steps,
                return_trajectory=True
            )

            elapsed = time.time() - start_time

            # Update result
            with self.task_lock:
                if task_id in self.tasks:
                    self.tasks[task_id].status = ReasoningStatus.COMPLETED
                    self.tasks[task_id].ctm_insight = insight
                    self.tasks[task_id].elapsed_time = elapsed

            print(f"[KlotskiCTMAsync] Task {task_id} COMPLETED in {elapsed:.1f}s")
            print(f"[KlotskiCTMAsync]   Consciousness: {insight.final_consciousness:.3f}, Converged: {insight.converged}")
            print(f"[KlotskiCTMAsync]   Strategy: {insight.suggested_strategy}")

        except Exception as e:
            elapsed = time.time() - start_time

            with self.task_lock:
                if task_id in self.tasks:
                    self.tasks[task_id].status = ReasoningStatus.FAILED
                    self.tasks[task_id].error_message = str(e)
                    self.tasks[task_id].elapsed_time = elapsed

            print(f"[KlotskiCTMAsync] Task {task_id} FAILED: {e}")

        finally:
            # Clean up thread reference
            with self.task_lock:
                if task_id in self.active_threads:
                    del self.active_threads[task_id]

    def is_complete(self, task_id: str) -> bool:
        """Check if reasoning is complete"""
        with self.task_lock:
            if task_id not in self.tasks:
                return False
            return self.tasks[task_id].status in [
                ReasoningStatus.COMPLETED,
                ReasoningStatus.FAILED,
                ReasoningStatus.INTERRUPTED
            ]

    def get_result(self, task_id: str, wait: bool = False, timeout: float = None) -> Optional[KlotskiAsyncResult]:
        """
        Get reasoning result

        Args:
            task_id: Task identifier
            wait: If True, block until complete
            timeout: Max time to wait (seconds)

        Returns:
            Result or None if not found
        """
        if wait:
            timeout = timeout or self.timeout_seconds
            start_time = time.time()

            while not self.is_complete(task_id):
                if time.time() - start_time > timeout:
                    print(f"[KlotskiCTMAsync] Task {task_id} TIMEOUT after {timeout}s")
                    with self.task_lock:
                        if task_id in self.tasks:
                            self.tasks[task_id].status = ReasoningStatus.INTERRUPTED
                            self.tasks[task_id].error_message = "Timeout"
                    break
                time.sleep(0.1)

        with self.task_lock:
            return self.tasks.get(task_id)

    def get_status(self, task_id: str) -> Optional[ReasoningStatus]:
        """Get task status"""
        with self.task_lock:
            if task_id in self.tasks:
                return self.tasks[task_id].status
            return None

    def cancel(self, task_id: str):
        """
        Cancel reasoning task

        Note: Cancellation is cooperative - thread will finish current step
        """
        with self.task_lock:
            if task_id in self.tasks:
                if self.tasks[task_id].status in [ReasoningStatus.PENDING, ReasoningStatus.RUNNING]:
                    self.tasks[task_id].status = ReasoningStatus.INTERRUPTED
                    print(f"[KlotskiCTMAsync] Task {task_id} CANCELLED")

    def get_active_tasks(self) -> List[str]:
        """Get list of active task IDs"""
        with self.task_lock:
            return [
                task_id for task_id, result in self.tasks.items()
                if result.status in [ReasoningStatus.PENDING, ReasoningStatus.RUNNING]
            ]

    def get_stats(self) -> Dict:
        """Get reasoner statistics"""
        with self.task_lock:
            total = len(self.tasks)
            completed = sum(1 for t in self.tasks.values() if t.status == ReasoningStatus.COMPLETED)
            failed = sum(1 for t in self.tasks.values() if t.status == ReasoningStatus.FAILED)
            active = sum(1 for t in self.tasks.values() if t.status in [ReasoningStatus.PENDING, ReasoningStatus.RUNNING])

            # Compute average consciousness for completed tasks
            completed_tasks = [t for t in self.tasks.values() if t.status == ReasoningStatus.COMPLETED and t.ctm_insight]
            avg_consciousness = 0.0
            avg_steps = 0.0
            if completed_tasks:
                avg_consciousness = sum(t.ctm_insight.final_consciousness for t in completed_tasks) / len(completed_tasks)
                avg_steps = sum(t.ctm_insight.reasoning_steps for t in completed_tasks) / len(completed_tasks)

        return {
            'total_tasks': total,
            'completed': completed,
            'failed': failed,
            'active': active,
            'max_concurrent': self.max_concurrent_tasks,
            'avg_consciousness': float(avg_consciousness),
            'avg_steps': float(avg_steps)
        }


if __name__ == "__main__":
    # Test async reasoner
    print("="*70)
    print("Testing Klotski CTM Async Reasoner")
    print("="*70)

    reasoner = KlotskiCTMAsyncReasoner(
        max_concurrent_tasks=2,
        consciousness_threshold=0.85,
        max_reasoning_steps=20
    )

    # Start multiple reasoning tasks
    tasks = [
        "Deploy distributed microservice architecture with auto-scaling",
        "Design real-time data pipeline with fault tolerance",
        "Implement security audit system with compliance monitoring"
    ]

    brain_state = {
        'modality_activations': {
            'tool_trace': 0.8,
            'temporal_pattern': 0.6,
            'error_signal': 0.3
        }
    }

    task_ids = []
    for task in tasks:
        task_id = reasoner.start_reasoning_async(task, brain_state, max_steps=15)
        task_ids.append(task_id)
        time.sleep(0.5)  # Stagger starts

    print("\n" + "="*70)
    print("Waiting for results...")
    print("="*70)

    # Wait and retrieve results
    for task_id in task_ids:
        result = reasoner.get_result(task_id, wait=True, timeout=20)

        if result and result.status == ReasoningStatus.COMPLETED:
            print(f"\n[Task {task_id}]")
            print(result.get_insights_summary())
        elif result:
            print(f"\n[Task {task_id}] Status: {result.status.value}")
            if result.error_message:
                print(f"Error: {result.error_message}")

    # Print stats
    print("\n" + "="*70)
    print("Reasoner Statistics")
    print("="*70)
    stats = reasoner.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "="*70)
    print("Test Complete!")
    print("="*70)
