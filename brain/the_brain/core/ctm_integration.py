"""
CTM (Continuous Thinking Model) Integration for ATM-R.

Connects ATM-R's adaptive routing to continuous reasoning loops.
ATM-R decides which reasoning modality (visual, verbal, spatial, etc.)
to attend to at each step.

Usage:
    from ctm_integration import CTMReasoner

    reasoner = CTMReasoner(config='configs/default.yaml')
    result = reasoner.reason(initial_state, steps=100)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from collections import deque

from core.thalamo_pc_adaptive import ThalamoPC6Adaptive
from core.thalamo_pc_live import ThalamoPC6
from core.config_loader import load_config
from monitoring.logger_viz import ATMRLogger


@dataclass
class ThoughtState:
    """
    State of continuous thinking process.

    Represents the current "mental state" in multi-step reasoning.
    """
    # Internal representations
    visual_buffer: np.ndarray      # Visual working memory
    verbal_buffer: np.ndarray      # Verbal/symbolic working memory
    spatial_buffer: np.ndarray     # Spatial reasoning buffer
    goal_state: np.ndarray         # Goal representation

    # Reasoning traces
    thought_history: List[str]     # Natural language thoughts
    confidence: float              # Confidence in current reasoning

    # Control
    step: int
    converged: bool
    interrupted: bool


class CTMReasoner:
    """
    Continuous Thinking Model with ATM-R routing.

    Uses ATM-R to dynamically route between different reasoning modalities:
    - Vision: Visual reasoning, mental imagery
    - Audio: Verbal/language-based reasoning
    - Touch: Embodied/kinesthetic reasoning
    - Taste: Reward prediction, value estimation
    - Vestibular: Spatial navigation, mental rotation
    - Threat: Safety monitoring, interrupts

    The system maintains a continuous thought stream and adaptively
    allocates attention based on task demands and safety.
    """

    def __init__(
        self,
        config: Union[str, Dict] = 'configs/default.yaml',
        adaptive: bool = True,
        thought_dim: int = 128,
        max_steps: int = 100
    ):
        """
        Initialize CTM reasoner.

        Args:
            config: ATM-R config path or dict
            adaptive: Use adaptive ATM-R
            thought_dim: Dimension of thought representations
            max_steps: Maximum reasoning steps
        """
        if isinstance(config, str):
            self.config = load_config(config)
        else:
            self.config = config

        # Create ATM-R
        self.atmr = ThalamoPC6Adaptive() if adaptive else ThalamoPC6()
        self.adaptive = adaptive

        # Reasoning parameters
        self.thought_dim = thought_dim
        self.max_steps = max_steps

        # Modality-specific reasoning modules
        self.reasoning_modules = self._init_reasoning_modules()

        # Thought history
        self.thought_stream = deque(maxlen=1000)

        # Logger
        self.logger = None

    def _init_reasoning_modules(self) -> Dict:
        """Initialize reasoning modules for each modality."""
        modules = {}

        # Vision: Visual reasoning (mental imagery, scene understanding)
        modules['vision'] = {
            'process': self._visual_reasoning,
            'description': 'Visual reasoning and mental imagery'
        }

        # Audio: Verbal reasoning (language, symbols, logic)
        modules['audio'] = {
            'process': self._verbal_reasoning,
            'description': 'Verbal and symbolic reasoning'
        }

        # Touch: Embodied reasoning (affordances, interactions)
        modules['touch'] = {
            'process': self._embodied_reasoning,
            'description': 'Embodied and kinesthetic reasoning'
        }

        # Vestibular: Spatial reasoning (navigation, mental rotation)
        modules['vestibular'] = {
            'process': self._spatial_reasoning,
            'description': 'Spatial and navigational reasoning'
        }

        # Taste: Value reasoning (rewards, costs, decisions)
        modules['taste'] = {
            'process': self._value_reasoning,
            'description': 'Value estimation and decision making'
        }

        # Threat: Safety monitoring (interrupts, alerts)
        modules['threat'] = {
            'process': self._safety_check,
            'description': 'Safety monitoring and interrupts'
        }

        return modules

    def _visual_reasoning(self, state: ThoughtState) -> Tuple[ThoughtState, str]:
        """Visual reasoning step."""
        # Simulate visual processing: update visual buffer
        state.visual_buffer += 0.1 * np.random.randn(self.thought_dim)
        state.visual_buffer = np.tanh(state.visual_buffer)  # bound

        # Generate thought
        thought = f"[Visual] Analyzing visual patterns... buffer norm={np.linalg.norm(state.visual_buffer):.2f}"

        return state, thought

    def _verbal_reasoning(self, state: ThoughtState) -> Tuple[ThoughtState, str]:
        """Verbal/symbolic reasoning step."""
        # Simulate verbal processing
        state.verbal_buffer += 0.1 * np.random.randn(self.thought_dim)
        state.verbal_buffer = np.tanh(state.verbal_buffer)

        # Simulate language-based inference
        similarity = np.dot(state.verbal_buffer, state.goal_state) / (
            np.linalg.norm(state.verbal_buffer) * np.linalg.norm(state.goal_state) + 1e-6
        )

        thought = f"[Verbal] Reasoning symbolically... goal similarity={similarity:.2f}"

        return state, thought

    def _embodied_reasoning(self, state: ThoughtState) -> Tuple[ThoughtState, str]:
        """Embodied/kinesthetic reasoning step."""
        # Simulate embodied cognition
        interaction_vec = np.random.randn(self.thought_dim) * 0.05

        state.visual_buffer += interaction_vec
        state.spatial_buffer += interaction_vec

        thought = "[Touch] Simulating embodied interactions..."

        return state, thought

    def _spatial_reasoning(self, state: ThoughtState) -> Tuple[ThoughtState, str]:
        """Spatial/navigational reasoning step."""
        # Simulate spatial transformations
        state.spatial_buffer += 0.1 * np.random.randn(self.thought_dim)
        state.spatial_buffer = np.tanh(state.spatial_buffer)

        # Mental rotation
        rotation_angle = 0.1
        # Simplified rotation in 2D subspace
        if self.thought_dim >= 2:
            x, y = state.spatial_buffer[0], state.spatial_buffer[1]
            state.spatial_buffer[0] = x * np.cos(rotation_angle) - y * np.sin(rotation_angle)
            state.spatial_buffer[1] = x * np.sin(rotation_angle) + y * np.cos(rotation_angle)

        thought = "[Vestibular] Performing mental rotation..."

        return state, thought

    def _value_reasoning(self, state: ThoughtState) -> Tuple[ThoughtState, str]:
        """Value-based reasoning and decision making."""
        # Compute expected value
        current_pos = np.mean([
            np.dot(state.visual_buffer, state.goal_state),
            np.dot(state.verbal_buffer, state.goal_state),
            np.dot(state.spatial_buffer, state.goal_state)
        ])

        expected_value = np.tanh(current_pos)
        state.confidence = 0.9 * state.confidence + 0.1 * abs(expected_value)

        thought = f"[Taste] Estimating value... EV={expected_value:.2f}, confidence={state.confidence:.2f}"

        return state, thought

    def _safety_check(self, state: ThoughtState) -> Tuple[ThoughtState, str]:
        """Safety monitoring and interrupts."""
        # Check for anomalies
        buffers = [state.visual_buffer, state.verbal_buffer, state.spatial_buffer]
        max_norm = max(np.linalg.norm(b) for b in buffers)

        if max_norm > 5.0:  # Threshold
            state.interrupted = True
            thought = f"[THREAT] Anomaly detected! max_norm={max_norm:.2f} - INTERRUPTING"
        else:
            thought = f"[Threat] Safety check passed (max_norm={max_norm:.2f})"

        return state, thought

    def reason(
        self,
        problem: str,
        initial_visual: Optional[np.ndarray] = None,
        initial_verbal: Optional[np.ndarray] = None,
        goal: Optional[np.ndarray] = None,
        steps: int = 50,
        convergence_threshold: float = 0.95,
        log_dir: Optional[str] = None
    ) -> Tuple[ThoughtState, List[str]]:
        """
        Perform continuous reasoning.

        Args:
            problem: Natural language problem description
            initial_visual: Initial visual input
            initial_verbal: Initial verbal/symbolic input
            goal: Goal state representation
            steps: Maximum reasoning steps
            convergence_threshold: Confidence threshold for convergence
            log_dir: Directory to save ATM-R logs

        Returns:
            final_state: Final thought state
            reasoning_trace: List of thought strings
        """
        print("=" * 60)
        print("CTM Continuous Reasoning")
        print("=" * 60)
        print(f"Problem: {problem}")
        print(f"Max steps: {steps}")
        print()

        # Initialize state
        state = ThoughtState(
            visual_buffer=initial_visual if initial_visual is not None else np.zeros(self.thought_dim),
            verbal_buffer=initial_verbal if initial_verbal is not None else np.zeros(self.thought_dim),
            spatial_buffer=np.zeros(self.thought_dim),
            goal_state=goal if goal is not None else np.random.randn(self.thought_dim),
            thought_history=[],
            confidence=0.0,
            step=0,
            converged=False,
            interrupted=False
        )

        # Initialize logger
        if log_dir:
            self.logger = ATMRLogger(log_dir=log_dir, save_interval=10)

        # Reasoning loop
        reasoning_trace = []

        for step in range(steps):
            # Prepare ATM-R input from current thought state
            x_t = {
                'vision': state.visual_buffer[:self.atmr.d['vision']],
                'audio': state.verbal_buffer[:self.atmr.d['audio']],
                'touch': np.zeros(self.atmr.d['touch']),
                'taste': np.zeros(self.atmr.d['taste']),
                'vestibular': state.spatial_buffer[:self.atmr.d['vestibular']],
                'threat': np.zeros(self.atmr.d['threat'])
            }

            # Context: goal-directed
            ctx = np.zeros(self.atmr.M)
            ctx[0] = 1.0  # Prefer vision initially

            # ATM-R routing
            if self.adaptive:
                out = self.atmr.step(x_t, ctx=ctx, adapt=True)
            else:
                out = self.atmr.step(x_t, ctx=ctx)

            gates = out['g']

            # Select dominant modality
            dominant_idx = np.argmax(gates)
            dominant_mod = self.atmr.modalities[dominant_idx]

            # Log
            if self.logger:
                self.logger.log_step(step, gates, out['pe'], out['v_next'])

            # Execute reasoning module
            if dominant_mod in self.reasoning_modules:
                state, thought = self.reasoning_modules[dominant_mod]['process'](state)
            else:
                thought = f"[{dominant_mod}] No reasoning module"

            # Record
            reasoning_trace.append(thought)
            state.thought_history.append(thought)
            state.step = step

            # Print
            print(f"Step {step:3d} | Gate: {dominant_mod:12s} ({gates[dominant_idx]:.2f}) | {thought}")

            # Check convergence
            if state.confidence >= convergence_threshold:
                state.converged = True
                print(f"\nConverged at step {step} (confidence={state.confidence:.2f})")
                break

            # Check interrupts
            if state.interrupted:
                print(f"\nInterrupted at step {step} (safety)")
                break

        # Save logs
        if self.logger:
            self.logger.save_csv()
            print(f"\nLogs saved to {log_dir}")

        print("\n" + "=" * 60)
        print("Reasoning complete!")
        print(f"  Steps: {state.step + 1}")
        print(f"  Converged: {state.converged}")
        print(f"  Confidence: {state.confidence:.2f}")
        print("=" * 60)

        return state, reasoning_trace


# Example usage
if __name__ == "__main__":
    # Create reasoner
    reasoner = CTMReasoner(adaptive=True)

    # Define problem
    problem = "Solve a spatial reasoning puzzle"

    # Initial conditions
    initial_visual = np.random.randn(128) * 0.5
    goal = np.random.randn(128)
    goal = goal / np.linalg.norm(goal)

    # Reason!
    final_state, trace = reasoner.reason(
        problem=problem,
        initial_visual=initial_visual,
        goal=goal,
        steps=30,
        log_dir='data/ctm_demo'
    )

    # Display thought stream
    print("\nThought Stream Summary:")
    print("-" * 60)
    for i, thought in enumerate(final_state.thought_history[-5:]):  # Last 5 thoughts
        print(f"  {i+1}. {thought}")
