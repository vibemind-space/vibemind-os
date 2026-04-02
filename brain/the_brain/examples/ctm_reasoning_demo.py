"""
CTM Reasoning Demo: Multi-Step Problem Solving with ATM-R.

Demonstrates how ATM-R's adaptive routing enables continuous thinking
across multiple reasoning modalities for complex problem solving.

Examples:
1. Spatial reasoning: Mental rotation and navigation
2. Mathematical reasoning: Verbal + visual + value estimation
3. Safety-critical reasoning: Interrupt handling
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import argparse
from ctm_integration import CTMReasoner
from logger_viz import ATMRVisualizer


def spatial_reasoning_task():
    """
    Spatial Reasoning: Navigate through a mental map.

    Task: Find optimal path from start to goal in mental space.
    """
    print("\n" + "="*60)
    print("TASK 1: Spatial Reasoning - Mental Navigation")
    print("="*60)

    reasoner = CTMReasoner(adaptive=True, thought_dim=128)

    # Start and goal positions in mental space
    start = np.zeros(128)
    start[0] = -5.0  # X coordinate
    start[1] = -5.0  # Y coordinate

    goal = np.zeros(128)
    goal[0] = 5.0
    goal[1] = 5.0

    # Encode spatial scene
    initial_visual = start.copy()
    initial_visual[10:20] = np.random.randn(10) * 0.5  # Visual features

    final_state, trace = reasoner.reason(
        problem="Navigate from (-5, -5) to (5, 5) in mental space",
        initial_visual=initial_visual,
        goal=goal,
        steps=25,
        convergence_threshold=0.9,
        log_dir='data/ctm_spatial'
    )

    # Analyze reasoning path
    print("\nReasoning Analysis:")
    print(f"  Final position: ({final_state.spatial_buffer[0]:.2f}, {final_state.spatial_buffer[1]:.2f})")
    print(f"  Distance to goal: {np.linalg.norm(final_state.spatial_buffer[:2] - goal[:2]):.2f}")

    # Visualize gates
    ATMRVisualizer.plot_gates(
        reasoner.logger,
        reasoner.atmr.modalities,
        save_path='data/ctm_spatial/gates_spatial.png'
    )

    return final_state, trace


def mathematical_reasoning_task():
    """
    Mathematical Reasoning: Solve a multi-step math problem.

    Task: Combine verbal (symbolic), visual (diagrams), and value (estimates).
    """
    print("\n" + "="*60)
    print("TASK 2: Mathematical Reasoning - Multi-Step Problem")
    print("="*60)

    reasoner = CTMReasoner(adaptive=True, thought_dim=128)

    # Problem: "If x^2 + 3x - 10 = 0, solve for x"
    # Encode problem symbolically
    initial_verbal = np.zeros(128)
    initial_verbal[0:5] = [1, 0, 3, 0, -10]  # Coefficients [x^2, x^1, x^0]
    initial_verbal += 0.1 * np.random.randn(128)

    # Visual representation (parabola)
    initial_visual = np.zeros(128)
    x_vals = np.linspace(-10, 10, 64)
    y_vals = x_vals**2 + 3*x_vals - 10
    initial_visual[:64] = y_vals / np.max(np.abs(y_vals))  # Normalized

    # Goal: Find roots (x = 2 or x = -5)
    goal = np.zeros(128)
    goal[0] = 2.0  # One solution
    goal[1] = -5.0  # Other solution

    final_state, trace = reasoner.reason(
        problem="Solve quadratic equation: x^2 + 3x - 10 = 0",
        initial_visual=initial_visual,
        initial_verbal=initial_verbal,
        goal=goal,
        steps=30,
        convergence_threshold=0.85,
        log_dir='data/ctm_math'
    )

    print("\nReasoning Analysis:")
    print(f"  Verbal buffer (symbolic state): {final_state.verbal_buffer[:5]}")
    print(f"  Visual buffer (diagram state): norm={np.linalg.norm(final_state.visual_buffer):.2f}")

    ATMRVisualizer.plot_gates(
        reasoner.logger,
        reasoner.atmr.modalities,
        save_path='data/ctm_math/gates_math.png'
    )

    return final_state, trace


def safety_critical_task():
    """
    Safety-Critical Reasoning: Interrupt handling.

    Task: Detect and respond to safety anomalies during reasoning.
    """
    print("\n" + "="*60)
    print("TASK 3: Safety-Critical Reasoning - Interrupt Handling")
    print("="*60)

    reasoner = CTMReasoner(adaptive=True, thought_dim=128)

    # Normal initial state
    initial_visual = np.random.randn(128) * 0.3

    # Goal
    goal = np.random.randn(128)
    goal = goal / np.linalg.norm(goal)

    # Inject anomaly midway (will trigger threat monitoring)
    class AnomalyInjector:
        def __init__(self, trigger_step=15):
            self.trigger_step = trigger_step
            self.original_visual_fn = None

        def inject(self, reasoner):
            self.original_visual_fn = reasoner.reasoning_modules['vision']['process']

            def anomalous_visual(state):
                if state.step == self.trigger_step:
                    # Inject anomaly: sudden large perturbation
                    state.visual_buffer += 10.0 * np.random.randn(reasoner.thought_dim)
                    thought = "[Visual] ANOMALY INJECTED - processing corrupted data!"
                else:
                    state, thought = self.original_visual_fn(state)
                return state, thought

            reasoner.reasoning_modules['vision']['process'] = anomalous_visual

    injector = AnomalyInjector(trigger_step=10)
    injector.inject(reasoner)

    final_state, trace = reasoner.reason(
        problem="Perform normal reasoning with safety monitoring",
        initial_visual=initial_visual,
        goal=goal,
        steps=30,
        convergence_threshold=0.9,
        log_dir='data/ctm_safety'
    )

    print("\nSafety Analysis:")
    print(f"  Interrupted: {final_state.interrupted}")
    print(f"  Steps before interrupt: {final_state.step + 1}")

    ATMRVisualizer.plot_gates(
        reasoner.logger,
        reasoner.atmr.modalities,
        save_path='data/ctm_safety/gates_safety.png'
    )

    return final_state, trace


def multi_task_sequence():
    """
    Multi-Task Reasoning: Sequence of different reasoning tasks.

    Demonstrates how ATM-R adapts across task switches.
    """
    print("\n" + "="*60)
    print("TASK 4: Multi-Task Sequence - Adaptive Switching")
    print("="*60)

    reasoner = CTMReasoner(adaptive=True, thought_dim=128)

    tasks = [
        ("Spatial: Navigate 2D space", 10),
        ("Verbal: Process symbolic logic", 10),
        ("Visual: Analyze patterns", 10),
        ("Value: Estimate rewards", 10)
    ]

    all_traces = []

    for task_name, task_steps in tasks:
        print(f"\n--- {task_name} ---")

        initial = np.random.randn(128) * 0.5
        goal = np.random.randn(128)
        goal = goal / np.linalg.norm(goal)

        final_state, trace = reasoner.reason(
            problem=task_name,
            initial_visual=initial,
            goal=goal,
            steps=task_steps,
            convergence_threshold=0.99,  # High threshold (won't converge, just run steps)
            log_dir=f'data/ctm_multi_{len(all_traces)}'
        )

        all_traces.extend(trace)

    print("\n" + "="*60)
    print("Multi-Task Sequence Complete!")
    print(f"  Total reasoning steps: {len(all_traces)}")
    print("="*60)

    return all_traces


def main():
    parser = argparse.ArgumentParser(description='CTM Reasoning Demo')
    parser.add_argument('--task', type=str, default='all',
                        choices=['spatial', 'math', 'safety', 'multi', 'all'],
                        help='Which task to run')

    args = parser.parse_args()

    print("=" * 60)
    print("CTM-ATM-R Continuous Reasoning Demo")
    print("=" * 60)
    print("\nDemonstrating adaptive multimodal routing for continuous thinking")
    print("across spatial, verbal, visual, and value-based reasoning.\n")

    if args.task == 'spatial' or args.task == 'all':
        spatial_reasoning_task()

    if args.task == 'math' or args.task == 'all':
        mathematical_reasoning_task()

    if args.task == 'safety' or args.task == 'all':
        safety_critical_task()

    if args.task == 'multi' or args.task == 'all':
        multi_task_sequence()

    print("\n" + "=" * 60)
    print("All tasks complete!")
    print("\nKey Insights:")
    print("  1. ATM-R dynamically routes attention across reasoning modalities")
    print("  2. Safety (threat) channel can interrupt ongoing reasoning")
    print("  3. Adaptive learning adjusts routing based on task demands")
    print("  4. Multi-step thinking emerges from modality coordination")
    print("=" * 60)


if __name__ == "__main__":
    main()
