"""
Generate and Analyze a Real Prediction

This script creates a real prediction using the production system
and provides detailed analysis of all components.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import numpy as np
from production.production_planner import ProductionPlanner

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
    print_section("INITIALIZING PRODUCTION PLANNER")

    # Initialize planner
    planner = ProductionPlanner(
        session_log_dir="data/logs/sessions",
        matrix_version="v20250115_trained",  # Use trained matrix
        enable_continuous_learning=False,     # Disable for analysis
        seed=42
    )

    print(f"✓ Loaded routing matrix: {planner.matrix_version}")
    print(f"✓ Total predictions made: {planner.total_predictions}")
    print(f"✓ Session log directory: data/logs/sessions")

    print_section(f"INPUT TASK")
    print(f"\n{task}\n")

    print_section("GENERATING PREDICTION")
    print("Running through 3-layer hierarchy...")

    # Make prediction
    result = planner.predict(task)

    print("✓ Prediction complete!")

    # ========================================================================
    # LAYER 1 ANALYSIS
    # ========================================================================
    print_section("LAYER 1: TASK FEATURE ROUTER")

    pred = result['prediction']
    print(f"\n🏷️  Task Classification:")
    print(f"   Task Type:    {pred['task_type']}")
    print(f"   Complexity:   {pred['complexity']:.2f} / 1.0")
    print(f"   Urgency:      {pred['urgency']:.2f} / 1.0")
    print(f"   Mode:         {pred['processing_mode']}")

    print(f"\n💡 Interpretation:")
    if pred['urgency'] > 0.7:
        print(f"   → HIGH urgency detected ({pred['urgency']:.0%})")
        print(f"   → System will prioritize speed over thoroughness")
    elif pred['urgency'] < 0.3:
        print(f"   → LOW urgency ({pred['urgency']:.0%})")
        print(f"   → System can take time for thorough analysis")
    else:
        print(f"   → MODERATE urgency ({pred['urgency']:.0%})")

    if pred['complexity'] > 0.7:
        print(f"   → HIGH complexity ({pred['complexity']:.0%})")
        print(f"   → Multi-step approach likely needed")
    elif pred['complexity'] < 0.3:
        print(f"   → LOW complexity ({pred['complexity']:.0%})")
        print(f"   → Simple, straightforward task")

    # ========================================================================
    # LAYER 2 ANALYSIS
    # ========================================================================
    print_section("LAYER 2: CONVERSATION PATH PLANNER (BRAIN)")

    brain = result['brain_state']
    print(f"\n🧠 Brain Modalities (Thalamic Gates):")

    if brain['gates']:
        gate_array = np.array(brain['gates'])
        modality_names = [
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal_pattern', 'error_signal', 'success_signal'
        ]

        # Sort by activation
        sorted_indices = np.argsort(gate_array)[::-1]

        print(f"\n   Top 5 Active Modalities:")
        for i in range(min(5, len(sorted_indices))):
            idx = sorted_indices[i]
            if idx < len(modality_names):
                name = modality_names[idx]
                value = gate_array[idx]
                bar = "█" * int(value * 50)
                print(f"   {i+1}. {name:20s} {value:5.1%} {bar}")

        print(f"\n   Gate Statistics:")
        print(f"   Sum:      {np.sum(gate_array):.6f}  (should be 1.0)")
        print(f"   Max:      {np.max(gate_array):.3f}")
        print(f"   Min:      {np.min(gate_array):.3f}")
        print(f"   Entropy:  {-np.sum(gate_array * np.log(gate_array + 1e-10)):.3f}")

        entropy = -np.sum(gate_array * np.log(gate_array + 1e-10))
        max_entropy = np.log(len(gate_array))

        print(f"\n💡 Gate Distribution Interpretation:")
        if entropy / max_entropy < 0.3:
            print(f"   → FOCUSED: One or two modalities dominate")
            print(f"   → Clear, decisive brain routing")
        elif entropy / max_entropy > 0.7:
            print(f"   → DISTRIBUTED: Activity spread across many modalities")
            print(f"   → Uncertain or complex task requiring multiple brain areas")
        else:
            print(f"   → BALANCED: Moderate distribution")

    print(f"\n🎯 Dominant Modalities (Reasoning Drivers):")
    for i, mod in enumerate(brain['dominant_modalities'][:3], 1):
        print(f"   {i}. {mod}")

    print(f"\n📊 Prediction Confidence:")
    print(f"   Overall Confidence:      {pred['confidence']:.1%}")

    if pred['confidence'] >= 0.8:
        confidence_level = "VERY HIGH ⭐"
        explanation = "Lots of training data, familiar task, high success rate"
    elif pred['confidence'] >= 0.6:
        confidence_level = "HIGH 🟢"
        explanation = "Good training data, moderately familiar task"
    elif pred['confidence'] >= 0.4:
        confidence_level = "MEDIUM 🟡"
        explanation = "Some training data, somewhat familiar task"
    else:
        confidence_level = "LOW 🔴"
        explanation = "Limited training data, unfamiliar task"

    print(f"   Level: {confidence_level}")
    print(f"   Means: {explanation}")

    # ========================================================================
    # LAYER 3 ANALYSIS
    # ========================================================================
    print_section("LAYER 3: DECISION ROUTER (MULTI-TARGET)")

    print(f"\n🎲 Intervention Distribution:")
    print(f"\n   PRIMARY DECISION:")
    print(f"   Action:      {pred['primary_action']}")
    print(f"   Weight:      {pred['primary_weight']:.1%}")
    print(f"   Confidence:  {pred['confidence']:.1%}")
    print(f"   Reasoning:   {pred['primary_reasoning']}")

    print(f"\n   ALTERNATIVE OPTIONS:")
    for i, alt in enumerate(pred['alternatives'], 1):
        bar = "▓" * int(alt['weight'] * 50)
        print(f"   {i}. {alt['action']:12s} {alt['weight']:5.1%} {bar}")

    # Calculate weight distribution stats
    weights = [pred['primary_weight']] + [a['weight'] for a in pred['alternatives']]
    weights_array = np.array(weights)

    print(f"\n   Distribution Statistics:")
    print(f"   Total weight sum:  {sum(weights):.6f}  (should be ~1.0)")
    print(f"   Primary dominance: {pred['primary_weight'] / sum(weights):.1%}")

    print(f"\n💡 Interpretation:")
    if pred['primary_weight'] > 0.7:
        print(f"   → DECISIVE: Primary action strongly dominates ({pred['primary_weight']:.0%})")
        print(f"   → High certainty about best intervention")
    elif pred['primary_weight'] < 0.4:
        print(f"   → UNCERTAIN: Competing interventions ({pred['primary_weight']:.0%})")
        print(f"   → Consider multiple strategies in parallel")
    else:
        print(f"   → MODERATE: Primary action leads but alternatives viable")

    # ========================================================================
    # REASONING CHAIN ANALYSIS
    # ========================================================================
    print_section("10-STEP REASONING CHAIN")

    print("\nHow the system arrived at this decision:\n")
    for i, step in enumerate(result['reasoning_chain'], 1):
        print(f"{i:2d}. {step}")

    # ========================================================================
    # MATHEMATICAL BREAKDOWN
    # ========================================================================
    print_section("MATHEMATICAL BREAKDOWN")

    if brain['gates']:
        gate_array = np.array(brain['gates'])

        print("\n📐 Thalamic Gating Process:")
        print(f"\n   Input: {len(gate_array)} brain modality activations")
        print(f"   Gates sum to 1.0: {np.sum(gate_array):.6f}")
        print(f"   Gates represent competitive routing (softmax normalized)")

        print(f"\n   Example calculation for primary action '{pred['primary_action']}':")
        print(f"   weight = Σ(gate_i × routing_matrix[i, '{pred['primary_action']}'])")
        print(f"   After softmax normalization → {pred['primary_weight']:.1%}")

    print(f"\n📊 Confidence Calculation (Layer 2):")
    print(f"   confidence = (data_factor × 0.4) +")
    print(f"                (success_factor × 0.4) +")
    print(f"                (familiarity_factor × 0.2)")
    print(f"   Result: {pred['confidence']:.3f}")

    # ========================================================================
    # RECOMMENDATIONS
    # ========================================================================
    print_section("SYSTEM RECOMMENDATIONS")

    print(f"\n✅ Primary Strategy:")
    print(f"   Execute: {pred['primary_action'].upper()}")
    print(f"   Confidence: {pred['confidence']:.0%}")
    print(f"   Rationale: {pred['primary_reasoning']}")

    print(f"\n⚠️  Fallback Strategies (if primary fails):")
    for i, alt in enumerate(pred['alternatives'][:2], 1):
        print(f"   {i}. Try '{alt['action']}' (weight: {alt['weight']:.0%})")

    if pred['confidence'] < 0.5:
        print(f"\n⚡ Warning: Low confidence ({pred['confidence']:.0%})")
        print(f"   → Consider gathering more information before acting")
        print(f"   → This may be an unfamiliar task type")
        print(f"   → Proceed with caution and monitor closely")

    # ========================================================================
    # FULL JSON OUTPUT
    # ========================================================================
    print_section("COMPLETE JSON OUTPUT")

    print(f"\n{json.dumps(result, indent=2, default=str)}")

    print("\n" + "=" * 80)
    print("  Analysis Complete!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    # Example tasks to analyze
    tasks = [
        "Deploy Docker container urgently for production",
        # "Debug failing unit tests in authentication module",
        # "Analyze customer churn data and create visualization"
    ]

    for task in tasks:
        analyze_prediction(task)
