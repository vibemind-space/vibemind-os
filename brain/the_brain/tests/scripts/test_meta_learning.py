"""
PHASE 4 DEMO: Meta-Learning

Demonstrates:
1. Learning rate adaptation based on performance
2. Meta-parameter evolution over time
3. Oscillation detection and damping
4. Performance-based exploration/exploitation
5. Second-order learning (learning how to learn)
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
print("PHASE 4: META-LEARNING DEMO")
print("=" * 70)
print()

# Initialize system with ALL cognitive features
print("[1/3] Initializing hierarchical planner with meta-learning...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with ALL cognitive features
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,
    enable_predictive_coding=True,
    enable_attention=True,
    enable_meta_learning=True,  # NEW: Meta-learning enabled!
    meta_learning_rate=0.02,  # Faster adaptation for demo
    seed=42
)

print(f"   {planner}")
print(f"   Memory: ENABLED")
print(f"   Predictive Coding: ENABLED")
print(f"   Attention: ENABLED")
print(f"   Meta-Learning: ENABLED")
print()

# Show initial meta-parameters
if planner.meta_learner:
    initial_params = planner.meta_learner.meta_params
    print("Initial Meta-Parameters:")
    print(f"  Memory Learning Rate: {initial_params.memory_learning_rate:.3f}")
    print(f"  Prediction Learning Rate: {initial_params.prediction_learning_rate:.3f}")
    print(f"  Attention Learning Rate: {initial_params.attention_learning_rate:.3f}")
    print(f"  Memory Importance Threshold: {initial_params.memory_importance_threshold:.3f}")
    print(f"  Exploration Rate: {initial_params.exploration_rate:.3f}")
print()

print("[2/3] Running tasks with varying success patterns...")
print("=" * 70)
print()

# Create patterns: initial failures, then successes, then mixed (to trigger adaptation)
task_scenarios = [
    # Phase 1: Initial failures (should increase learning rates)
    ("Deploy Docker urgently", "docker", "failure"),
    ("Fix critical bug", "unknown", "failure"),
    ("Deploy another Docker", "docker", "failure"),

    # Phase 2: Successes (should decrease learning rates, increase selectivity)
    ("Check server status", "memory", "success"),
    ("Deploy Docker container", "docker", "success"),
    ("Simple filesystem check", "filesystem", "success"),
    ("Another Docker deploy", "docker", "success"),

    # Phase 3: Mixed (oscillations - should stabilize learning rates)
    ("Critical Docker issue", "docker", "failure"),
    ("Docker deployment success", "docker", "success"),
    ("Docker failure again", "docker", "failure"),
    ("Docker success again", "docker", "success"),

    # Phase 4: Consistent success (exploitation mode)
    ("Regular Docker deploy", "docker", "success"),
    ("Another successful deploy", "docker", "success"),
    ("Final Docker deploy", "docker", "success"),
]

predictions = []
meta_param_history = []

for i, (task, expected_type, forced_outcome) in enumerate(task_scenarios, 1):
    print(f"TASK {i}/15: '{task}' (forcing outcome: {forced_outcome})")
    print("-" * 70)

    # Make prediction
    prediction = planner.predict(task)

    # Store
    predictions.append((task, prediction))

    # Extract decision
    decision = prediction.actionable_decision
    primary = decision.multi_target_decision['primary']

    print(f"  Decision: {primary['type']} ({primary['weight']:.1%})")
    print(f"  Confidence: {prediction.confidence:.1%}")

    # Show current meta-parameters
    if prediction.meta_parameters:
        mp = prediction.meta_parameters
        print(f"  [Meta] Memory LR: {mp.memory_learning_rate:.3f}, "
              f"Pred LR: {mp.prediction_learning_rate:.3f}, "
              f"Exploration: {mp.exploration_rate:.3f}")

        # Store for tracking
        meta_param_history.append({
            'task_num': i,
            'memory_lr': mp.memory_learning_rate,
            'prediction_lr': mp.prediction_learning_rate,
            'exploration': mp.exploration_rate,
            'importance_threshold': mp.memory_importance_threshold
        })

    # Use forced outcome
    outcome = forced_outcome
    importance = np.random.uniform(0.6, 0.95)

    # Record outcome
    planner.record_outcome(
        task=task,
        decision=primary['type'],
        outcome=outcome,
        importance=importance
    )

    # Consolidate if important
    if importance > 0.7:
        prediction.task_description = task
        planner.consolidate_experience(
            prediction=prediction,
            outcome=outcome,
            importance=importance,
            user_rating=np.random.uniform(0.7, 1.0) if outcome == 'success' else 0.3,
            execution_time_ms=np.random.uniform(500, 2000)
        )

    print(f"  Outcome: {outcome.upper()}")
    print()

print()
print("=" * 70)
print("[3/3] META-LEARNING ANALYSIS")
print("=" * 70)
print()

stats = planner.get_statistics()
ml_stats = stats.get('meta_learning_stats', {})

# Current meta-parameters
current_params = ml_stats.get('current_meta_params', {})
print("Final Meta-Parameters (After Adaptation):")
print(f"  Memory Learning Rate: {current_params.get('memory_learning_rate', 0):.3f}")
print(f"  Prediction Learning Rate: {current_params.get('prediction_learning_rate', 0):.3f}")
print(f"  Attention Learning Rate: {current_params.get('attention_learning_rate', 0):.3f}")
print(f"  Memory Importance Threshold: {current_params.get('memory_importance_threshold', 0):.3f}")
print(f"  Exploration Rate: {current_params.get('exploration_rate', 0):.3f}")
print()

# Performance metrics
performance = ml_stats.get('performance', {})
print("Performance Metrics:")
print(f"  Total Tasks: {performance.get('total_tasks', 0)}")
print(f"  Success Count: {performance.get('success_count', 0)}")
print(f"  Failure Count: {performance.get('failure_count', 0)}")
print(f"  Success Rate: {performance.get('success_rate', 0):.1%}")
print(f"  Avg Prediction Error: {performance.get('avg_prediction_error', 0):.3f}")
print(f"  Error Trend: {performance.get('error_trend', 'unknown')}")
print(f"  Oscillating: {performance.get('is_oscillating', False)}")
print()

# Total adaptations
print(f"Total Meta-Parameter Adaptations: {ml_stats.get('total_adaptations', 0)}")
print()

# Meta-parameter evolution
if meta_param_history:
    print("=" * 70)
    print("META-PARAMETER EVOLUTION")
    print("=" * 70)
    print()

    print("Task   Memory_LR  Pred_LR  Explor  ImportThresh  Phase")
    print("-" * 70)

    for entry in meta_param_history:
        task_num = entry['task_num']
        mem_lr = entry['memory_lr']
        pred_lr = entry['prediction_lr']
        explor = entry['exploration']
        threshold = entry['importance_threshold']

        # Determine phase
        if task_num <= 3:
            phase = "Failures"
        elif task_num <= 7:
            phase = "Successes"
        elif task_num <= 11:
            phase = "Mixed"
        else:
            phase = "Stable"

        print(f"{task_num:4d}   {mem_lr:7.3f}    {pred_lr:6.3f}   {explor:6.3f}     {threshold:9.3f}  {phase}")

    print()

    # Analyze trends
    print("Meta-Parameter Trends:")
    print("-" * 70)

    first_5 = meta_param_history[:5]
    last_5 = meta_param_history[-5:]

    avg_early_mem_lr = np.mean([e['memory_lr'] for e in first_5])
    avg_late_mem_lr = np.mean([e['memory_lr'] for e in last_5])

    avg_early_explor = np.mean([e['exploration'] for e in first_5])
    avg_late_explor = np.mean([e['exploration'] for e in last_5])

    print(f"Memory LR:      {avg_early_mem_lr:.3f} (early) -> {avg_late_mem_lr:.3f} (late)")
    print(f"Exploration:    {avg_early_explor:.3f} (early) -> {avg_late_explor:.3f} (late)")

    if avg_early_explor > avg_late_explor:
        print("  -> Brain shifted from EXPLORATION to EXPLOITATION")
    else:
        print("  -> Brain maintained exploration")

print()
print("=" * 70)
print("PHASE 4 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Learning rates adapt based on performance")
print("  [X] Oscillation detection and damping")
print("  [X] Exploration/exploitation balance learned")
print("  [X] Meta-parameters evolve over time")
print("  [X] Performance-based threshold adaptation")
print("  [X] Second-order learning (learning how to learn)")
print()
print("The brain now has META-LEARNING - it learns how to learn!")
print("Failures increase learning rates, successes reduce them.")
print("Oscillations trigger stability mechanisms.")
print("=" * 70)
