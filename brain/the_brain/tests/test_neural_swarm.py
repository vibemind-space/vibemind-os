"""
Test Multi-Brain Swarm with NEURAL embeddings
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.multi_brain_swarm import MultiBrainSwarm

print("="*70)
print("NEURAL EMBEDDINGS TEST - Multi-Brain Swarm")
print("="*70)

# Create swarm with neural embeddings (adjusted thresholds)
swarm = MultiBrainSwarm(
    num_brains=5,
    enable_semantic_coherence=True,
    k_min=0.55,  # Adjusted for neural embeddings
    green_threshold=0.75,  # Adjusted for neural embeddings
    alpha=0.5
)

# Override encoder to use neural
from core.semantic_coherence import SemanticEncoder
if swarm.semantic_layer:
    swarm.semantic_layer.encoder = SemanticEncoder(use_simple=False)
    print("[+] Switched to neural embeddings")

print("\n" + "="*70)
print("TEST 1: High Agreement Task")
print("="*70)

# All brains should agree on Docker task
decision1 = swarm.collect_brain_votes(
    task_description="Deploy Docker container with health checks",
    task_type="docker",
    available_decisions=["suggest", "retry", "wait", "terminate"],
    brain_reasonings={
        'brain_0': "suggest deploying Docker container with proper health monitoring",
        'brain_1': "suggest using Docker with automated health checks",
        'brain_2': "suggest containerized deployment with monitoring",
        'brain_3': "suggest Docker service with health validation",
        'brain_4': "suggest container orchestration with checks"
    }
)

print(f"\nTask: Deploy Docker container")
print(f"Decision: {decision1.consensus_decision}")
print(f"Voting Score: {decision1.consensus_confidence:.3f}")
print(f"Coherence K: {decision1.coherence_K:.3f}")
print(f"Disagreement U: {decision1.disagreement_U:.3f}")
print(f"Truth Stability: {decision1.truth_stability:.3f}")
print(f"Status: {decision1.semantic_status}")

print("\n" + "="*70)
print("TEST 2: Low Agreement Task (Conflicting)")
print("="*70)

# Brains disagree - different actions
decision2 = swarm.collect_brain_votes(
    task_description="Handle ambiguous error in production",
    task_type="terminal",
    available_decisions=["suggest", "retry", "wait", "terminate"],
    brain_reasonings={
        'brain_0': "retry the operation because transient errors often resolve",
        'brain_1': "wait and gather more information before acting",
        'brain_2': "terminate the process to prevent cascading failures",
        'brain_3': "suggest debugging the root cause immediately",
        'brain_4': "retry with exponential backoff strategy"
    }
)

print(f"\nTask: Handle ambiguous error")
print(f"Decision: {decision2.consensus_decision}")
print(f"Voting Score: {decision2.consensus_confidence:.3f}")
print(f"Coherence K: {decision2.coherence_K:.3f}")
print(f"Disagreement U: {decision2.disagreement_U:.3f}")
print(f"Truth Stability: {decision2.truth_stability:.3f}")
print(f"Status: {decision2.semantic_status}")

print("\n" + "="*70)
print("COMPARISON: Hash-TF-IDF vs Neural Embeddings")
print("="*70)

print("\nExpected with Hash-TF-IDF:")
print("  Test 1 (agreement):   K=0.88, Status=YELLOW")
print("  Test 2 (disagreement): K=0.88, Status=YELLOW (no difference!)")

print("\nActual with Neural Embeddings:")
print(f"  Test 1 (agreement):   K={decision1.coherence_K:.2f}, Status={decision1.semantic_status}")
print(f"  Test 2 (disagreement): K={decision2.coherence_K:.2f}, Status={decision2.semantic_status}")

if decision1.coherence_K > decision2.coherence_K + 0.1:
    print("\n[+] SUCCESS! Neural embeddings can distinguish agreement from disagreement!")
else:
    print("\n[!] Embeddings not distinguishing well enough")

print("\n" + "="*70)
