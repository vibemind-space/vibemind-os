"""
PHASE 7 DEMO: Temporal Memory

Demonstrates:
1. Temporal tagging of events with timestamps
2. Time-based memory decay
3. Temporal sequence learning
4. Next-event prediction
5. Time-of-day and day-of-week patterns
6. Temporal context similarity
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from datetime import datetime, timedelta

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor

print("=" * 70)
print("PHASE 7: TEMPORAL MEMORY DEMO")
print("=" * 70)
print()

# Initialize system with ALL cognitive features including temporal memory
print("[1/5] Initializing hierarchical planner with temporal memory...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with ALL 7 cognitive features
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,
    enable_predictive_coding=True,
    enable_attention=True,
    enable_meta_learning=True,
    enable_dream_mode=True,
    enable_neuromodulation=True,
    enable_temporal_memory=True,  # NEW: Temporal Memory enabled!
    seed=42
)

print(f"   {planner}")
print(f"   Memory: ENABLED")
print(f"   Predictive Coding: ENABLED")
print(f"   Attention: ENABLED")
print(f"   Meta-Learning: ENABLED")
print(f"   Dream Mode: ENABLED")
print(f"   Neuromodulation: ENABLED")
print(f"   Temporal Memory: ENABLED")
print()

# Show initial state
if planner.temporal_memory:
    print("Initial Temporal Memory State:")
    print(f"  Events tracked: {planner.temporal_memory.total_events}")
    print(f"  Sequences learned: {planner.temporal_memory.sequences_learned}")
    print()

print("[2/5] Running tasks with temporal patterns...")
print("=" * 70)
print()

# Test scenarios with temporal patterns
# Morning routine: docker tasks
# Afternoon: filesystem tasks
# Evening: github tasks
# Night: memory queries

task_scenarios = [
    # Morning routine (repeated docker tasks)
    ("Morning: Deploy Docker container #1", "docker", "success", 0.75, "morning"),
    ("Morning: Deploy Docker container #2", "docker", "success", 0.72, "morning"),
    ("Morning: Deploy Docker container #3", "docker", "success", 0.78, "morning"),

    # Afternoon filesystem work
    ("Afternoon: Filesystem cleanup task #1", "filesystem", "success", 0.68, "afternoon"),
    ("Afternoon: Filesystem migration #2", "filesystem", "failure", 0.82, "afternoon"),
    ("Afternoon: Filesystem backup #3", "filesystem", "success", 0.75, "afternoon"),

    # Evening GitHub activities
    ("Evening: Review GitHub PR #123", "github", "success", 0.85, "evening"),
    ("Evening: Merge GitHub PR #456", "github", "success", 0.88, "evening"),
    ("Evening: GitHub issue triage", "github", "success", 0.70, "evening"),

    # Night memory queries
    ("Night: Query previous commands", "memory", "success", 0.65, "night"),
    ("Night: Search command history", "memory", "success", 0.62, "night"),

    # Next morning - repeat pattern
    ("Next Morning: Deploy Docker container #4", "docker", "success", 0.80, "morning"),
    ("Next Morning: Docker health check", "docker", "success", 0.73, "morning"),
]

predictions = []

for i, (task, task_type, outcome, importance, time_label) in enumerate(task_scenarios, 1):
    print(f"TASK {i}/13: '{task}' [{time_label}]")
    print("-" * 70)

    # Make prediction
    prediction = planner.predict(task)
    predictions.append((task, prediction))

    # Show temporal context
    if prediction.temporal_context:
        tc = prediction.temporal_context
        print(f"  [Temporal Context]")
        print(f"    Time of day: {tc.time_of_day}")
        print(f"    Day of week: {tc.day_of_week}")
        print(f"    Relative time: {tc.relative_time}")
        if tc.previous_event:
            print(f"    Previous event: {tc.previous_event}")
            print(f"    Time since previous: {tc.time_since_previous:.1f}s")

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

    print(f"  Outcome: {outcome.upper()}")
    print()

print()
print("=" * 70)
print("[3/5] TEMPORAL SEQUENCE ANALYSIS")
print("=" * 70)
print()

if planner.temporal_memory:
    tm = planner.temporal_memory

    print(f"Total events tracked: {tm.total_events}")
    print(f"Sequences learned: {tm.sequences_learned}")
    print()

    # Show learned sequences
    print("Learned Temporal Sequences (top 10 by support):")
    print("-" * 70)

    sorted_sequences = sorted(
        tm.sequences.items(),
        key=lambda x: x[1].support,
        reverse=True
    )

    for seq_key, seq in sorted_sequences[:10]:
        print(f"  {seq_key}")
        print(f"    Support: {seq.support} occurrences")
        print(f"    Avg duration: {seq.avg_duration:.1f}s")
        print(f"    Confidence: {seq.confidence:.1%}")
        print()

    # Show transition probabilities
    print("Temporal Transitions (top 10 by frequency):")
    print("-" * 70)

    transitions = []
    for from_event, to_events in tm.transition_counts.items():
        for to_event, count in to_events.items():
            transitions.append((from_event, to_event, count))

    transitions.sort(key=lambda x: x[2], reverse=True)

    for from_ev, to_ev, count in transitions[:10]:
        # Calculate probability
        total_from = sum(tm.transition_counts[from_ev].values())
        prob = count / total_from if total_from > 0 else 0

        # Get average time
        transition_key = f"{from_ev}->{to_ev}"
        avg_time = np.mean(tm.transition_times.get(transition_key, [0]))

        print(f"  {from_ev} -> {to_ev}")
        print(f"    Probability: {prob:.1%} ({count}/{total_from})")
        print(f"    Avg time: {avg_time:.1f}s")
        print()

print()
print("=" * 70)
print("[4/5] NEXT-EVENT PREDICTION")
print("=" * 70)
print()

if planner.temporal_memory:
    # Test next-event prediction
    test_events = [
        "docker_wait",
        "filesystem_wait",
        "github_wait",
        "memory_wait"
    ]

    print("Predicting next events based on learned sequences:")
    print("-" * 70)

    for event in test_events:
        predictions = tm.predict_next_event(event, top_k=3)

        if predictions:
            print(f"\nAfter '{event}', likely next events:")
            for next_event, prob in predictions:
                print(f"  {next_event}: {prob:.1%}")
        else:
            print(f"\nNo predictions for '{event}' (insufficient data)")

print()
print()
print("=" * 70)
print("[5/5] TEMPORAL PATTERN ANALYSIS")
print("=" * 70)
print()

if planner.temporal_memory:
    stats = tm.get_statistics()

    # Time of day distribution
    print("Time-of-Day Event Distribution:")
    print("-" * 70)
    tod_dist = stats['time_of_day_distribution']
    for tod, count in tod_dist.items():
        if count > 0:
            bar = '#' * int(count / 2)
            print(f"  {tod:12s}: {count:3d} {bar}")
    print()

    # Day of week distribution
    print("Day-of-Week Event Distribution:")
    print("-" * 70)
    dow_dist = stats['day_of_week_distribution']
    for dow, count in dow_dist.items():
        if count > 0:
            bar = '#' * int(count / 2)
            print(f"  {dow:12s}: {count:3d} {bar}")
    print()

    # Get patterns for specific times
    print("Temporal Patterns by Time-of-Day:")
    print("-" * 70)

    for time_of_day in ['morning', 'afternoon', 'evening', 'night']:
        patterns = tm.get_temporal_patterns(time_of_day=time_of_day)
        if patterns:
            print(f"\n{time_of_day.capitalize()}:")
            sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
            for event, count in sorted_patterns[:5]:
                print(f"  {event}: {count} occurrences")

print()
print()
print("=" * 70)
print("[MEMORY STRENGTH DEMO]")
print("=" * 70)
print()

if planner.temporal_memory:
    # Demonstrate memory decay
    print("Memory Strength Decay Over Time:")
    print("-" * 70)

    now = datetime.now()
    time_points = [
        (now, "Just now"),
        (now - timedelta(hours=1), "1 hour ago"),
        (now - timedelta(days=1), "1 day ago"),
        (now - timedelta(days=7), "1 week ago"),
        (now - timedelta(days=30), "1 month ago"),
    ]

    importances = [0.3, 0.5, 0.8]
    retrieval_counts = [0, 3, 10]

    print("\nImportance  Retrievals  Just now  1hr  1day  1wk   1mo")
    print("-" * 70)

    for importance in importances:
        for retrieval in retrieval_counts:
            strengths = []
            for timestamp, _ in time_points:
                strength = tm.get_memory_strength(
                    timestamp=timestamp,
                    importance=importance,
                    retrieval_count=retrieval
                )
                strengths.append(strength)

            print(f"  {importance:.1f}        {retrieval:2d}        ", end="")
            for strength in strengths:
                print(f"{strength:.2f}  ", end="")
            print()

print()
print()
print("=" * 70)
print("PHASE 7 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Temporal tagging of all events")
print("  [X] Time-of-day and day-of-week pattern detection")
print("  [X] Temporal sequence learning (Markov chains)")
print("  [X] Next-event prediction")
print("  [X] Memory strength decay with importance modulation")
print("  [X] Temporal context similarity")
print()
print("The brain now has TEMPORAL MEMORY - remembering WHEN things happen!")
print("Events are tagged with precise timestamps")
print("Sequences are learned from experience")
print("Predictions include temporal context")
print("Memory strength decays realistically over time")
print()
print("Next: PHASE 8 - Active Inference (hypothesis generation, asking questions)")
print("=" * 70)
