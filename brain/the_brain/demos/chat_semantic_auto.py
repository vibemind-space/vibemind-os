"""
Auto-running semantic coherence chat demo
Runs without waiting for user input
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.multi_brain_swarm import MultiBrainSwarm
from core.semantic_coherence import SemanticEncoder


def main():
    print("=" * 70)
    print("TAHLAMUS BRAIN CHAT - WITH SEMANTIC COHERENCE")
    print("=" * 70)
    print()
    print("Initializing brain with semantic analysis...")

    # Create multi-brain swarm with semantic coherence
    swarm = MultiBrainSwarm(
        num_brains=5,
        enable_semantic_coherence=True,
        k_min=0.55,
        green_threshold=0.75,
        alpha=0.5
    )

    # Enable neural embeddings
    if swarm.semantic_layer:
        swarm.semantic_layer.encoder = SemanticEncoder(use_simple=False)
        print("[+] Neural embeddings enabled")

    print(f"[+] Created swarm with {len(swarm.brains)} specialized brains")
    print()

    for brain_id, brain in swarm.brains.items():
        print(f"  - {brain.brain_name} (expertise: {brain.expertise_level:.2f})")

    print()
    print("=" * 70)

    # Test examples
    examples = [
        ("Deploy Docker container with health checks", "docker"),
        ("Fix merge conflict in Git repository", "github"),
        ("Handle ambiguous production error", "general"),
        ("Read system log files", "filesystem"),
        ("Execute database migration script", "terminal")
    ]

    for i, (task, task_type) in enumerate(examples, 1):
        print(f"\n{'='*70}")
        print(f"EXAMPLE {i}/{len(examples)}")
        print("=" * 70)
        print(f"\n[YOU] {task}\n")

        # Get decision
        decision = swarm.collect_brain_votes(
            task_description=task,
            task_type=task_type,
            available_decisions=["suggest", "retry", "wait", "terminate"]
        )

        # Show brain responses
        print("[BRAIN] Responses:")
        print("-" * 70)
        for brain_id in decision.participating_brains:
            vote = decision.brain_votes[brain_id]
            confidence = decision.confidence_weights[brain_id]
            brain = swarm.brains[brain_id]
            print(f"  {brain.brain_name}: {vote} (confidence: {confidence:.2f})")
        print()

        # Show semantic analysis
        print("[ANALYSIS] Semantic Coherence:")
        print("-" * 70)
        print(f"  Coherence K: {decision.coherence_K:.3f}")
        print(f"  Disagreement U: {decision.disagreement_U:.3f}")
        print(f"  Voting Score: {decision.consensus_confidence:.3f}")
        print(f"  Truth Stability: {decision.truth_stability:.3f}")
        print()

        # Status
        status_map = {'GREEN': '[G]', 'YELLOW': '[Y]', 'RED': '[R]'}
        print(f"[STATUS] {status_map[decision.semantic_status]} {decision.semantic_status}")

        if decision.semantic_status == 'GREEN':
            print("  High confidence - Brains agree semantically")
        elif decision.semantic_status == 'YELLOW':
            print("  Medium confidence - Some uncertainty")
        else:
            print("  Low confidence - Clarification needed")
        print()

        # Recommendation
        print("[RECOMMENDATION]:")
        print("-" * 70)
        print(f"  Action: {decision.consensus_decision.upper()}")
        print(f"  Consensus Method: {decision.consensus_mechanism}")
        print()

    print("=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  Total decisions: {len(examples)}")

    if swarm.semantic_layer:
        stats = swarm.semantic_layer.get_statistics()
        print(f"  Avg Coherence K: {stats['avg_coherence_K']:.3f}")
        print(f"  Avg Truth Stability: {stats['avg_truth_stability']:.3f}")
        print(f"  GREEN Rate: {stats['green_rate']:.1%}")
        print(f"  YELLOW Rate: {stats['yellow_rate']:.1%}")
        print(f"  RED Rate: {stats['red_rate']:.1%}")


if __name__ == "__main__":
    main()
