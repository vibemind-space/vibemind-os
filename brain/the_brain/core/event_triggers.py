"""
Event Triggers (Phase 4) - Event Detection for Phase Dynamics

Implements the delta (δ) component of the phase dynamics equation:
    ΔφH(r) = -λ(ωqf δ(r) + ∇·(W×E))

Events are detected from tool results and state transitions:
- error_detected: Tool failure or exception
- goal_near: Close to task completion
- loop_detected: Repeated pattern (stuck)
- novelty_high: Unexpected/new state
- timeout: Waiting too long
"""

import numpy as np
import torch
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class EventType(Enum):
    """Types of events that can trigger phase changes"""
    ERROR = "error"
    GOAL_NEAR = "goal_near"
    LOOP = "loop"
    NOVELTY = "novelty"
    TIMEOUT = "timeout"


@dataclass
class EventTriggers:
    """
    δ(r) - Event flags that trigger phase changes

    These events cause the CTM to modify its phase dynamics:
    - When events occur, the oscillator phase changes
    - When no events, phases evolve smoothly via coupling only
    """
    error_detected: bool = False      # Tool failure, exception
    goal_near: bool = False           # Close to task completion
    loop_detected: bool = False       # Repeated pattern (stuck)
    novelty_high: bool = False        # New/unexpected state
    timeout: bool = False             # Waiting too long

    # Event strengths (0.0 to 1.0)
    error_strength: float = 0.0
    goal_strength: float = 0.0
    loop_strength: float = 0.0
    novelty_strength: float = 0.0
    timeout_strength: float = 0.0

    def to_vector(self) -> np.ndarray:
        """
        Convert to 5D binary vector for simple use

        Returns:
            np.ndarray: [error, goal_near, loop, novelty, timeout]
        """
        return np.array([
            float(self.error_detected),
            float(self.goal_near),
            float(self.loop_detected),
            float(self.novelty_high),
            float(self.timeout)
        ], dtype=np.float32)

    def to_strength_vector(self) -> np.ndarray:
        """
        Convert to 5D strength vector (continuous values)

        Returns:
            np.ndarray: [error_str, goal_str, loop_str, novelty_str, timeout_str]
        """
        return np.array([
            self.error_strength,
            self.goal_strength,
            self.loop_strength,
            self.novelty_strength,
            self.timeout_strength
        ], dtype=np.float32)

    def to_tensor(self, device: str = 'cpu') -> torch.Tensor:
        """Convert to PyTorch tensor"""
        return torch.tensor(self.to_strength_vector(), device=device)

    @property
    def any_triggered(self) -> bool:
        """Check if any event is triggered"""
        return any([
            self.error_detected,
            self.goal_near,
            self.loop_detected,
            self.novelty_high,
            self.timeout
        ])

    @property
    def total_strength(self) -> float:
        """Sum of all event strengths"""
        return (self.error_strength + self.goal_strength +
                self.loop_strength + self.novelty_strength +
                self.timeout_strength)

    def __repr__(self) -> str:
        active = []
        if self.error_detected:
            active.append(f"error({self.error_strength:.2f})")
        if self.goal_near:
            active.append(f"goal({self.goal_strength:.2f})")
        if self.loop_detected:
            active.append(f"loop({self.loop_strength:.2f})")
        if self.novelty_high:
            active.append(f"novelty({self.novelty_strength:.2f})")
        if self.timeout:
            active.append(f"timeout({self.timeout_strength:.2f})")
        if not active:
            return "EventTriggers(none)"
        return f"EventTriggers({', '.join(active)})"


class EventDetector:
    """
    Detects events from tool results and state changes

    Analyzes:
    - Tool execution results (success/failure)
    - State transitions (progress toward goal)
    - Pattern repetition (loop detection)
    - State novelty (unexpected changes)
    - Timing (timeout detection)
    """

    def __init__(
        self,
        error_threshold: float = 0.5,
        goal_threshold: float = 0.8,
        loop_window: int = 5,
        novelty_threshold: float = 0.7,
        timeout_ms: float = 30000
    ):
        """
        Initialize event detector

        Args:
            error_threshold: Confidence for error detection
            goal_threshold: Progress level to trigger goal_near
            loop_window: Number of steps to check for loops
            novelty_threshold: Threshold for novelty detection
            timeout_ms: Milliseconds before timeout triggers
        """
        self.error_threshold = error_threshold
        self.goal_threshold = goal_threshold
        self.loop_window = loop_window
        self.novelty_threshold = novelty_threshold
        self.timeout_ms = timeout_ms

        # History tracking
        self.tool_history: List[str] = []
        self.state_history: List[np.ndarray] = []
        self.last_action_time: float = 0.0

    def detect(
        self,
        tool_result: Optional[Dict[str, Any]] = None,
        prev_state: Optional[np.ndarray] = None,
        curr_state: Optional[np.ndarray] = None,
        goal_progress: float = 0.0,
        elapsed_ms: float = 0.0
    ) -> EventTriggers:
        """
        Detect events from current context

        Args:
            tool_result: Result from last tool execution
            prev_state: Previous brain state vector
            curr_state: Current brain state vector
            goal_progress: Progress toward goal (0.0 to 1.0)
            elapsed_ms: Time since last action

        Returns:
            EventTriggers with detected events
        """
        triggers = EventTriggers()

        # 1. Error detection
        if tool_result is not None:
            triggers = self._detect_error(tool_result, triggers)
            self._update_tool_history(tool_result)

        # 2. Goal proximity
        triggers = self._detect_goal_near(goal_progress, triggers)

        # 3. Loop detection
        triggers = self._detect_loop(triggers)

        # 4. Novelty detection
        if prev_state is not None and curr_state is not None:
            triggers = self._detect_novelty(prev_state, curr_state, triggers)
            self._update_state_history(curr_state)

        # 5. Timeout detection
        triggers = self._detect_timeout(elapsed_ms, triggers)

        return triggers

    def _detect_error(
        self,
        tool_result: Dict[str, Any],
        triggers: EventTriggers
    ) -> EventTriggers:
        """Detect error from tool result"""
        success = tool_result.get('success', True)
        error_msg = tool_result.get('error', '')
        error_code = tool_result.get('error_code', 0)

        if not success:
            triggers.error_detected = True
            # Strength based on error severity
            if error_code >= 500 or 'critical' in str(error_msg).lower():
                triggers.error_strength = 1.0
            elif error_code >= 400 or 'failed' in str(error_msg).lower():
                triggers.error_strength = 0.7
            else:
                triggers.error_strength = 0.5

        return triggers

    def _detect_goal_near(
        self,
        goal_progress: float,
        triggers: EventTriggers
    ) -> EventTriggers:
        """Detect proximity to goal"""
        if goal_progress >= self.goal_threshold:
            triggers.goal_near = True
            # Strength increases as we approach completion
            triggers.goal_strength = min(1.0, (goal_progress - self.goal_threshold) /
                                         (1.0 - self.goal_threshold + 0.01) + 0.5)
        elif goal_progress >= self.goal_threshold * 0.8:
            # Partial activation as we approach threshold
            triggers.goal_near = True
            triggers.goal_strength = 0.3

        return triggers

    def _detect_loop(self, triggers: EventTriggers) -> EventTriggers:
        """Detect repeated patterns (stuck in loop)"""
        if len(self.tool_history) < self.loop_window:
            return triggers

        recent = self.tool_history[-self.loop_window:]

        # Check for exact repetition
        if len(set(recent)) == 1:
            triggers.loop_detected = True
            triggers.loop_strength = 1.0
            return triggers

        # Check for alternating pattern (A-B-A-B)
        if len(set(recent)) <= 2:
            triggers.loop_detected = True
            triggers.loop_strength = 0.7
            return triggers

        # Check for repeated subsequence
        mid = len(recent) // 2
        first_half = recent[:mid]
        second_half = recent[mid:mid + len(first_half)]
        if first_half == second_half:
            triggers.loop_detected = True
            triggers.loop_strength = 0.8
            return triggers

        return triggers

    def _detect_novelty(
        self,
        prev_state: np.ndarray,
        curr_state: np.ndarray,
        triggers: EventTriggers
    ) -> EventTriggers:
        """Detect unexpected state changes"""
        # Compute state change magnitude
        diff = np.linalg.norm(curr_state - prev_state)

        # Compute expected change from history
        if len(self.state_history) >= 2:
            recent_diffs = []
            for i in range(1, min(5, len(self.state_history))):
                d = np.linalg.norm(self.state_history[-i] - self.state_history[-i-1])
                recent_diffs.append(d)
            expected_diff = np.mean(recent_diffs) if recent_diffs else 0.0
            std_diff = np.std(recent_diffs) if len(recent_diffs) > 1 else 0.1

            # Novelty = deviation from expected
            if std_diff > 0:
                z_score = (diff - expected_diff) / (std_diff + 0.01)
                if z_score > 2.0:
                    triggers.novelty_high = True
                    triggers.novelty_strength = min(1.0, z_score / 4.0)
        else:
            # First few steps - check absolute magnitude
            if diff > self.novelty_threshold:
                triggers.novelty_high = True
                triggers.novelty_strength = min(1.0, diff / 2.0)

        return triggers

    def _detect_timeout(
        self,
        elapsed_ms: float,
        triggers: EventTriggers
    ) -> EventTriggers:
        """Detect timeout condition"""
        if elapsed_ms >= self.timeout_ms:
            triggers.timeout = True
            triggers.timeout_strength = min(1.0, elapsed_ms / (self.timeout_ms * 2))
        elif elapsed_ms >= self.timeout_ms * 0.8:
            # Warning level
            triggers.timeout = True
            triggers.timeout_strength = 0.3

        return triggers

    def _update_tool_history(self, tool_result: Dict[str, Any]):
        """Update tool history for loop detection"""
        tool_name = tool_result.get('tool_name', 'unknown')
        self.tool_history.append(tool_name)
        # Keep limited history
        if len(self.tool_history) > 20:
            self.tool_history = self.tool_history[-20:]

    def _update_state_history(self, state: np.ndarray):
        """Update state history for novelty detection"""
        self.state_history.append(state.copy())
        if len(self.state_history) > 10:
            self.state_history = self.state_history[-10:]

    def reset(self):
        """Reset detector state"""
        self.tool_history = []
        self.state_history = []
        self.last_action_time = 0.0


def events_from_tool_result(
    tool_name: str,
    success: bool,
    error: Optional[str] = None,
    duration_ms: float = 0.0
) -> EventTriggers:
    """
    Convenience function to create events from a single tool result

    Args:
        tool_name: Name of the tool
        success: Whether tool succeeded
        error: Error message if failed
        duration_ms: How long the tool took

    Returns:
        EventTriggers with appropriate flags set
    """
    triggers = EventTriggers()

    if not success:
        triggers.error_detected = True
        # Classify error severity by keywords
        if error:
            error_lower = error.lower()
            if any(kw in error_lower for kw in ['critical', 'fatal', 'crash']):
                triggers.error_strength = 1.0
            elif any(kw in error_lower for kw in ['failed', 'error', 'exception']):
                triggers.error_strength = 0.7
            else:
                triggers.error_strength = 0.5
        else:
            triggers.error_strength = 0.5

    # Timeout based on duration
    if duration_ms > 30000:  # 30 seconds
        triggers.timeout = True
        triggers.timeout_strength = min(1.0, duration_ms / 60000)

    return triggers


if __name__ == "__main__":
    print("=" * 70)
    print("EVENT TRIGGERS - Testing")
    print("=" * 70)
    print()

    # Test 1: Basic event creation
    print("[1] Testing basic EventTriggers...")
    triggers = EventTriggers(
        error_detected=True,
        error_strength=0.8
    )
    print(f"    {triggers}")
    print(f"    Vector: {triggers.to_vector()}")
    print(f"    Strength vector: {triggers.to_strength_vector()}")
    print("    [OK] Basic creation working")
    print()

    # Test 2: Event detector
    print("[2] Testing EventDetector...")
    detector = EventDetector()

    # Simulate error
    result = {'tool_name': 'bash', 'success': False, 'error': 'Command failed'}
    events = detector.detect(tool_result=result)
    print(f"    Error event: {events}")
    assert events.error_detected, "Should detect error"
    print("    [OK] Error detection working")

    # Simulate goal proximity
    events = detector.detect(goal_progress=0.9)
    print(f"    Goal near: {events}")
    assert events.goal_near, "Should detect goal proximity"
    print("    [OK] Goal detection working")
    print()

    # Test 3: Loop detection
    print("[3] Testing loop detection...")
    detector.reset()
    for i in range(6):
        detector.detect(tool_result={'tool_name': 'bash', 'success': True})
    events = detector.detect(tool_result={'tool_name': 'bash', 'success': True})
    print(f"    Loop event: {events}")
    assert events.loop_detected, "Should detect loop"
    print("    [OK] Loop detection working")
    print()

    # Test 4: Convenience function
    print("[4] Testing convenience function...")
    events = events_from_tool_result(
        tool_name='docker_run',
        success=False,
        error='Container crashed',
        duration_ms=45000
    )
    print(f"    From tool result: {events}")
    assert events.error_detected, "Should detect error"
    assert events.timeout, "Should detect timeout"
    print("    [OK] Convenience function working")
    print()

    # Test 5: Tensor conversion
    print("[5] Testing tensor conversion...")
    triggers = EventTriggers(
        error_detected=True,
        error_strength=0.7,
        goal_near=True,
        goal_strength=0.9
    )
    tensor = triggers.to_tensor()
    print(f"    Tensor: {tensor}")
    print(f"    Shape: {tensor.shape}")
    assert tensor.shape == (5,), "Should be 5D tensor"
    print("    [OK] Tensor conversion working")
    print()

    print("=" * 70)
    print("EVENT TRIGGERS TESTS COMPLETE")
    print("=" * 70)
