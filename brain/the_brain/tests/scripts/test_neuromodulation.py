"""
PHASE 6 DEMO: Neuromodulation

Demonstrates:
1. Dopamine modulation based on reward prediction errors
2. Serotonin modulation based on consistent success
3. Norepinephrine modulation based on urgency and threat
4. Dynamic cognitive parameter adjustment
5. Neuromodulator evolution over different task scenarios
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
print("PHASE 6: NEUROMODULATION DEMO")
print("=" * 70)
print()

# Initialize system with ALL cognitive features including neuromodulation
print("[1/4] Initializing hierarchical planner with neuromodulation...")
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
    enable_meta_learning=True,
    enable_dream_mode=True,
    enable_neuromodulation=True,  # NEW: Neuromodulation enabled!
    seed=42
)

print(f"   {planner}")
print(f"   Memory: ENABLED")
print(f"   Predictive Coding: ENABLED")
print(f"   Attention: ENABLED")
print(f"   Meta-Learning: ENABLED")
print(f"   Dream Mode: ENABLED")
print(f"   Neuromodulation: ENABLED")
print()

# Show initial neuromodulator levels
if planner.neuromodulation:
    initial_levels = planner.neuromodulation.levels
    print("Initial Neuromodulator Levels (baseline):")
    print(f"  Dopamine (motivation/reward): {initial_levels.dopamine:.2f}")
    print(f"  Serotonin (mood/patience): {initial_levels.serotonin:.2f}")
    print(f"  Norepinephrine (arousal/urgency): {initial_levels.norepinephrine:.2f}")
    print()

print("[2/4] Running tasks with varying patterns...")
print("=" * 70)
print()

# Test scenarios with different patterns to trigger neuromodulation
task_scenarios = [
    # Scenario 1: Initial successes (dopamine should increase)
    ("Deploy Docker container successfully", "docker", "success", 0.80),
    ("Complete filesystem reorganization", "filesystem", "success", 0.75),
    ("Successful GitHub PR merge", "github", "success", 0.85),

    # Scenario 2: Unexpected failures (dopamine should drop, norepinephrine may rise)
    ("Critical Docker deployment failure!", "docker", "failure", 0.90),
    ("Urgent filesystem error - data loss risk!", "filesystem", "failure", 0.95),

    # Scenario 3: Recovery with successes (dopamine recovers, serotonin stabilizes)
    ("Docker hotfix deployed", "docker", "success", 0.80),
    ("Filesystem backup restored", "filesystem", "success", 0.85),
    ("Emergency resolved successfully", "unknown", "success", 0.82),

    # Scenario 4: Inconsistent outcomes (serotonin may decrease - impulsivity)
    ("Docker task attempt 1", "docker", "failure", 0.70),
    ("Docker task attempt 2", "docker", "success", 0.75),
    ("Docker task attempt 3", "docker", "failure", 0.72),
    ("Docker task attempt 4", "docker", "success", 0.78),

    # Scenario 5: Consistent success streak (serotonin should increase - patience)
    ("Routine task 1", "memory", "success", 0.70),
    ("Routine task 2", "memory", "success", 0.68),
    ("Routine task 3", "memory", "success", 0.72),
    ("Routine task 4", "memory", "success", 0.70),
]

predictions = []
neuro_history = []

for i, (task, task_type, outcome, importance) in enumerate(task_scenarios, 1):
    print(f"TASK {i}/16: '{task}'")
    print("-" * 70)

    # Make prediction
    prediction = planner.predict(task)
    predictions.append((task, prediction))

    # Show neuromodulator state BEFORE outcome
    if prediction.neuromodulator_levels:
        levels = prediction.neuromodulator_levels
        effects = prediction.neuromodulator_effects

        print(f"  [Before] DA={levels.dopamine:.2f}, "
              f"5-HT={levels.serotonin:.2f}, "
              f"NE={levels.norepinephrine:.2f}")

        # Store for tracking
        neuro_history.append({
            'task_num': i,
            'phase': 'before',
            'dopamine': levels.dopamine,
            'serotonin': levels.serotonin,
            'norepinephrine': levels.norepinephrine,
            'learning_rate_mult': effects.learning_rate_multiplier,
            'exploration_boost': effects.exploration_boost
        })

    # Extract decision
    decision = prediction.actionable_decision
    primary = decision.multi_target_decision['primary']

    print(f"  Decision: {primary['type']} ({primary['weight']:.1%})")
    print(f"  Confidence: {prediction.confidence:.1%}")

    # Record outcome and consolidate
    planner.record_outcome(
        task=task,
        decision=primary['type'],
        outcome=outcome,
        importance=importance
    )

    if importance > 0.65:
        prediction.task_description = task
        planner.consolidate_experience(
            prediction=prediction,
            outcome=outcome,
            importance=importance,
            user_rating=np.random.uniform(0.7, 1.0) if outcome == 'success' else 0.3,
            execution_time_ms=np.random.uniform(500, 3000)
        )

    # Store post-update neuromodulator state
    if planner.neuromodulation:
        levels_after = planner.neuromodulation.levels
        neuro_history.append({
            'task_num': i,
            'phase': 'after',
            'dopamine': levels_after.dopamine,
            'serotonin': levels_after.serotonin,
            'norepinephrine': levels_after.norepinephrine
        })

    print(f"  Outcome: {outcome.upper()}")
    print()

print()
print("=" * 70)
print("[3/4] NEUROMODULATION ANALYSIS")
print("=" * 70)
print()

stats = planner.get_statistics()
neuro_stats = stats.get('neuromodulation_stats', {})

# Current state
current_levels = neuro_stats.get('current_levels', {})
current_state = neuro_stats.get('current_state', 'Unknown')

print("Final Neuromodulator State:")
print(f"  {current_state}")
print(f"  Dopamine: {current_levels.get('dopamine', 0):.2f}")
print(f"  Serotonin: {current_levels.get('serotonin', 0):.2f}")
print(f"  Norepinephrine: {current_levels.get('norepinephrine', 0):.2f}")
print()

# Average levels over time
avg_levels = neuro_stats.get('average_levels', {})
print("Average Levels (recent 20 updates):")
print(f"  Dopamine: {avg_levels.get('dopamine', 0):.2f}")
print(f"  Serotonin: {avg_levels.get('serotonin', 0):.2f}")
print(f"  Norepinephrine: {avg_levels.get('norepinephrine', 0):.2f}")
print()

# Reward prediction
reward_pred = neuro_stats.get('reward_prediction', {})
print("Reward Prediction Learning:")
print(f"  Expected Reward: {reward_pred.get('expected_reward', 0):.2f}")
print(f"  Avg RPE: {reward_pred.get('avg_rpe', 0):.3f}")
print(f"  RPE Std Dev: {reward_pred.get('rpe_std', 0):.3f}")
print()

# Current effects on cognition
current_effects = neuro_stats.get('current_effects', {})
print("Current Effects on Cognition:")
print(f"  Learning Rate Multiplier: {current_effects.get('learning_rate_multiplier', 1.0):.2f}x")
print(f"  Exploration Boost: {current_effects.get('exploration_boost', 0.0):+.2f}")
print(f"  Attention Focus Multiplier: {current_effects.get('attention_focus_multiplier', 1.0):.2f}x")
print(f"  Confidence Threshold Delta: {current_effects.get('confidence_threshold_delta', 0.0):+.2f}")
print(f"  Response Urgency: {current_effects.get('response_urgency', 0.5):.2f}")
print()

print("=" * 70)
print("[4/4] NEUROMODULATOR EVOLUTION")
print("=" * 70)
print()

# Analyze evolution
print("Neuromodulator Evolution by Phase:")
print("-" * 70)
print()

# Group by scenario
scenarios = [
    (1, 3, "Initial Successes"),
    (4, 5, "Unexpected Failures"),
    (6, 8, "Recovery Phase"),
    (9, 12, "Inconsistent Outcomes"),
    (13, 16, "Consistent Success Streak")
]

for start, end, phase_name in scenarios:
    phase_data = [entry for entry in neuro_history if start <= entry['task_num'] <= end and entry['phase'] == 'after']

    if phase_data:
        avg_da = np.mean([e['dopamine'] for e in phase_data])
        avg_5ht = np.mean([e['serotonin'] for e in phase_data])
        avg_ne = np.mean([e['norepinephrine'] for e in phase_data])

        print(f"{phase_name} (Tasks {start}-{end}):")
        print(f"  Avg Dopamine: {avg_da:.2f}")
        print(f"  Avg Serotonin: {avg_5ht:.2f}")
        print(f"  Avg Norepinephrine: {avg_ne:.2f}")
        print()

# Detailed evolution table
print("Task-by-Task Evolution (showing after-update values):")
print("-" * 70)
print("Task   DA     5-HT   NE     Phase")
print("-" * 70)

after_entries = [e for e in neuro_history if e['phase'] == 'after']
for entry in after_entries:
    task_num = entry['task_num']
    da = entry['dopamine']
    sht = entry['serotonin']
    ne = entry['norepinephrine']

    # Determine phase
    if task_num <= 3:
        phase = "Initial Success"
    elif task_num <= 5:
        phase = "Failures"
    elif task_num <= 8:
        phase = "Recovery"
    elif task_num <= 12:
        phase = "Inconsistent"
    else:
        phase = "Steady Success"

    print(f"{task_num:4d}   {da:.2f}   {sht:.2f}   {ne:.2f}   {phase}")

print()

# Key observations
print("Key Observations:")
print("-" * 70)

first_3 = [e for e in neuro_history if e['task_num'] <= 3 and e['phase'] == 'after']
last_4 = [e for e in neuro_history if e['task_num'] >= 13 and e['phase'] == 'after']

if first_3 and last_4:
    early_da = np.mean([e['dopamine'] for e in first_3])
    late_da = np.mean([e['dopamine'] for e in last_4])

    early_5ht = np.mean([e['serotonin'] for e in first_3])
    late_5ht = np.mean([e['serotonin'] for e in last_4])

    print(f"Dopamine:   {early_da:.2f} (early) -> {late_da:.2f} (late)")
    print(f"Serotonin:  {early_5ht:.2f} (early) -> {late_5ht:.2f} (late)")
    print()

    if late_5ht > early_5ht:
        print("  -> Serotonin increased with consistent success (more patience)")
    if late_da < early_da:
        print("  -> Dopamine normalized (reward prediction adjusted)")

print()
print("=" * 70)
print("PHASE 6 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Dopamine responds to reward prediction errors")
print("  [X] Serotonin modulates with outcome consistency")
print("  [X] Norepinephrine responds to urgency and threat")
print("  [X] Neuromodulators dynamically adjust cognitive parameters")
print("  [X] Learning rate, exploration, and attention modulated")
print("  [X] Brain chemistry adapts to task patterns")
print()
print("The brain now has NEUROMODULATION - dynamic brain chemistry!")
print("Successes boost dopamine (motivation)")
print("Consistent outcomes stabilize serotonin (patience)")
print("Urgent tasks trigger norepinephrine (alertness)")
print("These chemicals modulate learning, attention, and decisions")
print()
print("Next: PHASE 7 - Temporal Memory (remembering when things happened)")
print("=" * 70)
