"""
PHASE 2 DEMO: Predictive Coding Integration

Demonstrates:
1. Task feature prediction at Layer 1
2. Decision outcome prediction at Layer 3
3. Prediction error computation and surprise detection
4. Curiosity-driven exploration signal
5. Learning from prediction errors
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor

print("=" * 70)
print("PHASE 2: PREDICTIVE CODING DEMO")
print("=" * 70)
print()

# Initialize system with memory AND predictive coding enabled
print("[1/4] Initializing hierarchical planner with predictive coding...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with predictive coding
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,
    enable_predictive_coding=True,  # NEW: Predictive coding enabled!
    seed=42
)

print(f"   {planner}")
print(f"   Memory: Working={len(planner.memory.working)}, Episodic={len(planner.memory.episodic)}")
print(f"   Predictive Coding: ENABLED")
print()

print("[2/4] Making predictions with predictive coding...")
print("=" * 70)
print()

# Test tasks - mix of similar and novel tasks to trigger different surprise levels
test_tasks = [
    ("Deploy Docker container", "docker"),
    ("Deploy Docker with authentication", "docker"),  # Similar to first
    ("Fix critical security vulnerability", "unknown"),  # Novel!
    ("Deploy another Docker service", "docker"),  # Similar again
    ("Quantum entanglement experiment", "unknown"),  # Very novel!
    ("Deploy Docker update", "docker"),  # Familiar by now
]

predictions = []

for i, (task, expected_type) in enumerate(test_tasks, 1):
    print(f"TASK {i}: '{task}'")
    print("-" * 70)

    # Make prediction (automatically uses predictive coding)
    prediction = planner.predict(task)

    # Store for later
    predictions.append((task, prediction))

    # Extract decision
    decision = prediction.actionable_decision
    primary = decision.multi_target_decision['primary']

    print(f"\n  Primary Action: {primary['type']} ({primary['weight']:.1%})")
    print(f"  Confidence: {prediction.confidence:.1%}")
    print(f"  Task Type: {prediction.task_type}")

    # Show prediction errors if available
    if prediction.prediction_errors:
        layer1_pe = prediction.prediction_errors.get('layer1')
        if layer1_pe:
            print(f"\n  [Predictive] Layer 1 Prediction Error:")
            print(f"    Error Magnitude: {layer1_pe['error_magnitude']:.3f}")
            print(f"    Surprise Level: {layer1_pe['surprise_level']}")

    # Show curiosity signal
    if prediction.curiosity_signal:
        curiosity = prediction.curiosity_signal
        print(f"\n  [Curiosity] Level: {curiosity['curiosity_level'].upper()}")
        print(f"    Recommendation: {curiosity['recommendation']}")
        print(f"    Layer 1 Error: {curiosity['layer1_error']:.3f}")
        print(f"    Layer 3 Error: {curiosity['layer3_error']:.3f}")

    print()

    # Simulate outcome
    # Novel tasks have lower success rate
    if expected_type == 'unknown':
        outcome = 'success' if np.random.rand() > 0.5 else 'failure'
    else:
        outcome = 'success' if np.random.rand() > 0.2 else 'failure'

    importance = np.random.uniform(0.5, 1.0)

    # Record outcome in working memory
    planner.record_outcome(
        task=task,
        decision=primary['type'],
        outcome=outcome,
        importance=importance
    )

    # If important, consolidate to episodic memory
    # This also updates Layer 3 prediction error!
    if importance > 0.7:
        prediction.task_description = task
        planner.consolidate_experience(
            prediction=prediction,
            outcome=outcome,
            importance=importance,
            user_rating=np.random.uniform(0.7, 1.0),
            execution_time_ms=np.random.uniform(500, 2000)
        )

    print(f"  Outcome: {outcome.upper()} (importance={importance:.2f})")
    print()

print()
print("=" * 70)
print("[3/4] PREDICTIVE CODING STATISTICS")
print("=" * 70)
print()

stats = planner.get_statistics()
pc_stats = stats.get('predictive_coding_stats', {})

print(f"Total Predictions: {pc_stats.get('total_predictions', 0)}")
print(f"High Surprise Events: {pc_stats.get('high_surprise_events', 0)}")
print()

# Layer 1 predictor stats
layer1_stats = pc_stats.get('layer1', {})
if layer1_stats:
    print("Layer 1 (Task Feature Predictor):")
    print(f"  Prediction Count: {layer1_stats.get('prediction_count', 0)}")
    recent = layer1_stats.get('recent_stats', {})
    if recent:
        print(f"  Mean Error: {recent.get('mean_error', 0):.3f}")
        print(f"  Std Error: {recent.get('std_error', 0):.3f}")
        print(f"  Surprise Rate: {recent.get('surprise_rate', 0):.1%}")
print()

# Layer 3 predictor stats
layer3_stats = pc_stats.get('layer3', {})
if layer3_stats:
    print("Layer 3 (Decision Outcome Predictor):")
    print(f"  Prediction Count: {layer3_stats.get('prediction_count', 0)}")
    recent = layer3_stats.get('recent_stats', {})
    if recent:
        print(f"  Mean Error: {recent.get('mean_error', 0):.3f}")
        print(f"  Std Error: {recent.get('std_error', 0):.3f}")
        print(f"  Surprise Rate: {recent.get('surprise_rate', 0):.1%}")
print()

# Curiosity signal
curiosity = pc_stats.get('curiosity', {})
if curiosity:
    print("Curiosity Signal:")
    print(f"  Level: {curiosity.get('curiosity_level', 'unknown').upper()}")
    print(f"  Recommendation: {curiosity.get('recommendation', 'balanced')}")
    print(f"  Layer 1 Surprise Rate: {curiosity.get('layer1_surprise_rate', 0):.1%}")
    print(f"  Layer 3 Surprise Rate: {curiosity.get('layer3_surprise_rate', 0):.1%}")
print()

print("=" * 70)
print("[4/4] PREDICTION ERROR EVOLUTION")
print("=" * 70)
print()

# Show how prediction errors changed over time
print("Task Progression (showing surprise evolution):")
print("-" * 70)

for i, (task, pred) in enumerate(predictions, 1):
    if pred.prediction_errors and 'layer1' in pred.prediction_errors:
        layer1_pe = pred.prediction_errors['layer1']
        if layer1_pe:
            surprise = layer1_pe['surprise_level']
            error = layer1_pe['error_magnitude']

            # Visual indicator
            if surprise == 'extreme':
                indicator = '[!] EXTREME'
            elif surprise == 'high':
                indicator = '[!!] HIGH'
            elif surprise == 'low':
                indicator = '[*] LOW'
            else:
                indicator = '[-] NORMAL'

            print(f"{i}. {task[:40]:40s} {indicator:12s} (error={error:.3f})")
        else:
            print(f"{i}. {task[:40]:40s} {'[ ] NO DATA':12s}")
    else:
        print(f"{i}. {task[:40]:40s} {'[ ] NO DATA':12s}")

print()
print("=" * 70)
print("PHASE 2 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Layer 1 predicts task features before processing")
print("  [X] Layer 3 predicts decision outcomes")
print("  [X] Prediction errors computed at each layer")
print("  [X] Surprise detection based on historical errors")
print("  [X] Curiosity signal guides exploration vs exploitation")
print("  [X] Brain learns from prediction errors")
print()
print("The brain now has PREDICTIVE CODING - it anticipates the future!")
print("High prediction errors indicate novel situations requiring attention.")
print("=" * 70)
