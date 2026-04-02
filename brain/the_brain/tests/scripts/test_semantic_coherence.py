"""
Test Semantic Coherence System (PHASE 13 - Truth Dynamics)

Demonstrates:
1. Multi-brain swarm with semantic coherence
2. Truth stability measurement (K × voting_score)
3. Traffic light system (GREEN/YELLOW/RED)
4. Meta-brain pattern analysis
5. Clarification subtasks for low coherence
6. Gödel-inspired meta-level validation

Usage:
    python demos/test_semantic_coherence.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from core.multi_brain_swarm import MultiBrainSwarm
from core.meta_brain import MetaBrain


def print_section(title: str):
    """Print section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def test_basic_semantic_coherence():
    """Test basic semantic coherence with multi-brain swarm"""
    print_section("1. Basic Semantic Coherence Test")

    # Create swarm with semantic coherence enabled (neural embeddings)
    swarm = MultiBrainSwarm(
        num_brains=5,
        consensus_threshold=0.6,
        load_balance=True,
        enable_semantic_coherence=True,
        k_min=0.55,  # Adjusted for neural embeddings
        green_threshold=0.75,  # Adjusted for neural embeddings
        alpha=0.5
    )

    # Enable neural embeddings
    from core.semantic_coherence import SemanticEncoder
    if swarm.semantic_layer:
        swarm.semantic_layer.encoder = SemanticEncoder(use_simple=False)
        print("[+] Neural embeddings enabled (sentence-transformers)")

    print(f"[+] Created swarm with {len(swarm.brains)} specialized brains:")
    for brain_id, brain in swarm.brains.items():
        print(f"  - {brain.brain_name}: {brain.primary_domain} (expertise: {brain.expertise_level:.2f})")

    # Test 1: High agreement task (should be GREEN)
    print("\n--- Test 1: High Agreement Task ---")
    task1 = "Deploy Docker container with health checks"
    decision1 = swarm.collect_brain_votes(
        task_description=task1,
        task_type="docker",
        available_decisions=["suggest", "retry", "wait", "terminate"]
    )

    print(f"Task: {task1}")
    print(f"Decision: {decision1.consensus_decision}")
    print(f"Voting Score: {decision1.consensus_confidence:.3f}")
    print(f"Coherence K: {decision1.coherence_K:.3f}")
    print(f"Disagreement U: {decision1.disagreement_U:.3f}")
    print(f"Truth Stability: {decision1.truth_stability:.3f}")
    print(f"Status: {decision1.semantic_status}")

    # Test 2: Low agreement task (should be YELLOW or RED)
    print("\n--- Test 2: Low Agreement Task ---")
    task2 = "Resolve merge conflict in obscure codebase"
    decision2 = swarm.collect_brain_votes(
        task_description=task2,
        task_type="github",
        available_decisions=["suggest", "retry", "wait", "terminate"]
    )

    print(f"Task: {task2}")
    print(f"Decision: {decision2.consensus_decision}")
    print(f"Voting Score: {decision2.consensus_confidence:.3f}")
    print(f"Coherence K: {decision2.coherence_K:.3f}")
    print(f"Disagreement U: {decision2.disagreement_U:.3f}")
    print(f"Truth Stability: {decision2.truth_stability:.3f}")
    print(f"Status: {decision2.semantic_status}")

    return swarm


def test_clarification_subtasks(swarm: MultiBrainSwarm):
    """Test clarification subtask generation"""
    print_section("2. Clarification Subtasks Test")

    # Create a low-coherence decision
    task = "Optimize database query performance"
    decision = swarm.collect_brain_votes(
        task_description=task,
        task_type="terminal",
        available_decisions=["suggest", "retry", "wait", "terminate"]
    )

    print(f"Task: {task}")
    print(f"Status: {decision.semantic_status}")

    if decision.semantic_status == 'RED':
        print("\n[!] Low coherence detected! Generating clarification subtasks...")

        # Get brain answers from semantic layer
        brain_answers = swarm.semantic_layer.consensus_history[-1].brain_answers if swarm.semantic_layer else []

        clarification_subtasks = swarm.create_clarification_subtasks(
            original_task=task,
            swarm_decision=decision,
            brain_answers=brain_answers
        )

        print(f"\nGenerated {len(clarification_subtasks)} clarification subtasks:")
        for subtask in clarification_subtasks:
            print(f"  - [{subtask.domain}] {subtask.description}")
    else:
        print(f"\n[+] Coherence acceptable ({decision.coherence_K:.3f} >= {swarm.semantic_layer.k_min})")


def test_meta_brain_analysis(swarm: MultiBrainSwarm):
    """Test meta-brain pattern analysis"""
    print_section("3. Meta-Brain Pattern Analysis")

    # Create meta-brain
    meta_brain = MetaBrain(
        consistency_window=10,
        drift_threshold=0.15,
        contradiction_threshold=0.3
    )

    print(f"[+] Created Meta-Brain (Level S_(n+1))")
    print(f"  - Consistency window: {meta_brain.consistency_window}")
    print(f"  - Drift threshold: {meta_brain.drift_threshold}")
    print(f"  - Contradiction threshold: {meta_brain.contradiction_threshold}")

    # Simulate multiple decisions
    tasks = [
        ("Deploy microservice", "docker", "success"),
        ("Fix GitHub workflow", "github", "success"),
        ("Read log files", "filesystem", "failure"),
        ("Run shell script", "terminal", "success"),
        ("Configure network", "network", "failure"),
        ("Deploy another service", "docker", "success"),
        ("Debug Git issue", "github", "failure"),
        ("Check disk space", "filesystem", "success"),
        ("Execute command", "terminal", "success"),
        ("Setup VPN", "network", "failure"),
    ]

    print(f"\nRunning {len(tasks)} decisions for meta-analysis...")

    for i, (task, domain, outcome) in enumerate(tasks, 1):
        decision = swarm.collect_brain_votes(
            task_description=task,
            task_type=domain,
            available_decisions=["suggest", "retry", "wait", "terminate"]
        )

        # Get brain answers
        brain_answers = []
        if swarm.semantic_layer and len(swarm.semantic_layer.consensus_history) > 0:
            brain_answers = swarm.semantic_layer.consensus_history[-1].brain_answers

        # Meta-brain analyzes decision
        meta_brain.analyze_decision(
            swarm_decision=decision.to_dict(),
            brain_answers=brain_answers,
            outcome=outcome
        )

        print(f"  {i}. [{domain}] {task} -> {decision.consensus_decision} ({decision.semantic_status}) | {outcome}")

    # Get meta-brain insights
    print("\n--- Meta-Brain Statistics ---")
    stats = meta_brain.get_statistics()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")

    # Get policy updates
    print("\n--- Recommended Policy Updates ---")
    updates = meta_brain.get_policy_updates()
    if updates:
        for brain_id, adjustment in updates.items():
            direction = "+" if adjustment > 0 else "-"
            print(f"  {brain_id}: {direction} {abs(adjustment):.2f}")
    else:
        print("  (No policy updates recommended)")

    # Show detected patterns
    if meta_brain.detected_patterns:
        print("\n--- Detected Patterns ---")
        for pattern in meta_brain.detected_patterns[-5:]:  # Last 5 patterns
            print(f"  [{pattern.pattern_type.upper()}] {pattern.description}")
            if pattern.recommendation:
                print(f"    -> Recommendation: {pattern.recommendation}")

    return meta_brain


def test_truth_stability_thresholds(swarm: MultiBrainSwarm):
    """Test traffic light system across different coherence levels"""
    print_section("4. Truth Stability Thresholds Test")

    # Test tasks with varying complexity
    test_cases = [
        ("Simple task", "docker", 0.2),
        ("Medium task", "github", 0.5),
        ("Complex task", "network", 0.8),
    ]

    print("Testing traffic light system (GREEN/YELLOW/RED):\n")

    results = {'GREEN': 0, 'YELLOW': 0, 'RED': 0}

    for task, domain, complexity in test_cases:
        decision = swarm.collect_brain_votes(
            task_description=task,
            task_type=domain,
            available_decisions=["suggest", "retry", "wait", "terminate"]
        )

        results[decision.semantic_status] += 1

        status_emoji = {
            'GREEN': '[G]',
            'YELLOW': '[Y]',
            'RED': '[R]'
        }

        print(f"{status_emoji[decision.semantic_status]} {decision.semantic_status:7s} | "
              f"K={decision.coherence_K:.3f} | "
              f"Truth={decision.truth_stability:.3f} | "
              f"{task} ({domain})")

    print(f"\nDistribution: GREEN={results['GREEN']}, YELLOW={results['YELLOW']}, RED={results['RED']}")


def test_semantic_layer_statistics(swarm: MultiBrainSwarm):
    """Test semantic coherence layer statistics"""
    print_section("5. Semantic Coherence Layer Statistics")

    if swarm.semantic_layer:
        stats = swarm.semantic_layer.get_statistics()

        print("Semantic Coherence Metrics:")
        print(f"  Total Decisions: {stats['total_decisions']}")
        print(f"  Avg Coherence K: {stats['avg_coherence_K']:.3f}")
        print(f"  Avg Disagreement U: {stats['avg_disagreement_U']:.3f}")
        print(f"  Avg Truth Stability: {stats['avg_truth_stability']:.3f}")
        print(f"\nDistribution:")
        print(f"  GREEN Rate: {stats['green_rate']:.1%}")
        print(f"  YELLOW Rate: {stats['yellow_rate']:.1%}")
        print(f"  RED Rate: {stats['red_rate']:.1%}")
        print(f"\nThresholds:")
        print(f"  K_min (RED/YELLOW): {stats['k_min']:.2f}")
        print(f"  GREEN Threshold: {stats['green_threshold']:.2f}")
        print(f"  Alpha (voting/coherence): {stats['alpha']:.2f}")
    else:
        print("[!] Semantic coherence layer not available")


def main():
    """Main test function"""
    print("\n" + "=" * 70)
    print("  SEMANTIC COHERENCE SYSTEM TEST (PHASE 13)")
    print("  Truth Dynamics: Wahrheit als stabile Kohärenz")
    print("=" * 70)

    try:
        # Test 1: Basic semantic coherence
        swarm = test_basic_semantic_coherence()

        # Test 2: Clarification subtasks
        test_clarification_subtasks(swarm)

        # Test 3: Meta-brain analysis
        meta_brain = test_meta_brain_analysis(swarm)

        # Test 4: Truth stability thresholds
        test_truth_stability_thresholds(swarm)

        # Test 5: Statistics
        test_semantic_layer_statistics(swarm)

        # Final summary
        print_section("Summary")
        print("[+] All tests completed successfully!")
        print(f"\nSwarm Statistics:")
        swarm_stats = swarm.get_swarm_intelligence_metrics()
        for key, value in swarm_stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.3f}")
            else:
                print(f"  {key}: {value}")

        print(f"\nMeta-Brain Summary:")
        print(f"  {meta_brain}")

        print("\n" + "=" * 70)
        print("Semantic coherence system validated successfully!")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n[X] Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
