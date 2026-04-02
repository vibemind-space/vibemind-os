"""
Interactive Semantic Coherence Demo
Shows step-by-step what happens inside the system
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from core.multi_brain_swarm import MultiBrainSwarm
from core.semantic_coherence import SemanticEncoder

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70 + "\n")

def print_step(number, text):
    print(f"\n--- Step {number}: {text} ---\n")

def main():
    print_header("INTERACTIVE SEMANTIC COHERENCE DEMO")

    # Step 1: Create encoder
    print_step(1, "Create Semantic Encoder")
    encoder = SemanticEncoder(use_simple=False)
    print("Created neural encoder (sentence-transformers)")
    print(f"Embedding dimension: 384")

    # Step 2: Show how text becomes embeddings
    print_step(2, "Convert Text to Embeddings")

    texts = [
        "Deploy Docker container with health checks",
        "Start Docker service with monitoring",
        "Eat pizza with friends"
    ]

    embeddings = []
    for i, text in enumerate(texts):
        emb = encoder.encode(text)
        embeddings.append(emb)
        print(f"Text {i+1}: '{text}'")
        print(f"  -> Embedding: [{emb[0]:.3f}, {emb[1]:.3f}, {emb[2]:.3f}, ..., {emb[-1]:.3f}]")
        print(f"  -> Vector length: {len(emb)}")
        print(f"  -> Normalized: {np.linalg.norm(emb):.3f} (should be 1.0)")

    # Step 3: Compute similarities
    print_step(3, "Compute Semantic Similarities")

    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    print("Pairwise similarities:")
    sim_12 = cosine_similarity(embeddings[0], embeddings[1])
    sim_13 = cosine_similarity(embeddings[0], embeddings[2])
    sim_23 = cosine_similarity(embeddings[1], embeddings[2])

    print(f"  Text 1 <-> Text 2: {sim_12:.3f} (both about Docker - HIGH)")
    print(f"  Text 1 <-> Text 3: {sim_13:.3f} (Docker vs pizza - LOW)")
    print(f"  Text 2 <-> Text 3: {sim_23:.3f} (Docker vs pizza - LOW)")

    # Step 4: Compute coherence K
    print_step(4, "Compute Coherence K")

    similarities = [sim_12, sim_13, sim_23]
    K = np.mean(similarities)
    U = np.var(similarities)

    print(f"All pairwise similarities: {[f'{s:.3f}' for s in similarities]}")
    print(f"Average (K): {K:.3f}")
    print(f"Variance (U): {U:.3f}")
    print(f"\nInterpretation:")
    print(f"  K={K:.3f} means {'HIGH' if K > 0.7 else 'MEDIUM' if K > 0.5 else 'LOW'} coherence")
    print(f"  U={U:.3f} means {'HIGH' if U > 0.1 else 'LOW'} disagreement")

    # Step 5: Multi-Brain Swarm simulation
    print_step(5, "Multi-Brain Swarm Decision")

    print("Simulating 5 brains making decisions...\n")

    brain_answers = [
        "suggest deploying Docker with health checks",
        "suggest using Docker with monitoring",
        "suggest containerized deployment",
        "suggest Docker service with validation",
        "suggest container orchestration"
    ]

    print("Brain Answers:")
    for i, answer in enumerate(brain_answers):
        print(f"  Brain {i}: '{answer}'")

    print("\nConverting to embeddings...")
    brain_embeddings = [encoder.encode(ans) for ans in brain_answers]

    print("\nComputing pairwise similarities:")
    n = len(brain_embeddings)
    similarities = []
    for i in range(n):
        for j in range(i+1, n):
            sim = cosine_similarity(brain_embeddings[i], brain_embeddings[j])
            similarities.append(sim)
            print(f"  Brain {i} <-> Brain {j}: {sim:.3f}")

    K = np.mean(similarities)
    U = np.var(similarities)

    print(f"\nCoherence Metrics:")
    print(f"  K (average similarity): {K:.3f}")
    print(f"  U (variance): {U:.3f}")

    # Step 6: Truth Stability
    print_step(6, "Compute Truth Stability")

    voting_score = 0.80  # Example: 80% of brains agree
    alpha = 0.5

    print(f"Voting Score: {voting_score:.3f} (80% brains voted 'suggest')")
    print(f"Coherence K: {K:.3f}")
    print(f"Alpha (weight): {alpha:.3f}")
    print(f"\nTruth Stability Formula:")
    print(f"  truth_stability = alpha × voting_score + (1-alpha) × K")
    print(f"  truth_stability = {alpha} × {voting_score:.3f} + {1-alpha} × {K:.3f}")

    truth_stability = alpha * voting_score + (1-alpha) * K
    print(f"  truth_stability = {truth_stability:.3f}")

    # Step 7: Traffic Light
    print_step(7, "Determine Traffic Light Status")

    k_min = 0.55
    green_threshold = 0.75

    print(f"Thresholds:")
    print(f"  GREEN: truth_stability >= {green_threshold}")
    print(f"  YELLOW: {k_min} <= truth_stability < {green_threshold}")
    print(f"  RED: truth_stability < {k_min}")

    print(f"\nCurrent truth_stability: {truth_stability:.3f}")

    if truth_stability >= green_threshold:
        status = "GREEN"
        meaning = "High confidence - Deploy/Execute"
    elif truth_stability >= k_min:
        status = "YELLOW"
        meaning = "Medium confidence - Review needed"
    else:
        status = "RED"
        meaning = "Low confidence - Clarification required"

    print(f"Status: {status}")
    print(f"Meaning: {meaning}")

    # Step 8: Complete Example
    print_step(8, "Complete Example with Real Swarm")

    swarm = MultiBrainSwarm(
        num_brains=5,
        enable_semantic_coherence=True,
        k_min=0.55,
        green_threshold=0.75,
        alpha=0.5
    )

    # Override encoder
    if swarm.semantic_layer:
        swarm.semantic_layer.encoder = SemanticEncoder(use_simple=False)

    print("Created swarm with 5 specialized brains")
    print("\nMaking decision...")

    decision = swarm.collect_brain_votes(
        task_description="Deploy Docker container urgently",
        task_type="docker",
        available_decisions=["suggest", "retry", "wait", "terminate"]
    )

    print(f"\nResults:")
    print(f"  Task: Deploy Docker container urgently")
    print(f"  Decision: {decision.consensus_decision}")
    print(f"  Mechanism: {decision.consensus_mechanism}")
    print(f"  Voting Score: {decision.consensus_confidence:.3f}")
    print(f"  Coherence K: {decision.coherence_K:.3f}")
    print(f"  Disagreement U: {decision.disagreement_U:.3f}")
    print(f"  Truth Stability: {decision.truth_stability:.3f}")
    print(f"  Status: {decision.semantic_status}")

    print(f"\nDetailed Voting:")
    for brain_id, vote in decision.brain_votes.items():
        confidence = decision.confidence_weights[brain_id]
        print(f"  {brain_id}: {vote} (confidence: {confidence:.3f})")

    # Summary
    print_header("SUMMARY")
    print("Flow:")
    print("  1. Text -> Embeddings (384-dim vectors)")
    print("  2. Embeddings -> Similarities (cosine)")
    print("  3. Similarities -> Coherence K (average)")
    print("  4. K + Voting -> Truth Stability")
    print("  5. Truth Stability -> Traffic Light (GREEN/YELLOW/RED)")

    print("\nKey Insight:")
    print("  High K = Brains agree semantically = High truth")
    print("  Low K = Brains disagree = Need clarification")

    print("\n" + "="*70)

if __name__ == "__main__":
    main()
