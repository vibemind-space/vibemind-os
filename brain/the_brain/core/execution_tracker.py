"""
Execution Tracker

Tracks agent executions as a structured list within a session.
Instead of storing each execution individually, accumulates them
into a session log that gets stored as a single memory.

This provides better context:
- "Last time I deployed Docker, I ran these 5 commands"
- "When task X failed, the sequence was A→B→fail"
- "Successful deployments follow this pattern: A→B→C→D"

Usage:
    tracker = ExecutionTracker(session_id="deploy-20250115")

    tracker.add_execution(
        step=1,
        command="docker build -t myapp .",
        result="SUCCESS",
        output="Successfully built image",
        duration_ms=3200
    )

    tracker.add_execution(
        step=2,
        command="docker run -p 8080:8080 myapp",
        result="SUCCESS",
        output="Container started on port 8080",
        duration_ms=1500
    )

    # Store entire session in Supermemory
    tracker.store_session(hippocampus, confidence=0.95)
"""

import os
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Execution:
    """Single execution step in a session."""
    step: int
    command: str
    result: str  # SUCCESS, FAILURE, PARTIAL, SKIPPED
    output: str
    duration_ms: int
    timestamp: str
    metadata: Dict[str, Any] = None

    def __str__(self):
        status_emoji = {
            'SUCCESS': '[OK]',
            'FAILURE': '[FAIL]',
            'PARTIAL': '[WARN]',
            'SKIPPED': '[SKIP]'
        }
        emoji = status_emoji.get(self.result, '[?]')
        return f"{emoji} Step {self.step}: {self.command} ({self.duration_ms}ms)"


class ExecutionTracker:
    """
    Tracks a session of agent executions as a list.

    Maintains execution history until session is complete,
    then stores as a single memory in Supermemory.
    """

    def __init__(
        self,
        session_id: str = None,
        task: str = None,
        agent_name: str = None,
        user_id: str = None
    ):
        """
        Initialize execution tracker.

        Args:
            session_id: Unique session identifier (auto-generated if not provided)
            task: High-level task description
            agent_name: Name of executing agent
            user_id: User identifier for multi-user support
        """
        self.session_id = session_id or f"session-{int(datetime.now().timestamp())}"
        self.task = task or "Unknown task"
        self.agent_name = agent_name or "unknown_agent"
        self.user_id = user_id

        self.executions: List[Execution] = []
        self.session_start = datetime.now().isoformat()
        self.session_end: Optional[str] = None
        self.overall_result: Optional[str] = None
        self.confidence: Optional[float] = None

        print(f"[ExecutionTracker] Started session: {self.session_id}")
        print(f"  Task: {self.task}")
        print(f"  Agent: {self.agent_name}")
        if user_id:
            print(f"  User: {self.user_id}")

    def add_execution(
        self,
        step: int,
        command: str,
        result: str,
        output: str,
        duration_ms: int,
        metadata: Dict[str, Any] = None
    ):
        """
        Add an execution step to the session.

        Args:
            step: Step number (1, 2, 3, ...)
            command: Command or action executed
            result: Execution result (SUCCESS, FAILURE, PARTIAL, SKIPPED)
            output: Command output or error message
            duration_ms: Execution duration in milliseconds
            metadata: Additional metadata
        """
        execution = Execution(
            step=step,
            command=command,
            result=result,
            output=output,
            duration_ms=duration_ms,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {}
        )

        self.executions.append(execution)
        print(f"[ExecutionTracker] {execution}")

    def mark_complete(
        self,
        overall_result: str,
        confidence: float
    ):
        """
        Mark session as complete.

        Args:
            overall_result: Overall session result (SUCCESS, FAILURE, PARTIAL)
            confidence: Agent's confidence in the result (0.0 to 1.0)
        """
        self.session_end = datetime.now().isoformat()
        self.overall_result = overall_result
        self.confidence = confidence

        print(f"[ExecutionTracker] Session complete: {overall_result} ({confidence:.1%} confidence)")

    def get_execution_list(self) -> List[Dict]:
        """
        Get executions as list of dicts.

        Returns:
            List of execution dicts
        """
        return [asdict(e) for e in self.executions]

    def format_as_text(self) -> str:
        """
        Format execution list as human-readable text.

        Returns:
            Formatted execution log
        """
        lines = []
        lines.append(f"SESSION: {self.session_id}")
        lines.append(f"TASK: {self.task}")
        lines.append(f"AGENT: {self.agent_name}")
        lines.append(f"START: {self.session_start}")
        if self.session_end:
            lines.append(f"END: {self.session_end}")
        if self.overall_result:
            lines.append(f"RESULT: {self.overall_result} ({self.confidence:.1%} confidence)")
        lines.append("")
        lines.append("EXECUTION LIST:")
        lines.append("-" * 60)

        for exec in self.executions:
            lines.append(f"\nStep {exec.step}: {exec.command}")
            lines.append(f"  Result: {exec.result}")
            lines.append(f"  Duration: {exec.duration_ms}ms")
            lines.append(f"  Output: {exec.output[:100]}...")
            if exec.metadata:
                lines.append(f"  Metadata: {json.dumps(exec.metadata)}")

        lines.append("-" * 60)
        lines.append(f"Total steps: {len(self.executions)}")

        success_count = sum(1 for e in self.executions if e.result == 'SUCCESS')
        failure_count = sum(1 for e in self.executions if e.result == 'FAILURE')
        lines.append(f"Success: {success_count} | Failures: {failure_count}")

        total_duration = sum(e.duration_ms for e in self.executions)
        lines.append(f"Total duration: {total_duration}ms")

        return '\n'.join(lines)

    def store_session(
        self,
        hippocampus,
        confidence: float = None
    ) -> bool:
        """
        Store complete session in Supermemory hippocampus.

        Args:
            hippocampus: SupermemoryHippocampus instance
            confidence: Override confidence (if not already set)

        Returns:
            True if stored successfully
        """
        if not self.session_end:
            print("[ExecutionTracker] Warning: Session not marked complete")
            self.mark_complete(
                overall_result="INCOMPLETE",
                confidence=confidence or 0.5
            )

        # Use provided confidence or stored confidence
        final_confidence = confidence if confidence is not None else self.confidence

        # Format execution list as text
        session_log = self.format_as_text()

        # Store in hippocampus
        success = hippocampus.store_execution_memory(
            task=self.task,
            result=self.overall_result,
            confidence=final_confidence,
            session_log=session_log,
            agent_name=self.agent_name,
            duration_ms=sum(e.duration_ms for e in self.executions)
        )

        if success:
            print(f"[ExecutionTracker] Session stored in Supermemory")
        else:
            print(f"[ExecutionTracker] Failed to store session")

        return success

    def get_total_duration(self) -> int:
        """
        Get total execution duration in milliseconds.

        Returns:
            Total duration in milliseconds
        """
        return sum(e.duration_ms for e in self.executions)

    def get_statistics(self) -> Dict:
        """
        Get session statistics.

        Returns:
            Dict with stats
        """
        if not self.executions:
            return {
                'total_steps': 0,
                'success_count': 0,
                'failure_count': 0,
                'total_duration_ms': 0
            }

        return {
            'session_id': self.session_id,
            'task': self.task,
            'agent_name': self.agent_name,
            'total_steps': len(self.executions),
            'success_count': sum(1 for e in self.executions if e.result == 'SUCCESS'),
            'failure_count': sum(1 for e in self.executions if e.result == 'FAILURE'),
            'partial_count': sum(1 for e in self.executions if e.result == 'PARTIAL'),
            'total_duration_ms': self.get_total_duration(),
            'overall_result': self.overall_result,
            'confidence': self.confidence,
            'session_start': self.session_start,
            'session_end': self.session_end
        }


# Example usage
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from core.supermemory_hippocampus import SupermemoryHippocampus

    print("=" * 70)
    print("EXECUTION TRACKER TEST")
    print("=" * 70)
    print()

    # Create tracker for a deployment session
    tracker = ExecutionTracker(
        session_id="deploy-docker-20250115",
        task="Deploy Docker container to production",
        agent_name="deployment_agent"
    )

    # Simulate execution steps
    print("\n[SIMULATING EXECUTION SEQUENCE]")
    print()

    tracker.add_execution(
        step=1,
        command="docker build -t myapp:latest .",
        result="SUCCESS",
        output="Successfully built image sha256:abc123...",
        duration_ms=3200,
        metadata={'image_size_mb': 145}
    )

    tracker.add_execution(
        step=2,
        command="docker tag myapp:latest registry.example.com/myapp:latest",
        result="SUCCESS",
        output="Tagged image",
        duration_ms=150
    )

    tracker.add_execution(
        step=3,
        command="docker push registry.example.com/myapp:latest",
        result="SUCCESS",
        output="Pushed to registry",
        duration_ms=8500,
        metadata={'registry': 'registry.example.com'}
    )

    tracker.add_execution(
        step=4,
        command="docker run -d -p 8080:8080 myapp:latest",
        result="SUCCESS",
        output="Container started: container_id=def456...",
        duration_ms=1200,
        metadata={'container_id': 'def456', 'port': 8080}
    )

    tracker.add_execution(
        step=5,
        command="curl http://localhost:8080/health",
        result="SUCCESS",
        output='{"status": "healthy"}',
        duration_ms=250,
        metadata={'health_check': 'passed'}
    )

    # Mark complete
    print()
    tracker.mark_complete(
        overall_result="SUCCESS",
        confidence=0.95
    )

    # Show formatted output
    print("\n" + "=" * 70)
    print("FORMATTED SESSION LOG")
    print("=" * 70)
    print(tracker.format_as_text())

    # Show statistics
    print("\n" + "=" * 70)
    print("SESSION STATISTICS")
    print("=" * 70)
    stats = tracker.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Store in Supermemory (if available)
    print("\n" + "=" * 70)
    print("STORING IN SUPERMEMORY")
    print("=" * 70)

    try:
        hippocampus = SupermemoryHippocampus(enable_fallback=True)
        if hippocampus.supermemory_available:
            tracker.store_session(hippocampus)
            print("\n[OK] Session stored successfully!")
        else:
            print("\n[INFO] Supermemory unavailable - session logged locally")
    except Exception as e:
        print(f"\n[ERROR] Failed to store: {e}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
