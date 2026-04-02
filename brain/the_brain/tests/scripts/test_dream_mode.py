"""
PHASE 5 DEMO: Dream Mode (Offline Consolidation)

Demonstrates:
1. Building up episodic memories through task execution
2. Offline consolidation during "sleep" cycles
3. Experience replay (forward and backward)
4. Counterfactual learning (what-if scenarios)
5. Pattern extraction across similar experiences
6. Using discovered patterns to inform future decisions
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
print("PHASE 5: DREAM MODE DEMO")
print("=" * 70)
print()

# Initialize system with ALL cognitive features including dream mode
print("[1/5] Initializing hierarchical planner with dream mode...")
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
    enable_dream_mode=True,  # NEW: Dream mode enabled!
    seed=42
)

print(f"   {planner}")
print(f"   Memory: ENABLED")
print(f"   Predictive Coding: ENABLED")
print(f"   Attention: ENABLED")
print(f"   Meta-Learning: ENABLED")
print(f"   Dream Mode: ENABLED")
print()

print("[2/5] Building episodic memories through task execution...")
print("=" * 70)
print()

# Execute tasks to build episodic memories
# Mix of successes and failures across different task types
task_scenarios = [
    # Docker tasks
    ("Deploy production Docker container", "docker", "success", 0.85),
    ("Docker deployment failed - port conflict", "docker", "failure", 0.90),
    ("Scale Docker service to 5 replicas", "docker", "success", 0.80),
    ("Docker image build timeout", "docker", "failure", 0.75),

    # GitHub tasks
    ("Create pull request for feature branch", "github", "success", 0.88),
    ("Git merge conflict resolution", "github", "failure", 0.82),
    ("Review and merge PR #42", "github", "success", 0.79),

    # Filesystem tasks
    ("Reorganize project directory structure", "filesystem", "success", 0.81),
    ("Filesystem permissions error", "filesystem", "failure", 0.85),

    # Memory/query tasks
    ("Search conversation history for Docker issues", "memory", "success", 0.77),
    ("Find previous filesystem commands", "memory", "success", 0.73),
]

predictions = []

for i, (task, task_type, outcome, importance) in enumerate(task_scenarios, 1):
    print(f"TASK {i}/11: '{task}'")
    print("-" * 70)

    # Make prediction
    prediction = planner.predict(task)
    predictions.append((task, prediction))

    # Extract decision
    decision = prediction.actionable_decision
    primary = decision.multi_target_decision['primary']

    print(f"  Decision: {primary['type']} ({primary['weight']:.1%})")
    print(f"  Confidence: {prediction.confidence:.1%}")

    # Record outcome
    planner.record_outcome(
        task=task,
        decision=primary['type'],
        outcome=outcome,
        importance=importance
    )

    # Consolidate to episodic if important
    if importance > 0.7:
        prediction.task_description = task
        planner.consolidate_experience(
            prediction=prediction,
            outcome=outcome,
            importance=importance,
            user_rating=np.random.uniform(0.7, 1.0) if outcome == 'success' else 0.3,
            execution_time_ms=np.random.uniform(500, 3000)
        )

    print(f"  Outcome: {outcome.upper()} (importance={importance:.2f})")
    print()

print()
print("=" * 70)
print("[3/5] ENTERING DREAM STATE (Offline Consolidation)")
print("=" * 70)
print()

# Get memory stats before dreaming
stats_before = planner.get_statistics()
memory_stats_before = stats_before.get('memory_stats', {})
print(f"Episodic memories before dreaming: {memory_stats_before.get('episodic_memory_size', 0)}")
print()

# Trigger first dream cycle
print("Dream Cycle 1: Experience Replay and Pattern Extraction...")
print("-" * 70)
dreams_cycle1 = planner.trigger_dream_cycle(num_dreams=5)

print()
print(f"Dreams from cycle 1: {len(dreams_cycle1)}")
for i, dream in enumerate(dreams_cycle1, 1):
    print(f"\n  Dream {i}:")
    print(f"    Type: {dream.dream_type}")
    print(f"    Task: {dream.original_task[:50]}...")
    print(f"    Original: {dream.original_decision} -> {dream.original_outcome}")

    if dream.alternative_decision:
        print(f"    Counterfactual: {dream.alternative_decision} -> {dream.hypothetical_outcome}")
        if dream.original_outcome == 'failure' and dream.hypothetical_outcome == 'success':
            print(f"    [Learning] Alternative might have succeeded!")

    if dream.pattern_discovered:
        print(f"    Pattern: {dream.pattern_discovered}")

print()
print()

# Trigger second dream cycle
print("Dream Cycle 2: Additional Consolidation...")
print("-" * 70)
dreams_cycle2 = planner.trigger_dream_cycle(num_dreams=5)

print()
print()
print("=" * 70)
print("[4/5] DREAM MODE ANALYSIS")
print("=" * 70)
print()

stats_after = planner.get_statistics()
dream_stats = stats_after.get('dream_mode_stats', {})

print("Dream Statistics:")
print(f"  Total Dreams: {dream_stats.get('total_dreams', 0)}")
print(f"  Total Replays: {dream_stats.get('total_replays', 0)}")
print(f"  Total Counterfactuals: {dream_stats.get('total_counterfactuals', 0)}")
print(f"  Patterns Discovered: {dream_stats.get('total_patterns_discovered', 0)}")
print()

# Show discovered patterns
patterns = dream_stats.get('patterns', {})
if patterns:
    print("Discovered Patterns:")
    print("-" * 70)
    for pattern_key, pattern in patterns.items():
        print(f"\n  Pattern: {pattern['pattern_type']}")
        print(f"    Preferred Decision: {pattern['decision_preference']}")
        print(f"    Success Rate: {pattern['success_rate']:.1%}")
        print(f"    Support: {pattern['support']} experiences")
        print(f"    Confidence: {pattern['confidence']:.1%}")
        print(f"    Examples:")
        for example in pattern['example_tasks']:
            print(f"      - {example[:50]}...")

print()

# Show recent dreams
recent_dreams = dream_stats.get('recent_dreams', [])
if recent_dreams:
    print("Recent Dreams (last 5):")
    print("-" * 70)
    for i, dream in enumerate(recent_dreams[-5:], 1):
        print(f"\n  {i}. {dream['dream_type'].upper()}")
        print(f"     Original: {dream['original_task'][:40]}...")
        print(f"     {dream['original_decision']} -> {dream['original_outcome']}")
        if dream.get('alternative_decision'):
            print(f"     What-if: {dream['alternative_decision']} -> {dream.get('hypothetical_outcome')}")

print()
print()

print("=" * 70)
print("[5/5] USING DREAM PATTERNS FOR NEW PREDICTIONS")
print("=" * 70)
print()

# Test using dream patterns for new tasks
test_tasks = [
    ("Deploy new Docker microservice", "docker"),
    ("Merge feature branch to main", "github"),
    ("Check filesystem usage statistics", "filesystem")
]

print("Testing pattern-informed predictions...")
print("-" * 70)
print()

for task, expected_type in test_tasks:
    print(f"Task: '{task}'")

    # Check if we have a pattern for this task type
    pattern = planner.get_dream_pattern_for_task(expected_type, min_confidence=0.5)

    if pattern:
        print(f"  [Dream Pattern Found]")
        print(f"    Task type: {pattern.pattern_type}")
        print(f"    Recommended: {pattern.decision_preference}")
        print(f"    Success rate: {pattern.success_rate:.1%}")
        print(f"    Confidence: {pattern.confidence:.1%}")
    else:
        print(f"  [No Pattern] First time seeing {expected_type} tasks")

    # Make prediction
    prediction = planner.predict(task)
    decision = prediction.actionable_decision.multi_target_decision['primary']

    print(f"  Actual Decision: {decision['type']} ({decision['weight']:.1%})")

    # Check if decision matches pattern
    if pattern and decision['type'] == pattern.decision_preference:
        print(f"  [Match!] Decision aligns with learned pattern")

    print()

print()
print("=" * 70)
print("PHASE 5 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Episodic memories accumulated during task execution")
print("  [X] Dream cycles triggered during idle time")
print("  [X] Experience replay (forward and backward)")
print("  [X] Counterfactual learning (what-if scenarios)")
print("  [X] Pattern extraction across similar experiences")
print("  [X] Discovered patterns inform future decisions")
print()
print("The brain now has DREAM MODE - it consolidates offline!")
print("During idle time, the brain:")
print("  - Replays important experiences")
print("  - Explores counterfactual alternatives")
print("  - Extracts patterns across similar tasks")
print("  - Strengthens important memories")
print("  - Learns from hypothetical outcomes")
print()
print("Next: PHASE 6 - Neuromodulation (dopamine, serotonin, etc.)")
print("=" * 70)
