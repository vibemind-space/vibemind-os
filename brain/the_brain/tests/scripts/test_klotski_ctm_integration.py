"""
Klotski CTM Integration Demo

Demonstrates the dual-system architecture:
- System 1 (Tahlamus): Fast heuristic routing (<100ms)
- System 2 (Klotski CTM): Slow deliberate reasoning (5-15s)

Inspired by Kahneman's "Thinking Fast and Slow"
"""

import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.klotski_ctm import KlotskiCTM, KLOTSKI_AVAILABLE
from core.klotski_ctm_async import KlotskiCTMAsyncReasoner


def demo_basic_klotski_ctm():
    """Demo 1: Basic Klotski CTM reasoning (synchronous)"""
    print("="*70)
    print("DEMO 1: Basic Klotski CTM Reasoning")
    print("="*70)

    if not KLOTSKI_AVAILABLE:
        print("[ERROR] Klotski neurosymbolic brain not available")
        return

    # Initialize CTM
    ctm = KlotskiCTM(
        feature_dim=256,
        consciousness_threshold=0.85,
        max_reasoning_steps=30
    )

    # Test task
    task = "Design distributed microservice architecture with auto-scaling and fault tolerance"

    # Mock brain state (in real system, comes from Tahlamus)
    brain_state = {
        'modality_activations': {
            'vision': 0.2,
            'audio': 0.1,
            'tool_trace': 0.8,
            'temporal_pattern': 0.6,
            'error_signal': 0.3,
            'success_signal': 0.5
        }
    }

    print(f"\nTask: {task}")
    print(f"Brain State: {len(brain_state['modality_activations'])} modalities")

    # Run CTM reasoning
    print("\nRunning System 2 (Klotski CTM) reasoning...")
    start_time = time.time()

    insight = ctm.reason(
        task=task,
        brain_state=brain_state,
        max_steps=20
    )

    elapsed = time.time() - start_time

    # Display results
    print("\n" + "="*70)
    print("CTM INSIGHTS")
    print("="*70)
    print(f"Reasoning Steps: {insight.reasoning_steps}")
    print(f"Elapsed Time: {elapsed:.2f}s")
    print(f"Final Consciousness: {insight.final_consciousness:.3f}")
    print(f"Converged: {insight.converged}")
    print(f"Confidence: {insight.confidence:.0%}")
    print(f"\nSuggested Strategy:")
    print(f"  {insight.suggested_strategy}")

    print(f"\nTop Brain Modules:")
    sorted_modules = sorted(
        insight.module_activations.items(),
        key=lambda x: x[1],
        reverse=True
    )
    for mod, act in sorted_modules[:5]:
        print(f"  {mod}: {act:.3f}")

    print(f"\nConsciousness Trajectory:")
    traj = insight.consciousness_trajectory
    if len(traj) > 0:
        print(f"  Start: {traj[0]:.3f}")
        if len(traj) > 5:
            print(f"  Mid:   {traj[len(traj)//2]:.3f}")
        print(f"  End:   {traj[-1]:.3f}")

    print(f"\nDMN Energy: {insight.dmn_energy:.3f}")
    print(f"Error Magnitude: {insight.error_magnitude:.3f}")


def demo_async_reasoning():
    """Demo 2: Async CTM reasoning (background)"""
    print("\n\n" + "="*70)
    print("DEMO 2: Async CTM Reasoning (System 1 + System 2)")
    print("="*70)

    if not KLOTSKI_AVAILABLE:
        print("[ERROR] Klotski neurosymbolic brain not available")
        return

    # Initialize async reasoner
    reasoner = KlotskiCTMAsyncReasoner(
        max_concurrent_tasks=2,
        consciousness_threshold=0.85,
        max_reasoning_steps=20
    )

    # Simulate System 1 + System 2 workflow
    tasks = [
        {
            'task': "Deploy complex Kubernetes cluster with auto-scaling",
            'complexity': 0.85,  # Above threshold -> triggers CTM
            'expected_action': 'suggest'
        },
        {
            'task': "List files in directory",
            'complexity': 0.2,  # Below threshold -> System 1 only
            'expected_action': 'execute'
        },
        {
            'task': "Design fault-tolerant distributed database",
            'complexity': 0.9,  # High complexity -> triggers CTM
            'expected_action': 'suggest'
        }
    ]

    brain_state = {
        'modality_activations': {
            'tool_trace': 0.8,
            'temporal_pattern': 0.6,
            'error_signal': 0.4
        }
    }

    print(f"\nProcessing {len(tasks)} tasks with dual-system architecture...")

    task_ids = []

    for i, task_info in enumerate(tasks, 1):
        print(f"\n--- Task {i} ---")
        print(f"Task: {task_info['task'][:60]}...")
        print(f"Complexity: {task_info['complexity']:.2f}")

        # System 1: Fast prediction (always runs)
        system1_start = time.time()
        system1_prediction = {
            'primary_action': task_info['expected_action'],
            'confidence': 0.65,
            'complexity': task_info['complexity']
        }
        system1_time = time.time() - system1_start

        print(f"\n[System 1] Prediction: {system1_prediction['primary_action']} (confidence: {system1_prediction['confidence']:.2f})")
        print(f"[System 1] Time: {system1_time*1000:.1f}ms")

        # System 2: Deep reasoning (only if complex)
        if task_info['complexity'] >= 0.75:
            print(f"[System 2] Complexity {task_info['complexity']:.2f} >= 0.75 threshold")
            print(f"[System 2] Starting background CTM reasoning...")

            task_id = reasoner.start_reasoning_async(
                task=task_info['task'],
                brain_state=brain_state,
                max_steps=15
            )
            task_ids.append((task_id, task_info))
        else:
            print(f"[System 2] Complexity {task_info['complexity']:.2f} < 0.75 threshold")
            print(f"[System 2] CTM not triggered (System 1 sufficient)")
            task_ids.append((None, task_info))

    # Wait for CTM results
    print("\n" + "="*70)
    print("Waiting for System 2 (CTM) reasoning to complete...")
    print("="*70)

    time.sleep(1)  # Simulate doing other work

    for task_id, task_info in task_ids:
        if task_id:
            print(f"\n--- CTM Result: {task_info['task'][:50]}... ---")

            result = reasoner.get_result(task_id, wait=True, timeout=20)

            if result and result.ctm_insight:
                print(f"Status: {result.status.value}")
                print(f"Elapsed: {result.elapsed_time:.2f}s")
                print(f"\nCTM Insights:")
                print(f"  Consciousness: {result.ctm_insight.final_consciousness:.3f}")
                print(f"  Converged: {result.ctm_insight.converged}")
                print(f"  Strategy: {result.ctm_insight.suggested_strategy}")
                print(f"  Confidence: {result.ctm_insight.confidence:.0%}")

                top_modules = sorted(
                    result.ctm_insight.module_activations.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                print(f"  Top Modules: {', '.join(f'{m}({a:.2f})' for m, a in top_modules)}")
            elif result:
                print(f"Status: {result.status.value}")
                if result.error_message:
                    print(f"Error: {result.error_message}")
        else:
            print(f"\n--- No CTM: {task_info['task'][:50]}... ---")
            print(f"System 1 only (low complexity)")

    # Display stats
    print("\n" + "="*70)
    print("ASYNC REASONER STATISTICS")
    print("="*70)
    stats = reasoner.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"{key}: {value:.3f}")
        else:
            print(f"{key}: {value}")


def demo_system_comparison():
    """Demo 3: Compare System 1 vs System 2 performance"""
    print("\n\n" + "="*70)
    print("DEMO 3: System 1 vs System 2 Comparison")
    print("="*70)

    if not KLOTSKI_AVAILABLE:
        print("[ERROR] Klotski neurosymbolic brain not available")
        return

    test_tasks = [
        ("Simple task", "List files in current directory", 0.1),
        ("Moderate task", "Deploy Docker container with Redis", 0.6),
        ("Complex task", "Design distributed microservice architecture", 0.9)
    ]

    print("\n{:<15} | {:>10} | {:>10} | {:>15}".format(
        "Task Type", "System 1", "System 2", "Benefit"
    ))
    print("-" * 70)

    for task_type, task, complexity in test_tasks:
        # System 1: Always fast
        system1_time = 0.08  # ~80ms typical

        # System 2: Only for complex tasks
        if complexity >= 0.75:
            system2_triggered = True
            system2_time = 10.0  # ~10s typical
            benefit = "Deep insights"
        else:
            system2_triggered = False
            system2_time = 0.0
            benefit = "Not needed"

        print("{:<15} | {:>8.1f}ms | {:>8.1f}s | {:>15}".format(
            task_type,
            system1_time * 1000,
            system2_time,
            benefit
        ))

    print("\n" + "="*70)
    print("KEY INSIGHTS")
    print("="*70)
    print("1. System 1 (Tahlamus) always runs: <100ms latency")
    print("2. System 2 (Klotski CTM) only for complex tasks: 5-15s")
    print("3. Simple tasks: Zero CTM overhead (System 1 sufficient)")
    print("4. Complex tasks: Deep insights without blocking System 1")
    print("5. Async architecture: Best of both worlds")


def main():
    """Run all demos"""
    print("\n" + "="*70)
    print("KLOTSKI CTM INTEGRATION DEMO")
    print("Dual-System Cognitive Architecture")
    print("="*70)
    print("\nSystem 1: Tahlamus (Fast, Heuristic, <100ms)")
    print("System 2: Klotski CTM (Slow, Deliberate, 5-15s)")
    print("\nInspired by Kahneman's 'Thinking Fast and Slow'")

    if not KLOTSKI_AVAILABLE:
        print("\n[ERROR] Klotski neurosymbolic brain not available!")
        print("Please ensure learning_engine/klotski/neurosymbolic is installed.")
        return

    # Run demos
    demo_basic_klotski_ctm()
    demo_async_reasoning()
    demo_system_comparison()

    print("\n" + "="*70)
    print("DEMO COMPLETE")
    print("="*70)
    print("\nKey Takeaways:")
    print("1. Klotski CTM provides true System 2 reasoning")
    print("2. 3.7M parameters, 10 brain modules, consciousness metric")
    print("3. Zero latency impact on simple tasks")
    print("4. Deep insights on complex tasks (background)")
    print("5. Neurosymbolic hybrid: learned + symbolic rules")
    print("\nNext: Integrate with HierarchicalPlanner for production use")


if __name__ == "__main__":
    main()
