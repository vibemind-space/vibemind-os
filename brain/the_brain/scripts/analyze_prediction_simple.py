"""
Generate and Analyze a Real Prediction (Simplified Version)

This version works without session logs by using the core components directly.
"""

import sys
import os

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import numpy as np

from core.task_feature_router import TaskFeatureRouter
from core.decision_router import DecisionRouter
from core.multi_target_router import MultiTargetDecisionRouter

def print_section(title):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def analyze_prediction(task: str):
    """
    Generate and analyze a prediction for a given task

    Args:
        task: Task description
    """
    print_section("INITIALIZING COGNITIVE SYSTEM")

    # Modalities and interventions
    modalities = [
        'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
        'tool_trace', 'temporal_pattern', 'error_signal', 'success_signal'
    ]
    intervention_types = ['suggest', 'retry', 'wait', 'terminate']

    # Initialize Layer 1
    layer1 = TaskFeatureRouter(modalities=modalities, seed=42)
    print(f"✓ Layer 1 initialized: TaskFeatureRouter")

    # Initialize Layer 3 with trained matrix
    layer3_router = MultiTargetDecisionRouter(
        num_modalities=10,
        intervention_types=intervention_types,
        seed=42
    )

    # Load trained routing matrix
    matrix_path = "production/trained_matrices/routing_matrix_v20250115_trained.npy"
    trained_matrix = np.load(matrix_path)
    layer3_router.set_routing_matrix(trained_matrix)
    print(f"✓ Layer 3 initialized: DecisionRouter (10×4 trained matrix)")

    print(f"✓ System ready!")

    print_section(f"INPUT TASK")
    print(f"\n\"{task}\"\n")

    # ========================================================================
    # LAYER 1: FEATURE EXTRACTION
    # ========================================================================
    print_section("LAYER 1: TASK FEATURE ROUTER")
    print("Extracting task features...")

    layer1_result = layer1.route_task(task)

    print(f"\n🏷️  Task Classification:")
    print(f"   Task Type:        {layer1_result.features.task_type}")
    print(f"   Complexity:       {layer1_result.features.complexity:.2f} / 1.0")
    print(f"   Urgency:          {layer1_result.features.urgency:.2f} / 1.0")
    print(f"   Processing Mode:  {layer1_result.processing_mode}")
    print(f"   Keywords:         {', '.join(layer1_result.features.keywords[:5])}")

    print(f"\n🧭 Brain Routing Weights:")
    for i, (mod, weight) in enumerate(zip(modalities, layer1_result.routing_weights)):
        if weight > 0.05:  # Only show significant weights
            bar = "█" * int(weight * 50)
            print(f"   {mod:20s} {weight:5.1%} {bar}")

    print(f"\n🎯 Dominant Brain Areas:")
    for i, area in enumerate(layer1_result.dominant_areas[:3], 1):
        print(f"   {i}. {area}")

    print(f"\n💡 Layer 1 Interpretation:")
    if layer1_result.features.urgency > 0.7:
        print(f"   → HIGH urgency detected ({layer1_result.features.urgency:.0%})")
        print(f"   → System will prioritize speed over thoroughness")
    elif layer1_result.features.urgency < 0.3:
        print(f"   → LOW urgency ({layer1_result.features.urgency:.0%})")
        print(f"   → System can take time for thorough analysis")

    if layer1_result.features.complexity > 0.7:
        print(f"   → HIGH complexity ({layer1_result.features.complexity:.0%})")
        print(f"   → Multi-step approach likely needed")
    elif layer1_result.features.complexity < 0.3:
        print(f"   → LOW complexity ({layer1_result.features.complexity:.0%})")
        print(f"   → Simple, straightforward task")

    # ========================================================================
    # SIMULATE LAYER 2: BRAIN GATING
    # ========================================================================
    print_section("LAYER 2: BRAIN SIMULATION (THALAMIC GATING)")
    print("Simulating competitive thalamic routing...")

    # Use Layer 1 routing weights as gates
    # In full system, this would come from MetaRouter with TRN inhibition
    brain_gates = layer1_result.routing_weights.copy()

    # Simulate thalamic refinement: winner-take-more effect
    temperature = 0.8
    enhanced_gates = np.exp(brain_gates / temperature)
    brain_gates = enhanced_gates / np.sum(enhanced_gates)

    print(f"\n🧠 Thalamic Gates (Softmax Normalized):")
    sorted_indices = np.argsort(brain_gates)[::-1]

    for i in range(min(5, len(sorted_indices))):
        idx = sorted_indices[i]
        name = modalities[idx]
        value = brain_gates[idx]
        bar = "█" * int(value * 50)
        print(f"   {i+1}. {name:20s} {value:5.1%} {bar}")

    print(f"\n   Gate Statistics:")
    print(f"   Sum:      {np.sum(brain_gates):.6f}  (must be 1.0)")
    print(f"   Max:      {np.max(brain_gates):.3f}")
    print(f"   Min:      {np.min(brain_gates):.3f}")

    # Calculate entropy (measure of distribution)
    entropy = -np.sum(brain_gates * np.log(brain_gates + 1e-10))
    max_entropy = np.log(len(brain_gates))
    normalized_entropy = entropy / max_entropy

    print(f"   Entropy:  {entropy:.3f} / {max_entropy:.3f} = {normalized_entropy:.1%}")

    print(f"\n💡 Gate Distribution Analysis:")
    if normalized_entropy < 0.3:
        print(f"   → FOCUSED ({normalized_entropy:.0%}): One or two modalities dominate")
        print(f"   → Clear, decisive brain routing")
    elif normalized_entropy > 0.7:
        print(f"   → DISTRIBUTED ({normalized_entropy:.0%}): Activity spread across modalities")
        print(f"   → Uncertain or complex task requiring multiple brain areas")
    else:
        print(f"   → BALANCED ({normalized_entropy:.0%}): Moderate distribution")

    # Simulate confidence (would come from ConversationPathPlanner)
    # Based on task familiarity and complexity
    base_confidence = 0.7
    complexity_penalty = layer1_result.features.complexity * 0.2
    urgency_boost = layer1_result.features.urgency * 0.1
    confidence = np.clip(base_confidence - complexity_penalty + urgency_boost, 0.3, 0.95)

    print(f"\n📊 Simulated Prediction Confidence: {confidence:.1%}")
    print(f"   (In full system, this comes from ConversationPathPlanner)")

    # ========================================================================
    # LAYER 3: DECISION ROUTING
    # ========================================================================
    print_section("LAYER 3: DECISION ROUTER (MULTI-TARGET)")
    print("Routing brain gates through trained 10×4 matrix...")

    # Get dominant modalities
    dominant_modalities = [modalities[i] for i in sorted_indices[:3]]

    # Route to decision
    decision = layer3_router.route_decision(
        gates=brain_gates,
        confidence=confidence,
        dominant_modalities=dominant_modalities
    )

    print(f"\n🎲 Multi-Target Decision Distribution:")
    print(f"\n   PRIMARY DECISION:")
    print(f"   Action:      {decision.primary.intervention_type.upper()}")
    print(f"   Weight:      {decision.primary.weight:.1%}")
    print(f"   Confidence:  {decision.primary.confidence:.1%}")
    print(f"   Reasoning:   {decision.primary.reasoning}")

    print(f"\n   ALTERNATIVE OPTIONS:")
    for i, alt in enumerate(decision.alternatives, 1):
        bar = "▓" * int(alt.weight * 50)
        print(f"   {i}. {alt.intervention_type:12s} {alt.weight:5.1%} {bar}")

    print(f"\n   Distribution Statistics:")
    print(f"   Total weight sum:  {decision.total_weight_sum:.6f}")
    primary_dominance = decision.primary.weight / decision.total_weight_sum
    print(f"   Primary dominance: {primary_dominance:.1%}")

    print(f"\n💡 Decision Interpretation:")
    if decision.primary.weight > 0.7:
        print(f"   → DECISIVE: Primary strongly dominates ({decision.primary.weight:.0%})")
        print(f"   → High certainty about best intervention")
        print(f"   → Execute primary strategy confidently")
    elif decision.primary.weight < 0.4:
        print(f"   → UNCERTAIN: Competing interventions ({decision.primary.weight:.0%})")
        print(f"   → Consider multiple strategies in parallel")
        print(f"   → Monitor closely and be ready to switch")
    else:
        print(f"   → MODERATE: Primary leads but alternatives viable")
        print(f"   → Execute primary, keep alternatives ready")

    # ========================================================================
    # MATHEMATICAL BREAKDOWN
    # ========================================================================
    print_section("MATHEMATICAL BREAKDOWN")

    print("\n📐 Step-by-Step Calculation:")

    print("\n1. LAYER 1: Feature Extraction")
    print(f"   Input: '{task}'")
    print(f"   Output: routing_weights[10] = {layer1_result.routing_weights}")

    print("\n2. LAYER 2: Thalamic Gating (Softmax)")
    print(f"   Input: routing_weights[10]")
    print(f"   Process: enhanced = exp(weights / τ), gates = enhanced / Σ(enhanced)")
    print(f"   Temperature τ = {temperature}")
    print(f"   Output: brain_gates[10] = {brain_gates}")
    print(f"   Constraint: Σ(gates) = {np.sum(brain_gates):.6f} ✓")

    print("\n3. LAYER 3: Routing Matrix Multiplication")
    print(f"   Input: gates[10] = {brain_gates}")
    print(f"   Matrix: routing_matrix[10 × 4]")
    print(f"\n   Matrix values (first 3 rows):")
    for i in range(3):
        print(f"   {modalities[i]:20s} {trained_matrix[i]}")

    print(f"\n   Calculation: intervention_logits = gates @ matrix")
    intervention_logits = np.dot(brain_gates, trained_matrix)
    print(f"   Raw logits: {intervention_logits}")

    print(f"\n   Softmax normalization:")
    exp_logits = np.exp(intervention_logits - np.max(intervention_logits))
    weights = exp_logits / np.sum(exp_logits)
    print(f"   exp(logits - max): {exp_logits}")
    print(f"   Final weights: {weights}")

    for i, (itype, w) in enumerate(zip(intervention_types, weights)):
        print(f"   {itype:12s} {w:.1%}")

    # ========================================================================
    # VISUALIZATION
    # ========================================================================
    print_section("VISUAL DECISION FLOW")

    print("\n" + " " * 20 + "COGNITIVE PROCESSING PIPELINE")
    print("\n   INPUT TASK")
    print("   │")
    print("   ├─> Layer 1: Feature Extraction")
    print(f"   │   ├─ Task Type: {layer1_result.features.task_type}")
    print(f"   │   ├─ Complexity: {layer1_result.features.complexity:.2f}")
    print(f"   │   └─ Urgency: {layer1_result.features.urgency:.2f}")
    print("   │")
    print("   ├─> Layer 2: Brain Simulation")
    print(f"   │   ├─ Dominant: {', '.join(dominant_modalities[:2])}")
    print(f"   │   ├─ Gates sum: {np.sum(brain_gates):.3f}")
    print(f"   │   └─ Confidence: {confidence:.0%}")
    print("   │")
    print("   └─> Layer 3: Decision Routing")
    print(f"       ├─ Primary: {decision.primary.intervention_type} ({decision.primary.weight:.0%})")
    for alt in decision.alternatives[:2]:
        print(f"       ├─ Alt: {alt.intervention_type} ({alt.weight:.0%})")
    print("       │")
    print("       ▼")
    print("   FINAL DECISION")

    # ========================================================================
    # RECOMMENDATIONS
    # ========================================================================
    print_section("SYSTEM RECOMMENDATIONS")

    print(f"\n✅ PRIMARY STRATEGY:")
    print(f"   ACTION: {decision.primary.intervention_type.upper()}")
    print(f"   Weight: {decision.primary.weight:.0%}")
    print(f"   Confidence: {decision.primary.confidence:.0%}")
    print(f"   Rationale: {decision.primary.reasoning}")

    print(f"\n📋 EXECUTION PLAN:")
    if decision.primary.intervention_type == 'suggest':
        print(f"   1. Provide proactive guidance based on {', '.join(dominant_modalities[:2])}")
        print(f"   2. Offer specific recommendations")
        print(f"   3. Monitor execution")
    elif decision.primary.intervention_type == 'retry':
        print(f"   1. Analyze failure mode")
        print(f"   2. Adjust parameters")
        print(f"   3. Retry with modifications")
    elif decision.primary.intervention_type == 'wait':
        print(f"   1. Monitor situation")
        print(f"   2. Gather more information")
        print(f"   3. Re-evaluate when state changes")
    elif decision.primary.intervention_type == 'terminate':
        print(f"   1. Safely stop current execution")
        print(f"   2. Rollback changes if needed")
        print(f"   3. Report critical failure")

    print(f"\n⚠️  FALLBACK STRATEGIES (if primary fails):")
    for i, alt in enumerate(decision.alternatives[:2], 1):
        print(f"   {i}. Switch to '{alt.intervention_type}' (weight: {alt.weight:.0%})")
        print(f"      {alt.reasoning}")

    if confidence < 0.5:
        print(f"\n⚡ WARNING: Low confidence ({confidence:.0%})")
        print(f"   → This may be an unfamiliar or complex task")
        print(f"   → Consider gathering more information before acting")
        print(f"   → Proceed with caution and monitor closely")

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print_section("PREDICTION SUMMARY")

    summary = {
        "task": task,
        "layer1": {
            "task_type": layer1_result.features.task_type,
            "complexity": float(layer1_result.features.complexity),
            "urgency": float(layer1_result.features.urgency),
            "processing_mode": layer1_result.processing_mode,
            "dominant_areas": layer1_result.dominant_areas[:3]
        },
        "layer2": {
            "brain_gates": brain_gates.tolist(),
            "dominant_modalities": dominant_modalities[:3],
            "confidence": float(confidence),
            "gate_entropy": float(normalized_entropy)
        },
        "layer3": {
            "primary_action": decision.primary.intervention_type,
            "primary_weight": float(decision.primary.weight),
            "primary_reasoning": decision.primary.reasoning,
            "alternatives": [
                {
                    "action": alt.intervention_type,
                    "weight": float(alt.weight),
                    "reasoning": alt.reasoning
                }
                for alt in decision.alternatives
            ],
            "confidence": float(decision.primary.confidence)
        }
    }

    print(f"\n{json.dumps(summary, indent=2)}")

    print("\n" + "=" * 80)
    print("  ✓ Analysis Complete!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    # Example task to analyze
    task = "Deploy Docker container urgently for production environment"

    analyze_prediction(task)
